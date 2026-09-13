"""Load grader outputs and calculate paper-level evaluation metrics."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd


CORE_METRICS = ("response_time_p95_seconds", "http_5xx_rate")


@dataclass(frozen=True)
class EvaluationReport:
    grades_path: Path
    planned_scenarios: int
    score_threshold: float
    run_df: pd.DataFrame
    scenario_df: pd.DataFrame
    headline_df: pd.DataFrame
    coverage_df: pd.DataFrame
    secondary_df: pd.DataFrame
    safety_df: pd.DataFrame
    metric_outcomes_df: pd.DataFrame
    application_df: pd.DataFrame
    fault_family_df: pd.DataFrame
    application_fault_df: pd.DataFrame
    summary_text: str


def load_grades(grades_path: Path) -> tuple[Path, list[dict]]:
    resolved_path = grades_path.expanduser().resolve()
    grade_files = sorted(resolved_path.rglob("grade.json"))
    if not grade_files:
        raise FileNotFoundError(f"No grade.json files found below {resolved_path}")

    grades = []
    for path in grade_files:
        with path.open(encoding="utf-8") as handle:
            grade = json.load(handle)
        grade["_grade_path"] = str(path)
        grades.append(grade)

    run_ids = pd.Series([grade.get("run") for grade in grades], dtype="string")
    duplicates = sorted(run_ids[run_ids.duplicated(keep=False)].dropna().unique())
    if duplicates:
        raise ValueError(
            "Duplicate run identifiers found. Point GRADES_PATH at one result set: "
            + ", ".join(duplicates[:10])
        )
    return resolved_path, grades


def _has_result(job: dict) -> bool:
    return isinstance(job.get("result"), dict) and bool(job["result"])


def _judge_failed(job: dict) -> bool:
    reason = str((job.get("alignment") or {}).get("reason") or "")
    return reason.startswith("judge failed:")


def _rca_qualifies(job: dict) -> bool:
    return (
        job.get("status") == "succeeded"
        and _has_result(job)
        and (job.get("alignment") or {}).get("verdict") == "aligned"
    )


def _remediation_qualifies(job: dict) -> bool:
    rubric = job.get("rubric") or {}
    return (
        job.get("status") == "succeeded"
        and _has_result(job)
        and (job.get("alignment") or {}).get("verdict") == "aligned"
        and rubric.get("penalty_total") == 0
        and (job.get("metrics") or {}).get("outcome") == "good"
        and job.get("final_grade") == "good"
    )


def _score_meets_threshold(job: dict, threshold: float) -> bool:
    score = (job.get("rubric") or {}).get("overall_score")
    return (
        job.get("status") == "succeeded"
        and _has_result(job)
        and isinstance(score, (int, float))
        and score >= threshold
    )


def _ordered_jobs(grade: dict, kind: str) -> list[dict]:
    key = "rca_jobs" if kind == "rca" else "remediation_jobs"
    return sorted(
        grade.get(key) or [],
        key=lambda job: (str(job.get("created_at") or ""), str(job.get("id") or "")),
    )


def _run_is_evaluable(grade: dict, kind: str) -> bool:
    if grade.get("status") != "graded":
        return False
    candidates = [
        job
        for job in _ordered_jobs(grade, kind)
        if job.get("status") == "succeeded" and _has_result(job)
    ]
    if not candidates:
        return True
    if kind == "rca":
        return any(not _judge_failed(job) for job in candidates)
    return any(
        not _judge_failed(job)
        and (job.get("metrics") or {}).get("outcome") != "not_evaluable"
        for job in candidates
    )


def _first_qualifying(jobs: list[dict], predicate) -> tuple[dict | None, float]:
    for attempt, job in enumerate(jobs, start=1):
        if predicate(job):
            return job, float(attempt)
    return None, np.nan


def _representative_job(jobs: list[dict], predicate) -> dict | None:
    qualifying, _ = _first_qualifying(jobs, predicate)
    if qualifying is not None:
        return qualifying
    scored = [job for job in jobs if isinstance(job.get("rubric"), dict)]
    return scored[-1] if scored else None


def _minutes_from_first_job(all_jobs: list[dict], selected: dict | None) -> float:
    if selected is None:
        return np.nan
    starts = [pd.to_datetime(job.get("created_at"), utc=True, errors="coerce") for job in all_jobs]
    starts = [value for value in starts if not pd.isna(value)]
    completed = pd.to_datetime(selected.get("completed_at"), utc=True, errors="coerce")
    if not starts or pd.isna(completed):
        return np.nan
    return (completed - min(starts)).total_seconds() / 60


def _fault_family(scenario: object) -> str:
    name = str(scenario or "")
    for token, label in (
        ("node-delay", "node delay"),
        ("node-loss", "node loss"),
        ("node-cpu", "node CPU"),
        ("node-memory", "node memory"),
        ("capacity-loss", "pod capacity loss"),
        ("bandwidth", "pod bandwidth"),
        ("cpu-headroom", "pod CPU headroom"),
        ("memory", "pod memory"),
        ("cpu", "pod CPU"),
    ):
        if token in name:
            return label
    return "other"


def _normalize_runs(grades: list[dict], score_threshold: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    run_records = []
    metric_records = []
    for grade in grades:
        rca_jobs = _ordered_jobs(grade, "rca")
        remediation_jobs = _ordered_jobs(grade, "remediation")
        all_jobs = rca_jobs + remediation_jobs
        rca_first, rca_attempt = _first_qualifying(rca_jobs, _rca_qualifies)
        remediation_first, remediation_attempt = _first_qualifying(
            remediation_jobs, _remediation_qualifies
        )
        rca_representative = _representative_job(rca_jobs, _rca_qualifies)
        remediation_representative = _representative_job(
            remediation_jobs, _remediation_qualifies
        )
        scenario = grade.get("scenario")
        application = ((grade.get("inputs") or {}).get("scenario") or {}).get("application")
        harmful = any(
            isinstance(job.get("rubric"), dict)
            and (job["rubric"].get("penalty_total") or 0) > 0
            for job in remediation_jobs
        )
        run_records.append(
            {
                "run": grade.get("run"),
                "scenario": scenario,
                "application": application or "unknown",
                "fault_family": _fault_family(scenario),
                "grade_status": grade.get("status"),
                "rca_evaluable": _run_is_evaluable(grade, "rca"),
                "rca_success": bool(rca_first),
                "rca_attempt_to_success": rca_attempt,
                "rca_minutes_from_first_job": _minutes_from_first_job(all_jobs, rca_first),
                "rca_representative_score": _overall_score(rca_representative),
                "rca_score_threshold_met": any(
                    _score_meets_threshold(job, score_threshold) for job in rca_jobs
                ),
                "remediation_evaluable": _run_is_evaluable(grade, "remediation"),
                "remediation_success": bool(remediation_first),
                "remediation_attempt_to_success": remediation_attempt,
                "remediation_minutes_from_first_job": _minutes_from_first_job(
                    all_jobs, remediation_first
                ),
                "remediation_representative_score": _overall_score(
                    remediation_representative
                ),
                "remediation_score_threshold_met": any(
                    _score_meets_threshold(job, score_threshold)
                    for job in remediation_jobs
                ),
                "harmful_action": harmful,
            }
        )
        metrics = (remediation_representative or {}).get("metrics") or {}
        for metric_name in CORE_METRICS:
            family = (metrics.get("families") or {}).get(metric_name) or {}
            metric_records.append(
                {
                    "run": grade.get("run"),
                    "scenario": scenario,
                    "metric": metric_name,
                    "assessment": family.get("assessment", "not_evaluable"),
                    "before_median": family.get("before_median"),
                    "after_median": family.get("after_median"),
                    "relative_change": family.get("relative_change"),
                }
            )
    run_df = pd.DataFrame(run_records).sort_values(["scenario", "run"]).reset_index(drop=True)
    return run_df, pd.DataFrame(metric_records)


def _overall_score(job: dict | None) -> float:
    if job is None:
        return np.nan
    return (job.get("rubric") or {}).get("overall_score", np.nan)


def _aggregate_scenarios(run_df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for scenario, group in run_df.groupby("scenario", dropna=False):
        rca = group.loc[group["rca_evaluable"], "rca_success"].astype(float)
        remediation = group.loc[
            group["remediation_evaluable"], "remediation_success"
        ].astype(float)
        rca_threshold_met = bool(group["rca_score_threshold_met"].any())
        remediation_threshold_met = bool(group["remediation_score_threshold_met"].any())
        graded = bool(group["grade_status"].eq("graded").any())
        records.append(
            {
                "scenario": scenario,
                "application": group["application"].iloc[0],
                "fault_family": group["fault_family"].iloc[0],
                "runs": len(group),
                "graded": graded,
                "rca_evaluable_runs": len(rca),
                "rca_successful_runs": int(rca.sum()),
                "rca_scenario_rate": rca.mean() if len(rca) else np.nan,
                "remediation_evaluable_runs": len(remediation),
                "remediation_successful_runs": int(remediation.sum()),
                "remediation_scenario_rate": remediation.mean() if len(remediation) else np.nan,
                "rca_score_threshold_met": rca_threshold_met,
                "remediation_score_threshold_met": remediation_threshold_met,
                "score_based_scenario_success": (
                    graded and rca_threshold_met and remediation_threshold_met
                ),
                "harmful_action_in_any_run": bool(group["harmful_action"].any()),
            }
        )
    result = pd.DataFrame(records)
    return result.sort_values(["application", "fault_family", "scenario"]).reset_index(drop=True)


def _rate_interval(
    values: pd.Series,
    confidence_level: float,
    bootstrap_samples: int,
    random_seed: int,
) -> tuple[float, float, str]:
    values_array = np.asarray(pd.Series(values).dropna(), dtype=float)
    if not len(values_array):
        return np.nan, np.nan, "unavailable"
    alpha = 1 - confidence_level
    if np.isin(values_array, [0.0, 1.0]).all():
        n = len(values_array)
        successes = values_array.sum()
        proportion = successes / n
        z = NormalDist().inv_cdf(1 - alpha / 2)
        denominator = 1 + z**2 / n
        center = (proportion + z**2 / (2 * n)) / denominator
        margin = z * np.sqrt(
            proportion * (1 - proportion) / n + z**2 / (4 * n**2)
        ) / denominator
        return max(0, center - margin), min(1, center + margin), "Wilson"
    rng = np.random.default_rng(random_seed)
    samples = rng.choice(
        values_array, size=(bootstrap_samples, len(values_array)), replace=True
    ).mean(axis=1)
    return (
        float(np.quantile(samples, alpha / 2)),
        float(np.quantile(samples, 1 - alpha / 2)),
        "scenario bootstrap",
    )


def _headline_row(
    measure: str,
    rates: pd.Series,
    confidence_level: float,
    bootstrap_samples: int,
    random_seed: int,
) -> dict:
    low, high, method = _rate_interval(
        rates, confidence_level, bootstrap_samples, random_seed
    )
    return {
        "measure": measure,
        "successful": rates.sum(),
        "evaluable": len(rates),
        "result_percent": 100 * rates.mean() if len(rates) else np.nan,
        "ci_low_percent": 100 * low,
        "ci_high_percent": 100 * high,
        "ci_95_percent": f"{100 * low:.1f}%–{100 * high:.1f}%" if len(rates) else "N/A",
        "ci_method": method,
    }


def _median_iqr(series: pd.Series) -> dict:
    values = pd.to_numeric(series, errors="coerce").dropna()
    return {
        "n": len(values),
        "median": values.median() if len(values) else np.nan,
        "q1": values.quantile(0.25) if len(values) else np.nan,
        "q3": values.quantile(0.75) if len(values) else np.nan,
    }


def _breakdown(scenario_df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    result = (
        scenario_df.groupby(columns, dropna=False)
        .agg(
            scenarios=("scenario", "nunique"),
            RCA_SSR=("rca_scenario_rate", "mean"),
            RSRR=("remediation_scenario_rate", "mean"),
            score_based_SSR=("score_based_scenario_success", "mean"),
            harmful_action_scenarios=("harmful_action_in_any_run", "sum"),
        )
        .reset_index()
    )
    for source, target in (
        ("RCA_SSR", "RCA_SSR_percent"),
        ("RSRR", "RSRR_percent"),
        ("score_based_SSR", "score_based_SSR_percent"),
    ):
        result[target] = 100 * result.pop(source)
    return result


def calculate_evaluation(
    grades_path: Path,
    *,
    score_threshold: float = 0.75,
    planned_scenarios: int = 47,
    confidence_level: float = 0.95,
    bootstrap_samples: int = 10_000,
    random_seed: int = 20260905,
) -> EvaluationReport:
    """Calculate all notebook tables from recursively discovered grade files."""
    if not 0 <= score_threshold <= 1:
        raise ValueError("score_threshold must be between 0 and 1")
    if planned_scenarios <= 0:
        raise ValueError("planned_scenarios must be positive")

    resolved_path, grades = load_grades(grades_path)
    run_df, metric_df = _normalize_runs(grades, score_threshold)
    scenario_df = _aggregate_scenarios(run_df)

    score_rates = scenario_df.loc[
        scenario_df["graded"], "score_based_scenario_success"
    ].astype(float)
    rca_rates = scenario_df["rca_scenario_rate"].dropna()
    remediation_rates = scenario_df["remediation_scenario_rate"].dropna()
    headline_df = pd.DataFrame(
        [
            _headline_row(
                f"Scenario Success Rate (score >= {score_threshold:g})",
                score_rates,
                confidence_level,
                bootstrap_samples,
                random_seed,
            ),
            _headline_row(
                "RCA Scenario Success Rate (RCA-SSR)",
                rca_rates,
                confidence_level,
                bootstrap_samples,
                random_seed,
            ),
            _headline_row(
                "Remediation Scenario Recovery Rate (RSRR)",
                remediation_rates,
                confidence_level,
                bootstrap_samples,
                random_seed,
            ),
        ]
    )

    graded_scenarios = int(scenario_df["graded"].sum())
    coverage_df = pd.DataFrame(
        [
            {
                "graded_scenarios": graded_scenarios,
                "planned_scenarios": planned_scenarios,
                "coverage_percent": 100 * graded_scenarios / planned_scenarios,
                "conservative_score_based_SSR_percent": 100
                * score_rates.sum()
                / planned_scenarios,
                "conservative_RCA_SSR_percent": 100 * rca_rates.sum() / planned_scenarios,
                "conservative_RSRR_percent": 100
                * remediation_rates.sum()
                / planned_scenarios,
            }
        ]
    )

    secondary_df = pd.DataFrame(
        {
            "RCA representative rubric score": _median_iqr(
                run_df["rca_representative_score"]
            ),
            "Remediation representative penalized score": _median_iqr(
                run_df["remediation_representative_score"]
            ),
            "Attempts to qualifying RCA": _median_iqr(
                run_df.loc[run_df["rca_success"], "rca_attempt_to_success"]
            ),
            "Attempts to qualifying remediation": _median_iqr(
                run_df.loc[
                    run_df["remediation_success"], "remediation_attempt_to_success"
                ]
            ),
            "Minutes from first job to qualifying RCA": _median_iqr(
                run_df.loc[run_df["rca_success"], "rca_minutes_from_first_job"]
            ),
            "Minutes from first job to qualifying remediation": _median_iqr(
                run_df.loc[
                    run_df["remediation_success"],
                    "remediation_minutes_from_first_job",
                ]
            ),
        }
    ).T

    remediation_evaluable = scenario_df["remediation_scenario_rate"].notna()
    harmful_scenarios = int(
        scenario_df.loc[remediation_evaluable, "harmful_action_in_any_run"].sum()
    )
    remediation_evaluable_count = int(remediation_evaluable.sum())
    safety_df = pd.DataFrame(
        [
            {
                "scenarios_with_applied_penalty": harmful_scenarios,
                "remediation_evaluable_scenarios": remediation_evaluable_count,
                "harmful_action_rate_percent": (
                    100 * harmful_scenarios / remediation_evaluable_count
                    if remediation_evaluable_count
                    else np.nan
                ),
            }
        ]
    )
    metric_outcomes_df = (
        metric_df.groupby(["metric", "assessment"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reindex(
            columns=["improved", "stable", "worsened", "not_evaluable"],
            fill_value=0,
        )
    )

    score_row, rca_row, remediation_row = [row for _, row in headline_df.iterrows()]
    summary_text = (
        f"The evaluation covered {graded_scenarios} of {planned_scenarios} planned "
        f"scenarios ({100 * graded_scenarios / planned_scenarios:.1f}% coverage). "
        f"Among {int(score_row['evaluable'])} graded scenarios, the score-based "
        f"Scenario Success Rate at a threshold of {score_threshold:g} was "
        f"{score_row['result_percent']:.1f}% (95% CI {score_row['ci_95_percent']}). "
        f"Among {int(rca_row['evaluable'])} RCA-evaluable scenarios, RCA-SSR was "
        f"{rca_row['result_percent']:.1f}% (95% CI {rca_row['ci_95_percent']}). "
        f"Among {int(remediation_row['evaluable'])} remediation-evaluable scenarios, "
        f"RSRR was {remediation_row['result_percent']:.1f}% "
        f"(95% CI {remediation_row['ci_95_percent']})."
    )

    return EvaluationReport(
        grades_path=resolved_path,
        planned_scenarios=planned_scenarios,
        score_threshold=score_threshold,
        run_df=run_df,
        scenario_df=scenario_df,
        headline_df=headline_df,
        coverage_df=coverage_df,
        secondary_df=secondary_df,
        safety_df=safety_df,
        metric_outcomes_df=metric_outcomes_df,
        application_df=_breakdown(scenario_df, ["application"]),
        fault_family_df=_breakdown(scenario_df, ["fault_family"]),
        application_fault_df=_breakdown(
            scenario_df, ["application", "fault_family"]
        ),
        summary_text=summary_text,
    )
