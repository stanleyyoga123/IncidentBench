from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from .chaos import ArchivedInputError, load_archived_chaos, load_archived_scenario
from .ground_truth import DEFAULT_GROUND_TRUTH_DIR, load_ground_truth
from .judge import JudgeClient, PROMPT_VERSION, build_payload, build_penalty_payload
from .metrics import evaluate_metrics
from .penalty import (
    DEFAULT_PENALTIES_DIR,
    PenaltySet,
    apply_penalties,
    load_penalties,
    parse_penalty_judgements,
    penalty_set_for,
)
from .reports import (
    write_global_report,
    write_rubric_score_csv,
    write_run_report,
    write_summary_csv,
)
from .rubric import (
    DEFAULT_RUBRIC_PATH,
    KindRubric,
    Rubric,
    alignment_reason,
    derived_alignment,
    load_rubric,
    parse_classifications,
    score_classifications,
)


LOGGER = logging.getLogger("grader.pipeline")
DEFAULT_CONCURRENCY = 5


@dataclass(frozen=True)
class GraderConfig:
    input_path: Path = Path("results")
    output_path: Path = Path("grades")
    ground_truth_path: Path = DEFAULT_GROUND_TRUTH_DIR
    rubric_path: Path = DEFAULT_RUBRIC_PATH
    penalties_path: Path = DEFAULT_PENALTIES_DIR
    model: str = "unknown"
    judge_max_tokens: int = 8192
    concurrency: int = DEFAULT_CONCURRENCY
    window_minutes: float = 5.0
    threshold: float = 0.15
    refresh_judge: bool = False


def grade_runs(config: GraderConfig, judge: JudgeClient) -> list[dict[str, Any]]:
    if config.window_minutes <= 0:
        raise ValueError("window_minutes must be positive")
    if not 0 < config.threshold < 1:
        raise ValueError("threshold must be between zero and one")
    if config.concurrency <= 0:
        raise ValueError("concurrency must be positive")
    rubric = load_rubric(config.rubric_path)
    penalties = load_penalties(config.penalties_path)
    LOGGER.info(
        "grading started input=%s output=%s model=%s judge_max_tokens=%s concurrency=%s window_minutes=%s threshold=%s refresh_judge=%s rubric=%s rubric_hash=%s penalties=%s penalty_scenarios=%d",
        config.input_path,
        config.output_path,
        config.model,
        config.judge_max_tokens,
        config.concurrency,
        config.window_minutes,
        config.threshold,
        config.refresh_judge,
        rubric.source_path,
        rubric.source_hash,
        config.penalties_path,
        len(penalties),
    )
    ground_truth = load_ground_truth(config.ground_truth_path)
    LOGGER.debug(
        "validated ground truth directory=%s scenarios=%d",
        config.ground_truth_path,
        len(ground_truth),
    )
    metadata_files = sorted(Path(config.input_path).rglob("metadata.json"))
    LOGGER.info("discovered runs=%d", len(metadata_files))
    output = Path(config.output_path)
    (output / "runs").mkdir(parents=True, exist_ok=True)
    run_specs: list[tuple[Path, Path, str, Path]] = []
    seen_names: set[str] = set()
    for metadata_path in metadata_files:
        run_folder = metadata_path.parent
        run_name = run_folder.name
        if run_name in seen_names:
            raise ValueError(f"duplicate run folder name under input: {run_name}")
        seen_names.add(run_name)
        run_output = output / "runs" / run_name
        run_specs.append((metadata_path, run_folder, run_name, run_output))

    def process_run(spec: tuple[Path, Path, str, Path]) -> dict[str, Any]:
        metadata_path, run_folder, run_name, run_output = spec
        run_output.mkdir(parents=True, exist_ok=True)
        LOGGER.info("run started run=%s path=%s", run_name, run_folder)
        grade = _grade_run(
            run_folder,
            metadata_path,
            run_output,
            ground_truth,
            rubric,
            penalties,
            config,
            judge,
        )
        cache_path = run_output / "judge-cache.json"
        if not cache_path.exists():
            _write_cache(
                cache_path,
                {**_cache_metadata(config.model, rubric.source_hash), "entries": {}},
            )
        (run_output / "grade.json").write_text(
            json.dumps(grade, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_run_report(run_output / "report.md", grade, rubric)
        if grade["status"] == "graded":
            LOGGER.info(
                "run completed run=%s rca_jobs=%d remediation_jobs=%d",
                run_name,
                len(grade["rca_jobs"]),
                len(grade["remediation_jobs"]),
            )
        else:
            LOGGER.warning(
                "run ungraded run=%s scenario=%s reason=%s",
                run_name,
                grade.get("scenario"),
                grade.get("reason"),
            )
        return grade

    worker_count = min(config.concurrency, max(1, len(run_specs)))
    LOGGER.info("grading runs concurrently workers=%d", worker_count)
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        # executor.map preserves the sorted input order for aggregate reports.
        grades = list(executor.map(process_run, run_specs))

    rows = [row for grade in grades for row in _summary_rows(grade)]
    write_summary_csv(output / "summary.csv", rows)
    write_rubric_score_csv(
        output / "rca_rubric_score.csv", grades, rubric.kind("rca")
    )
    write_rubric_score_csv(
        output / "remediation_rubric_score.csv", grades, rubric.kind("remediation")
    )
    write_global_report(output / "report.md", grades, rubric)
    LOGGER.info(
        "grading completed runs=%d graded=%d ungraded=%d jobs=%d",
        len(grades),
        sum(item["status"] == "graded" for item in grades),
        sum(item["status"] != "graded" for item in grades),
        len(rows),
    )
    LOGGER.debug(
        "aggregate artifacts summary_csv=%s rca_rubric_score_csv=%s remediation_rubric_score_csv=%s report=%s",
        output / "summary.csv",
        output / "rca_rubric_score.csv",
        output / "remediation_rubric_score.csv",
        output / "report.md",
    )
    return grades


def _grade_run(
    run_folder: Path,
    metadata_path: Path,
    run_output: Path,
    ground_truth_entries: dict[str, dict[str, str]],
    rubric: Rubric,
    penalties: dict[str, PenaltySet],
    config: GraderConfig,
    judge: JudgeClient,
) -> dict[str, Any]:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if not isinstance(metadata, dict):
            raise ValueError("metadata root is not an object")
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return _ungraded(run_folder.name, None, f"invalid metadata.json: {exc}")
    try:
        scenario = load_archived_scenario(run_folder)
    except (ArchivedInputError, json.JSONDecodeError, OSError) as exc:
        return _ungraded(run_folder.name, None, str(exc))
    scenario_name = str(scenario.get("name"))
    LOGGER.debug("archived scenario loaded run=%s scenario=%s", run_folder.name, scenario_name)
    truth = ground_truth_entries.get(scenario_name)
    if truth is None:
        return _ungraded(
            run_folder.name,
            scenario_name,
            f"no ground truth for scenario {scenario_name!r}",
        )
    try:
        chaos = load_archived_chaos(run_folder, scenario)
    except (ArchivedInputError, yaml.YAMLError, OSError) as exc:
        return _ungraded(run_folder.name, scenario_name, str(exc))
    LOGGER.debug(
        "archived chaos loaded run=%s manifests=%d references=%s",
        run_folder.name,
        len(chaos),
        ",".join(item["reference"] for item in chaos),
    )

    cache_path = run_output / "judge-cache.json"
    cache = _load_cache(cache_path)
    cache_entries = cache.setdefault("entries", {})
    try:
        rca_jobs = _load_job_list(run_folder / "sessions" / "rca_session.json")
        remediation_jobs = _load_job_list(
            run_folder / "sessions" / "remediation_run.json"
        )
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return _ungraded(run_folder.name, scenario_name, f"invalid job export: {exc}")
    LOGGER.debug(
        "job exports loaded run=%s rca_jobs=%d remediation_jobs=%d",
        run_folder.name,
        len(rca_jobs),
        len(remediation_jobs),
    )
    penalty_set = penalty_set_for(penalties, scenario_name)
    cache.update(_cache_metadata(config.model, rubric.source_hash))
    rca_results = []
    for job in rca_jobs:
        rca_results.append(
            _grade_job(
                "rca",
                job,
                scenario_name,
                truth,
                chaos,
                rubric,
                penalty_set,
                config,
                judge,
                cache_entries,
            )
        )
        _write_cache(cache_path, cache)
    remediation_results = []
    for job in remediation_jobs:
        item = _grade_job(
            "remediation",
            job,
            scenario_name,
            truth,
            chaos,
            rubric,
            penalty_set,
            config,
            judge,
            cache_entries,
        )
        # Metric grading is independent of semantic judging. A failed model call
        # must not hide an otherwise complete before/after metric comparison.
        if job.get("status") != "succeeded" or not _has_result(job.get("result")):
            metrics = evaluate_metrics(
                run_folder,
                None,
                window_seconds=config.window_minutes * 60,
                threshold=config.threshold,
            )
            metrics["reason"] = (
                "metric comparison requires a succeeded remediation with a "
                "non-empty final result object"
            )
        else:
            metrics = evaluate_metrics(
                run_folder,
                job.get("completed_at"),
                window_seconds=config.window_minutes * 60,
                threshold=config.threshold,
            )
        item["metrics"] = metrics
        item["final_grade"] = _final_grade(item["alignment"]["verdict"], metrics["outcome"])
        LOGGER.debug(
            "remediation metric outcome run=%s job_id=%s outcome=%s final_grade=%s reason=%s",
            run_folder.name,
            job.get("id"),
            metrics["outcome"],
            item["final_grade"],
            metrics["reason"],
        )
        for metric_name, family in metrics.get("families", {}).items():
            LOGGER.debug(
                "metric family run=%s job_id=%s metric=%s assessment=%s before=%s after=%s series=%d",
                run_folder.name,
                job.get("id"),
                metric_name,
                family.get("assessment"),
                family.get("before_median"),
                family.get("after_median"),
                len(family.get("series") or []),
            )
        remediation_results.append(item)
        _write_cache(cache_path, cache)
    return {
        "schema_version": 1,
        "run": run_folder.name,
        "run_path": str(run_folder),
        "scenario": scenario_name,
        "status": "graded",
        "reason": None,
        "inputs": {
            "scenario": scenario,
            "ground_truth": truth,
            "chaos_manifests": chaos,
        },
        "configuration": {
            "prompt_version": PROMPT_VERSION,
            "model": config.model,
            "judge_max_tokens": config.judge_max_tokens,
            "concurrency": config.concurrency,
            "window_minutes": config.window_minutes,
            "threshold": config.threshold,
            "rubric_path": str(rubric.source_path),
            "rubric_hash": rubric.source_hash,
            "penalties_path": str(penalty_set.source_path) if penalty_set.source_path else None,
            "penalty_hash": penalty_set.source_hash or None,
        },
        "rca_jobs": rca_results,
        "remediation_jobs": remediation_results,
    }


def _grade_job(
    kind: str,
    job: dict[str, Any],
    scenario: str,
    truth: dict[str, str],
    chaos: list[dict[str, Any]],
    rubric: Rubric,
    penalty_set: PenaltySet,
    config: GraderConfig,
    judge: JudgeClient,
    cache_entries: dict[str, Any],
) -> dict[str, Any]:
    result = job.get("result")
    kind_rubric = rubric.kind(kind)
    base = {
        "id": job.get("id"),
        "workflow_id": job.get("workflow_id"),
        "status": job.get("status"),
        "created_at": job.get("created_at"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "result": result,
        "rubric": None,
    }
    if job.get("status") != "succeeded":
        LOGGER.debug(
            "job not evaluable kind=%s job_id=%s status=%s",
            kind,
            job.get("id"),
            job.get("status"),
        )
        base["alignment"] = {
            "verdict": "not_evaluable",
            "reason": f"job status is {job.get('status')!r}, not succeeded",
            "cached": False,
            "cache_key": None,
        }
        return base
    if not _has_result(result):
        LOGGER.debug("job result missing kind=%s job_id=%s", kind, job.get("id"))
        base["alignment"] = {
            "verdict": "not_evaluable",
            "reason": "job has no non-empty final result object",
            "cached": False,
            "cache_key": None,
        }
        return base
    payload = build_payload(
        kind=kind,
        scenario=scenario,
        ground_truth=truth,
        result=result,
    )
    key = _cache_key(kind, payload, config.model, rubric.source_hash)
    cached_entry = cache_entries.get(key)
    if not config.refresh_judge and _valid_cache_entry(cached_entry, kind_rubric):
        LOGGER.debug("judge cache hit kind=%s job_id=%s cache_key=%s", kind, job.get("id"), key)
        graded = _apply_classifications(
            base,
            kind_rubric,
            cached_entry["classifications"],
            cached=True,
            cache_key=key,
        )
    else:
        try:
            LOGGER.debug(
                "judge call started kind=%s job_id=%s cache_key=%s",
                kind,
                job.get("id"),
                key,
            )
            classifications = judge.grade(kind, payload)
        except Exception as exc:
            LOGGER.error(
                "judge call failed kind=%s job_id=%s cache_key=%s error_type=%s detail=%s",
                kind,
                job.get("id"),
                key,
                type(exc).__name__,
                str(exc) if isinstance(exc, ValueError) else "suppressed",
            )
            base["alignment"] = {
                "verdict": "not_evaluable",
                "reason": f"judge failed: {type(exc).__name__}: {exc}",
                "cached": False,
                "cache_key": key,
            }
            return base
        cache_entries[key] = {"classifications": classifications}
        graded = _apply_classifications(
            base,
            kind_rubric,
            classifications,
            cached=False,
            cache_key=key,
        )
        LOGGER.debug(
            "judge call completed kind=%s job_id=%s cache_key=%s verdict=%s overall_score=%s classes=%s",
            kind,
            job.get("id"),
            key,
            graded["alignment"]["verdict"],
            graded["rubric"]["overall_score"],
            ",".join(
                f"{criterion_id}={item['class']}"
                for criterion_id, item in graded["rubric"]["criteria"].items()
            ),
        )
    if kind == "remediation":
        return _attach_penalties(
            graded,
            payload,
            chaos,
            penalty_set,
            config,
            judge,
            cache_entries,
        )
    return graded


def _apply_classifications(
    base: dict[str, Any],
    kind_rubric: KindRubric,
    classifications: dict[str, dict[str, str]],
    *,
    cached: bool,
    cache_key: str,
) -> dict[str, Any]:
    scored = score_classifications(kind_rubric, classifications)
    base["rubric"] = {
        "overall_score": scored["overall_score"],
        "criteria": scored["criteria"],
    }
    base["alignment"] = {
        "verdict": derived_alignment(scored),
        "reason": alignment_reason(scored),
        "cached": cached,
        "cache_key": cache_key,
    }
    return base


def _attach_penalties(
    graded: dict[str, Any],
    payload: dict[str, Any],
    chaos_manifests: list[dict[str, Any]],
    penalty_set: PenaltySet,
    config: GraderConfig,
    judge: JudgeClient,
    cache_entries: dict[str, Any],
) -> dict[str, Any]:
    scored = graded.get("rubric") or {}
    rubric_score = scored.get("overall_score")
    if not penalty_set.items:
        scored["rubric_score"] = rubric_score
        scored["penalty_total"] = 0.0
        scored["penalties"] = []
        graded["rubric"] = scored
        return graded
    penalty_payload = build_penalty_payload(
        payload, penalty_set, chaos_manifests
    )
    key = _cache_key(
        "remediation_penalty",
        penalty_payload,
        config.model,
        penalty_set.source_hash,
    )
    cached_entry = cache_entries.get(key)
    if not config.refresh_judge and _valid_penalty_cache_entry(
        cached_entry, penalty_set
    ):
        LOGGER.debug(
            "penalty cache hit job_id=%s cache_key=%s",
            graded.get("id"),
            key,
        )
        judgements = cached_entry["judgements"]
        cached = True
    else:
        try:
            LOGGER.debug(
                "penalty judge call started job_id=%s cache_key=%s count=%s",
                graded.get("id"),
                key,
                len(penalty_set.items),
            )
            judgements = judge.grade_penalties(penalty_set, penalty_payload)
        except Exception as exc:
            LOGGER.error(
                "penalty judge call failed job_id=%s cache_key=%s error_type=%s detail=%s",
                graded.get("id"),
                key,
                type(exc).__name__,
                str(exc) if isinstance(exc, ValueError) else "suppressed",
            )
            graded["alignment"] = {
                "verdict": "not_evaluable",
                "reason": f"judge failed: {type(exc).__name__}: {exc}",
                "cached": False,
                "cache_key": key,
            }
            scored["rubric_score"] = rubric_score
            scored["penalty_total"] = None
            scored["penalties"] = None
            graded["rubric"] = scored
            return graded
        cache_entries[key] = {"judgements": judgements}
        cached = False
    applied = apply_penalties(float(rubric_score), penalty_set, judgements)
    scored["rubric_score"] = applied["rubric_score"]
    scored["penalty_total"] = applied["penalty_total"]
    scored["penalties"] = applied["penalties"]
    scored["overall_score"] = applied["overall_score"]
    scored["penalty_cached"] = cached
    scored["penalty_cache_key"] = key
    graded["rubric"] = scored
    LOGGER.debug(
        "penalty judge call completed job_id=%s cache_key=%s penalty_total=%s overall_score=%s applied=%s",
        graded.get("id"),
        key,
        applied["penalty_total"],
        applied["overall_score"],
        ",".join(
            str(item["index"])
            for item in applied["penalties"]
            if item["applied"]
        ),
    )
    return graded


def _has_result(result: Any) -> bool:
    return isinstance(result, dict) and bool(result)


def _valid_cache_entry(value: Any, kind_rubric: KindRubric) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        parse_classifications(kind_rubric, value.get("classifications"))
    except ValueError:
        return False
    return True


def _valid_penalty_cache_entry(value: Any, penalty_set: PenaltySet) -> bool:
    if not isinstance(value, dict):
        return False
    try:
        parse_penalty_judgements(penalty_set, value.get("judgements"))
    except ValueError:
        return False
    return True


def _load_job_list(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload is None:
        return []
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise ValueError(f"session export must be an array or object: {path}")
    jobs = [item for item in payload if isinstance(item, dict)]
    return sorted(
        jobs,
        key=lambda item: (
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )


def _cache_metadata(model: str, rubric_hash: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "rubric_hash": rubric_hash,
    }


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"entries": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), dict):
        return {"entries": {}}
    return payload


def _write_cache(path: Path, cache: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _cache_key(
    kind: str, payload: dict[str, Any], model: str, rubric_hash: str
) -> str:
    material = {
        "prompt_version": PROMPT_VERSION,
        "rubric_hash": rubric_hash,
        "model": model,
        "kind": kind,
        "payload": payload,
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _final_grade(alignment: str, metric_outcome_value: str) -> str:
    if alignment == "not_evaluable" or metric_outcome_value == "not_evaluable":
        return "not_evaluable"
    return "good" if alignment == "aligned" and metric_outcome_value == "good" else "not_good"


def _ungraded(run: str, scenario: str | None, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "run": run,
        "scenario": scenario,
        "status": "ungraded",
        "reason": reason,
        "inputs": {},
        "configuration": {},
        "rca_jobs": [],
        "remediation_jobs": [],
    }


def _summary_rows(grade: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for kind, jobs in (
        ("rca", grade.get("rca_jobs") or []),
        ("remediation", grade.get("remediation_jobs") or []),
    ):
        for job in jobs:
            rows.append(
                {
                    "run": grade["run"],
                    "scenario": grade.get("scenario"),
                    "kind": kind,
                    "job_id": job.get("id"),
                    "workflow_id": job.get("workflow_id"),
                    "status": job.get("status"),
                    "alignment": (job.get("alignment") or {}).get("verdict"),
                    "overall_score": (job.get("rubric") or {}).get("overall_score"),
                    "metric_outcome": (job.get("metrics") or {}).get("outcome"),
                    "final_grade": job.get("final_grade"),
                    "reason": _summary_reason(kind, job),
                }
            )
    return rows


def _summary_reason(kind: str, job: dict[str, Any]) -> str | None:
    job_alignment_reason = (job.get("alignment") or {}).get("reason")
    if kind != "remediation":
        return job_alignment_reason
    metric_reason = (job.get("metrics") or {}).get("reason")
    parts = [str(value) for value in (job_alignment_reason, metric_reason) if value]
    return "; metrics: ".join(parts) if parts else None
