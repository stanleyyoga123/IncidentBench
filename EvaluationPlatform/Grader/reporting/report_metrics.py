"""Offline report measurements; never invokes a judge or modifies archives."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from grader.time_scope import chaos_intervals, job_scope
from grader.window_comparison import compare_windows, paired_frontend_window


@dataclass(frozen=True)
class ReportConfig:
    score_threshold: float = 0.8  # Strictly greater than, as requested.
    p95_change_limit: float = 0.2  # Fraction: selected / baseline - 1 < this.
    max_5xx_rps: float = 0.5
    window_minutes: float = 5.0
    baseline_ignore_minutes: float = 5.0
    workload: str = "front-end"
    namespace: str | None = "sock-shop"
    repeat_policy: str = "latest_completed_else_latest"

    def __post_init__(self):
        for name in ("score_threshold", "p95_change_limit", "max_5xx_rps", "window_minutes", "baseline_ignore_minutes"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not 0 <= self.score_threshold <= 1 or self.max_5xx_rps < 0 or self.window_minutes <= 0 or self.baseline_ignore_minutes < 0:
            raise ValueError("Invalid threshold or window configuration")
        if self.repeat_policy not in ("latest_completed_else_latest", "all_runs"):
            raise ValueError("Unknown repeat_policy")


def read(path, default=None):
    return json.loads(path.read_text()) if path.is_file() else default


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def stamp(value):
    if not isinstance(value, str):
        return pd.NaT
    result = pd.to_datetime(value, errors="coerce")
    if pd.isna(result) or result.tzinfo is None:
        return pd.NaT
    return result.tz_convert("UTC")


def usable_score(job):
    score = (job.get("rubric") or {}).get("overall_score")
    if (job.get("status") in ("succeeded", "failed")
            and (job.get("alignment") or {}).get("verdict") in ("aligned", "not_aligned")
            and finite(score)):
        return float(score)
    return None


def job_summary(jobs, origin, threshold):
    scored = [(j, usable_score(j)) for j in jobs]
    scored = [(j, s) for j, s in scored if s is not None]
    scores = [s for _, s in scored]
    highest = max(scores) if scores else None
    winners = [j for j, s in scored if s == highest]
    timed = [(stamp(j.get("completed_at")), str(j.get("id", ""))) for j in winners]
    missing_time = any(pd.isna(t) for t, _ in timed)
    known = sorted((t, job_id) for t, job_id in timed if not pd.isna(t))
    # If any tied maximum lacks completion time, the earliest cannot be proven.
    first = known[0] if known and not missing_time else None
    seconds = (first[0] - origin).total_seconds() if first and not pd.isna(origin) else None
    reason = ("no_scored_output" if not scores else "missing_top_score_completion_time" if missing_time
              else "missing_chaos_start" if pd.isna(origin) else "before_chaos_start" if seconds is not None and seconds < 0
              else "available")
    return {
        "max_score": highest, "average_score": sum(scores) / len(scores) if scores else None,
        "sessions": len(jobs), "scored_sessions": len(scores),
        "successful_sessions": sum(s > threshold for s in scores),
        "has_successful_output": highest > threshold if highest is not None else None,
        "first_highest_score_job_id": first[1] if first else None,
        "first_highest_score_completed_at": first[0] if first else pd.NaT,
        "time_to_first_highest_score_seconds": seconds,
        "time_to_first_highest_score_minutes": seconds / 60 if seconds is not None else None,
        "timing_status": reason,
    }


def performance(paired, config):
    baseline = paired.get("baseline") or {}
    result = {"baseline_p95_seconds": baseline.get("p95_seconds"),
              "baseline_5xx_rps": baseline.get("http_5xx_rps"),
              "baseline_5xx_imputed_samples": baseline.get("http_5xx_imputed_samples"),
              "window_status": paired.get("status"),
              "window_reason": paired.get("reason") or paired.get("baseline_reason"),
              "window_seconds": paired.get("window_seconds"),
              "workload": paired.get("workload"), "namespace": paired.get("namespace"),
              "baseline_start": baseline.get("start"), "baseline_end": baseline.get("end")}
    window = paired.get("best") or {}
    for source, suffix in (("p95_seconds", "p95_seconds"), ("http_5xx_rps", "5xx_rps"),
                           ("start", "window_start"), ("end", "window_end"),
                           ("http_5xx_imputed_samples", "5xx_imputed_samples"),
                           ("p95_coverage", "p95_coverage"), ("http_5xx_coverage", "5xx_coverage")):
        result[f"best_{suffix}"] = window.get(source)
    for metric, source in (("p95_seconds", "p95_seconds"), ("5xx_rps", "http_5xx_rps")):
        before, after = baseline.get(source), window.get(source)
        delta = after - before if finite(before) and finite(after) else None
        fraction = delta / before if delta is not None and before > 0 else None
        result[f"best_{metric}_difference"] = delta
        result[f"best_{metric}_change_percent"] = 100 * fraction if fraction is not None else None
    before, after, errors = baseline.get("p95_seconds"), window.get("p95_seconds"), window.get("http_5xx_rps")
    assessable = finite(before) and before > 0 and finite(after) and finite(errors)
    result["best_holistic_pass"] = bool(after < before * (1 + config.p95_change_limit) and errors <= config.max_5xx_rps) if assessable else None
    # Covered candidates rejected by the 5xx ceiling are known failures, not
    # missing evidence. Otherwise the aggregate denominator would be biased.
    if (not paired.get('best') and paired.get('covered_windows', 0) > 0
            and finite(baseline.get('p95_seconds')) and baseline['p95_seconds'] > 0):
        result['best_holistic_pass'] = False
    return result


def build_report(grade_dir: Path, archive_dir: Path, config: ReportConfig, *, include_ungraded=False):
    files = sorted(grade_dir.glob("runs/*/grade.json"))
    if not files and not include_ungraded:
        raise ValueError(f"No per-run grades found under {grade_dir}")
    archives = {}
    for metadata_path in sorted(archive_dir.rglob('metadata.json')):
        folder = metadata_path.parent
        if folder.name in archives:
            raise ValueError(f'Duplicate archived run name: {folder.name}')
        archives[folder.name] = folder
    entries = [(path, read(path)) for path in files]
    if include_ungraded:
        graded = {grade['run'] for _, grade in entries}
        for run, folder in archives.items():
            if run in graded:
                continue
            scenario = read(folder / 'inputs/scenario.json', {})
            entries.append((None, {'run': run, 'scenario': scenario.get('name') or run,
                                  'status': 'not_graded', 'rca_jobs': [], 'remediation_jobs': []}))
    if not entries:
        raise ValueError(f'No grades or archived runs found for {archive_dir.name}')
    rows, job_rows = [], []
    for path, grade in entries:
        run = grade["run"]
        archive = archives.get(run, archive_dir / run)  # Never follow archived machine paths.
        metadata = read(archive / "metadata.json", {})
        status = read(archive / "run-status.json", {})
        code = status.get("execution_returncode", status.get("returncode"))
        completed = (metadata.get("status") == "completed" or status.get("status") == "completed") and code in (None, 0)
        if metadata.get("status") in ("failed", "interrupted") or status.get("status") in ("failed", "interrupted"):
            completed = False
        faults = [s for s in metadata.get("chaos_steps", []) if s.get("chaos") and not s.get("idle")]
        origin = stamp(faults[0].get("active_started_at")) if faults else pd.NaT
        if pd.isna(origin):
            origin = stamp((grade.get("research", {}).get("operational", {}).get("timing") or {}).get("scheduled_fault_start"))
        row = {"run": run, "scenario": grade.get("scenario") or run,
               "run_started_at": stamp(metadata.get("started_at") or status.get("started_at")),
               "archive_status": metadata.get("status") or status.get("status") or "missing",
               "run_completed": completed, "grade_status": grade.get("status"),
               "chaos_start": origin, "archive_available": (archive / "metadata.json").is_file(),
               "grade_path": str(path) if path else None, "archive_path": str(archive)}
        try:
            spans = chaos_intervals(metadata)
            row['time_scope_status'] = 'available'
        except (ValueError, TypeError, KeyError):
            spans = []
            row['time_scope_status'] = 'missing_or_invalid_chaos_boundaries'
        for kind in ("rca", "remediation"):
            jobs = grade.get(kind + "_jobs") or []
            # Counts use original exports, including ungraded / result-less jobs.
            filename = "rca_session.json" if kind == "rca" else "remediation_run.json"
            exported = read(archive / "sessions" / filename)
            if exported is not None and not isinstance(exported, list):
                raise ValueError(f"Expected session array: {archive / 'sessions' / filename}")
            if path is None and exported is not None:
                # Raw exports contain outputs, not semantic grades.
                jobs = [{k: job.get(k) for k in ('id', 'status', 'completed_at')} for job in exported]
            included_jobs = [job for job in jobs if job_scope(job, spans)['included']]
            values = job_summary(included_jobs, origin, config.score_threshold)
            count_jobs = exported if exported is not None else jobs
            values['exported_sessions'] = len(count_jobs)
            values['sessions'] = sum(job_scope(job, spans)['included'] for job in count_jobs) if spans else None
            values['excluded_sessions'] = len(count_jobs) - values['sessions'] if spans else None
            row.update({kind + "_" + k: v for k, v in values.items()})
            for job in jobs:
                scope = job_scope(job, spans)
                score = usable_score(job) if scope['included'] else None
                job_rows.append({"run": run, "scenario": row['scenario'], "kind": kind,
                                 "job_id": job.get('id'), "status": job.get('status'), "score": score,
                                 "included_in_chaos": scope["included"], "exclusion_reason": scope["reason"],
                                 "successful": score > config.score_threshold if score is not None else None,
                                 "completed_at": stamp(job.get('completed_at'))})
        # Recompute locally so report window/baseline/error thresholds actually
        # change selection; existing grades and caches are never rewritten.
        comparison = compare_windows(archive, config.window_minutes)
        paired = paired_frontend_window(archive, comparison, config.workload, config.namespace,
                                        config.max_5xx_rps, config.baseline_ignore_minutes)
        row.update(performance(paired, config))
        rows.append(row)
    all_runs = pd.DataFrame(rows).sort_values(["scenario", "run_started_at", "run"], na_position="first").reset_index(drop=True)
    if config.repeat_policy == "all_runs":
        selected = all_runs.copy()
    else:
        # Prefer the latest completed attempt; keep the latest failed/incomplete
        # attempt visible when no completed attempt exists for that scenario.
        selected = (all_runs.sort_values(["scenario", "run_completed", "run_started_at", "run"], na_position="first")
                    .groupby("scenario", sort=False, as_index=False).tail(1).sort_values("scenario").reset_index(drop=True))
    all_runs['selected'] = all_runs['run'].isin(selected['run'])
    jobs = pd.DataFrame(job_rows, columns=['run','scenario','kind','job_id','status','score','successful','completed_at','included_in_chaos','exclusion_reason'])
    jobs['selected'] = jobs['run'].isin(selected['run'])
    return all_runs, selected, jobs


def aggregate_report(selected, jobs, config):
    rows = []
    for kind in ("rca", "remediation"):
        subset = jobs[(jobs['selected']) & (jobs['kind'] == kind)]
        scored = subset['score'].dropna()
        flags = selected[kind + '_has_successful_output'].dropna()
        for label, numerator, denominator in [
            (f"Successful {kind.upper()} sessions (score > {config.score_threshold:g})", int((scored > config.score_threshold).sum()), len(scored)),
            (f"Scenarios/runs with successful {kind.upper()}", int(flags.astype(bool).sum()), len(flags)),
        ]:
            rows.append({'metric':label,'count':numerator,'evaluable':denominator,
                         'percent_of_evaluable':100*numerator/denominator if denominator else None})
    completed = selected[selected['run_completed']]
    flags = completed['best_holistic_pass'].dropna()
    rows.append({'metric':'Holistic performance within tolerance (best window)',
                 'count':int(flags.astype(bool).sum()),'evaluable':len(flags),
                 'percent_of_evaluable':100*flags.astype(bool).sum()/len(flags) if len(flags) else None})
    return pd.DataFrame(rows)
