#!/usr/bin/env python3
"""Generate a scenario-level Markdown summary from evaluation results and grades."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist
from typing import Iterable


DATASETS = {
    "TeaStore": "teastore-1",
    "Online Boutique": "online-boutique-1",
    "Sock Shop": "sock-shop-1",
}
RCA_DIMENSIONS = (
    "root_cause_correctness",
    "causal_reasoning_quality",
    "evidence_grounding",
    "localization_accuracy",
    "diagnostic_completeness",
)
REMEDIATION_DIMENSIONS = (
    "remediation_correctness",
    "technical_feasibility",
    "risk_and_safety",
    "evidence_alignment",
    "remediation_completeness",
    "penalty_total",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate summary.md from one grader output directory."
    )
    parser.add_argument(
        "input",
        nargs="?",
        type=Path,
        default=Path("grades/combined"),
        help="Grader output directory containing summary.csv and runs/*/grade.json (default: grades/combined)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Grader root used to resolve relative paths (default: script directory)",
    )
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("../Runner/results"),
        help="Raw results directory used for execution status (default: ../Runner/results)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output Markdown path (default: <input>/summary.md)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Score threshold for RCA-SSR and Remediation-SSR (default: 0.8)",
    )
    return parser.parse_args()


def read_csv(path: Path, applications: dict[str, str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["application"] = applications.get(row.get("run", ""), "Unknown")
    return rows


def application_label(reference: object) -> str:
    normalized = str(reference or "").strip().lower()
    if normalized == "teastore":
        return "TeaStore"
    if normalized == "online-boutique":
        return "Online Boutique"
    if normalized == "sock-shop":
        return "Sock Shop"
    return str(reference or "Unknown")


def grade_applications(grades: Path) -> dict[str, str]:
    applications: dict[str, str] = {}
    for path in sorted(grades.rglob("grade.json")):
        grade = json.loads(path.read_text(encoding="utf-8"))
        reference = ((grade.get("inputs") or {}).get("scenario") or {}).get("application")
        applications[str(grade.get("run") or path.parent.name)] = application_label(reference)
    if not applications:
        raise FileNotFoundError(f"no grade.json files found below {grades}")
    return applications


def number(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def quantile(values: Iterable[float], probability: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def mean(values: Iterable[float]) -> float | None:
    items = list(values)
    return statistics.fmean(items) if items else None


def wilson(successes: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    z = NormalDist().inv_cdf(1 - (1 - confidence) / 2)
    proportion = successes / total
    denominator = 1 + z**2 / total
    center = (proportion + z**2 / (2 * total)) / denominator
    margin = z * math.sqrt(
        proportion * (1 - proportion) / total + z**2 / (4 * total**2)
    ) / denominator
    return max(0, center - margin), min(1, center + margin)


def fault_family(name: str) -> str:
    for token, label in (
        ("node-delay", "Node delay"),
        ("node-loss", "Node loss"),
        ("node-cpu", "Node CPU"),
        ("node-memory", "Node memory"),
        ("capacity-loss", "Pod capacity loss"),
        ("bandwidth", "Pod bandwidth"),
        ("cpu-headroom", "Pod CPU headroom"),
        ("memory", "Pod memory"),
        ("cpu", "Pod CPU"),
    ):
        if token in name:
            return label
    return "Other"


def failure_detail(metadata: dict) -> tuple[str, str]:
    failed = [phase for phase in metadata.get("phases", []) if phase.get("status") != "completed"]
    if not failed:
        return "", ""
    phase = failed[0]
    name = str(phase.get("name") or "unknown")
    details = phase.get("details") or {}
    if name == "baseline":
        health = details.get("health") or {}
        observed = 100 * float(health.get("failure_ratio") or 0)
        maximum = 100 * float(health.get("maximum_failure_ratio") or 0)
        return name, f"baseline failure ratio {observed:.2f}% (limit {maximum:.2f}%)"
    if name == "chaos":
        return name, str((details.get("step") or {}).get("error") or "chaos phase failed")
    command = details.get("command") or {}
    errors = command.get("errors") or []
    if errors:
        return name, "; ".join(map(str, errors))
    return name, str(command.get("failed_command") or f"{name} failed")


def escape(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        value = f"{value:.4f}"
    return str(value).replace("|", "\\|").replace("\n", " ")


def markdown_table(headers: list[str], rows: Iterable[Iterable[object]]) -> str:
    materialized = [[escape(value) for value in row] for row in rows]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---:" if index else "---" for index in range(len(headers))) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in materialized)
    return "\n".join(lines)


def metric_formulas(threshold: float) -> list[tuple[str, str]]:
    return [
        ("Status count", "Σ I(execution_status = status)"),
        ("Discovered runs", "completed + failed + missing_metadata + other statuses"),
        ("Completion rate", "100 × completed / discovered runs"),
        ("Baseline failure ratio", "100 × failed requests / total requests"),
        ("Best RCA score B_R(r)", "max overall score among succeeded scored RCA jobs in run r"),
        ("Best remediation score B_M(r)", "max overall score among succeeded scored remediation jobs in run r"),
        ("RCA success S_R(r)", f"I(B_R(r) ≥ {threshold:g})"),
        ("Remediation success S_M(r)", f"I(B_M(r) ≥ {threshold:g})"),
        ("Joint success S_J(r)", "S_R(r) × S_M(r)"),
        ("RCA-SSR", "100 × Σ S_R(r) / completed runs"),
        ("Remediation-SSR", "100 × Σ S_M(r) / completed runs"),
        ("Joint score SSR", "100 × Σ S_J(r) / completed runs"),
        ("Aligned RCA rate", "100 × runs with any succeeded aligned RCA / completed runs"),
        ("Metric recovery rate", "100 × runs with any succeeded metric_outcome=good remediation / completed runs"),
        ("Strict recovery rate", "100 × runs with any succeeded final_grade=good remediation / completed runs"),
        ("Wilson 95% CI", "center ± margin, where center=(p+z²/2n)/(1+z²/n), margin=z√(p(1-p)/n+z²/4n²)/(1+z²/n), z=1.959964"),
        ("RCA overall score", "0.30RC + 0.25CR + 0.20EG + 0.15LA + 0.10DC"),
        ("Remediation rubric score", "0.30RC + 0.20TF + 0.20RS + 0.15EA + 0.15CM"),
        ("Penalized remediation score", "max(0, remediation rubric score − penalty_total)"),
        ("Mean", "Σxᵢ / n"),
        ("Median", "middle ordered value; mean of two middle values when n is even"),
        ("Sample standard deviation", "√(Σ(xᵢ−mean)²/(n−1))"),
        ("Q1 / Q3", "linear-interpolated 25th / 75th percentile"),
        ("Relative metric change", "(after-window median − before-window median) / before-window median"),
        ("Metric improved / worsened", "relative change ≤ −15% / ≥ +15%; otherwise stable"),
        ("Good metric outcome", "at least one core metric improved and no core metric worsened"),
        ("Penalized percent", "100 × succeeded remediations with penalty_total>0 / succeeded remediations"),
        ("Subgroup SSR", "same SSR numerator and denominator restricted to application or fault-family subgroup"),
    ]


def load_data(results: Path, grades: Path) -> tuple[list[dict], list[dict], list[dict], list[dict]]:
    executions: list[dict] = []
    applications = grade_applications(grades)
    for application, dataset in DATASETS.items():
        result_root = results / dataset
        if not result_root.is_dir():
            raise FileNotFoundError(f"missing raw result directory: {result_root}")
        for run_dir in sorted(path for path in result_root.iterdir() if path.is_dir()):
            metadata_path = run_dir / "metadata.json"
            if not metadata_path.exists():
                executions.append({
                    "application": application,
                    "run": run_dir.name,
                    "scenario": "",
                    "status": "missing_metadata",
                    "failed_phase": "unknown",
                    "failure_detail": "metadata.json was not produced",
                })
                continue
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            phase, detail = failure_detail(metadata)
            executions.append({
                "application": application,
                "run": run_dir.name,
                "scenario": (metadata.get("scenario") or {}).get("name") or "",
                "status": metadata.get("status") or "unknown",
                "failed_phase": phase,
                "failure_detail": detail,
            })
    summaries = read_csv(grades / "summary.csv", applications)
    rca_rows = read_csv(grades / "rca_rubric_score.csv", applications)
    remediation_rows = read_csv(grades / "remediation_rubric_score.csv", applications)
    return executions, summaries, rca_rows, remediation_rows


def build_runs(executions: list[dict], summaries: list[dict], threshold: float) -> list[dict]:
    completed = {row["run"] for row in executions if row["status"] == "completed"}
    by_run: dict[str, list[dict]] = defaultdict(list)
    for row in summaries:
        if row["run"] in completed:
            by_run[row["run"]].append(row)
    records = []
    for execution in executions:
        if execution["status"] != "completed":
            continue
        jobs = by_run[execution["run"]]
        rca = [row for row in jobs if row["kind"] == "rca"]
        remediation = [row for row in jobs if row["kind"] == "remediation"]
        succeeded_rca = [row for row in rca if row["status"] == "succeeded"]
        succeeded_remediation = [row for row in remediation if row["status"] == "succeeded"]
        rca_scores = [value for row in succeeded_rca if (value := number(row["overall_score"])) is not None]
        remediation_scores = [
            value for row in succeeded_remediation if (value := number(row["overall_score"])) is not None
        ]
        scenario = execution["scenario"] or (jobs[0]["scenario"] if jobs else "")
        best_rca = max(rca_scores) if rca_scores else None
        best_remediation = max(remediation_scores) if remediation_scores else None
        rca_success = best_rca is not None and best_rca >= threshold
        remediation_success = best_remediation is not None and best_remediation >= threshold
        records.append({
            "application": execution["application"],
            "run": execution["run"],
            "scenario": scenario,
            "fault_family": fault_family(scenario),
            "rca_jobs": len(rca),
            "remediation_jobs": len(remediation),
            "best_rca_score": best_rca,
            "best_remediation_score": best_remediation,
            "rca_success": rca_success,
            "remediation_success": remediation_success,
            "joint_success": rca_success and remediation_success,
            "aligned_rca": any(row["alignment"] == "aligned" for row in succeeded_rca),
            "metric_recovery": any(row["metric_outcome"] == "good" for row in succeeded_remediation),
            "strict_recovery": any(row["final_grade"] == "good" for row in succeeded_remediation),
        })
    return records


def rate_row(application: str, runs: list[dict]) -> list[object]:
    total = len(runs)
    values = []
    for key in ("rca_success", "remediation_success", "joint_success", "aligned_rca", "strict_recovery"):
        successes = sum(bool(row[key]) for row in runs)
        low, high = wilson(successes, total)
        values.extend((successes, f"{100*successes/total:.1f}%", f"{100*low:.1f}–{100*high:.1f}%"))
    return [application, total, *values]


def score_distribution(rows: list[dict], completed: set[str]) -> list[list[object]]:
    output = []
    for application in DATASETS:
        for kind in ("rca", "remediation"):
            values = [
                score for row in rows
                if row["application"] == application and row["run"] in completed
                and row["kind"] == kind and row["status"] == "succeeded"
                and (score := number(row["overall_score"])) is not None
            ]
            output.append([
                application, kind, len(values), mean(values), statistics.median(values) if values else None,
                statistics.stdev(values) if len(values) > 1 else None, min(values) if values else None,
                quantile(values, 0.25), quantile(values, 0.75), max(values) if values else None,
            ])
    return output


def render(results: Path, grades: Path, threshold: float) -> str:
    executions, summaries_all, rca_all, remediation_all = load_data(results, grades)
    runs = build_runs(executions, summaries_all, threshold)
    completed = {row["run"] for row in runs}
    summaries = [row for row in summaries_all if row["run"] in completed]
    rca_rows = [row for row in rca_all if row["run"] in completed]
    remediation_rows = [row for row in remediation_all if row["run"] in completed]
    sections = [
        "# Evaluation metrics summary",
        "",
        f"Score threshold: **{threshold:g}**. Grading metrics use only execution-completed runs; failed and missing-metadata runs are reported separately.",
        "",
        "## Formula reference",
        "",
        markdown_table(["Metric", "Formula / rule"], metric_formulas(threshold)),
        "",
        "## Execution coverage",
        "",
    ]

    coverage_rows = []
    for application in DATASETS:
        selected = [row for row in executions if row["application"] == application]
        counts = Counter(row["status"] for row in selected)
        total = len(selected)
        coverage_rows.append([
            application, total, counts["completed"], counts["failed"], counts["missing_metadata"],
            f"{100*counts['completed']/total:.1f}%",
        ])
    sections.extend([
        markdown_table(
            ["Application", "Discovered", "Completed", "Failed", "Missing metadata", "Completion rate"],
            coverage_rows,
        ),
        "",
        "### Failed or incomplete executions",
        "",
        markdown_table(
            ["Application", "Run", "Status", "Failed phase", "Reason"],
            ([row[key] for key in ("application", "run", "status", "failed_phase", "failure_detail")]
             for row in executions if row["status"] != "completed"),
        ),
        "",
        "## Headline scenario-level rates",
        "",
    ])
    rate_headers = ["Application", "Completed"]
    for label in ("RCA-SSR", "Remediation-SSR", "Joint SSR", "Aligned RCA", "Strict recovery"):
        rate_headers.extend((f"{label} successes", label, "95% CI"))
    per_application = [[row for row in runs if row["application"] == application] for application in DATASETS]
    rate_rows = [rate_row(application, selected) for application, selected in zip(DATASETS, per_application)]
    rate_rows.append(rate_row("Combined", runs))
    sections.extend([markdown_table(rate_headers, rate_rows), "", "## Joint score-successful runs", ""])
    joint = [row for row in runs if row["joint_success"]]
    sections.extend([
        markdown_table(
            ["Application", "Run", "Scenario", "Fault family", "Best RCA", "Best remediation", "Strict recovery"],
            ([row[key] for key in ("application", "run", "scenario", "fault_family", "best_rca_score",
                                   "best_remediation_score", "strict_recovery")] for row in joint),
        ),
        "",
        "## Job counts by status",
        "",
    ])
    status_values = sorted({row["status"] for row in summaries})
    status_rows = []
    for application in DATASETS:
        for kind in ("rca", "remediation"):
            counts = Counter(row["status"] for row in summaries if row["application"] == application and row["kind"] == kind)
            status_rows.append([application, kind, *[counts[value] for value in status_values], sum(counts.values())])
    sections.extend([
        markdown_table(["Application", "Kind", *status_values, "Total"], status_rows),
        "",
        "## Alignment verdict counts",
        "",
    ])
    alignment_values = sorted({row["alignment"] for row in summaries})
    alignment_rows = []
    for application in DATASETS:
        for kind in ("rca", "remediation"):
            counts = Counter(row["alignment"] for row in summaries if row["application"] == application and row["kind"] == kind)
            alignment_rows.append([application, kind, *[counts[value] for value in alignment_values], sum(counts.values())])
    sections.extend([
        markdown_table(["Application", "Kind", *alignment_values, "Total"], alignment_rows),
        "",
        "## Succeeded-job score distributions",
        "",
        markdown_table(
            ["Application", "Kind", "Outputs", "Mean", "Median", "Sample SD", "Min", "Q1", "Q3", "Max"],
            score_distribution(summaries, completed),
        ),
        "",
        "## Mean rubric dimensions",
        "",
    ])
    dimension_rows = []
    for application in DATASETS:
        for kind, source, dimensions in (
            ("rca", rca_rows, RCA_DIMENSIONS),
            ("remediation", remediation_rows, REMEDIATION_DIMENSIONS),
        ):
            selected = [row for row in source if row["application"] == application and row["status"] == "succeeded"]
            dimension_rows.append([application, kind, *[
                mean(value for row in selected if (value := number(row.get(dimension))) is not None)
                for dimension in dimensions
            ]])
    sections.extend([
        markdown_table(
            ["Application", "Kind", "Correctness", "Reasoning / feasibility", "Evidence / safety",
             "Localization / evidence alignment", "Completeness", "Penalty (remediation only)"],
            [row + [None] if row[1] == "rca" else row for row in dimension_rows],
        ),
        "",
        "## Remediation outcomes and safety",
        "",
    ])
    remediation_summary = [row for row in summaries if row["kind"] == "remediation"]
    outcome_rows = []
    for application in DATASETS:
        selected = [row for row in remediation_summary if row["application"] == application]
        metric_counts = Counter(row["metric_outcome"] or "missing" for row in selected)
        final_counts = Counter(row["final_grade"] or "missing" for row in selected)
        rubric_selected = [row for row in remediation_rows if row["application"] == application and row["status"] == "succeeded"]
        penalties = [number(row.get("penalty_total")) or 0 for row in rubric_selected]
        penalized = sum(value > 0 for value in penalties)
        outcome_rows.append([
            application, len(selected), metric_counts["good"], metric_counts["not_good"], metric_counts["not_evaluable"],
            final_counts["good"], final_counts["not_good"], final_counts["not_evaluable"],
            len(rubric_selected), penalized, f"{100*penalized/len(rubric_selected):.1f}%" if rubric_selected else "",
            sum(penalties), mean(penalties),
        ])
    sections.extend([
        markdown_table(
            ["Application", "Remediation outputs", "Metric good", "Metric not good", "Metric non-evaluable",
             "Final good", "Final not good", "Final non-evaluable", "Succeeded", "Penalized",
             "Penalized %", "Total penalty", "Mean penalty"],
            outcome_rows,
        ),
        "",
        "## Fault-family scenario rates",
        "",
    ])
    family_rows = []
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in runs:
        groups[(row["application"], row["fault_family"])].append(row)
    for (application, family), selected in sorted(groups.items()):
        total = len(selected)
        rca_success = sum(row["rca_success"] for row in selected)
        remediation_success = sum(row["remediation_success"] for row in selected)
        joint_success = sum(row["joint_success"] for row in selected)
        strict = sum(row["strict_recovery"] for row in selected)
        best_rca = [row["best_rca_score"] for row in selected if row["best_rca_score"] is not None]
        best_remediation = [row["best_remediation_score"] for row in selected if row["best_remediation_score"] is not None]
        family_rows.append([
            application, family, total, rca_success, f"{100*rca_success/total:.1f}%",
            remediation_success, f"{100*remediation_success/total:.1f}%", joint_success,
            f"{100*joint_success/total:.1f}%", strict, f"{100*strict/total:.1f}%",
            statistics.median(best_rca) if best_rca else None,
            statistics.median(best_remediation) if best_remediation else None,
        ])
    sections.extend([
        markdown_table(
            ["Application", "Fault family", "Runs", "RCA successes", "RCA-SSR", "Remediation successes",
             "Remediation-SSR", "Joint successes", "Joint SSR", "Strict recoveries", "Strict recovery rate",
             "Median best RCA", "Median best remediation"],
            family_rows,
        ),
        "",
        "## Complete scenario audit table",
        "",
        markdown_table(
            ["Application", "Run", "Scenario", "Fault family", "RCA jobs", "Remediation jobs", "Best RCA",
             "Best remediation", "RCA success", "Remediation success", "Joint success", "Aligned RCA",
             "Metric recovery", "Strict recovery"],
            ([row[key] for key in ("application", "run", "scenario", "fault_family", "rca_jobs", "remediation_jobs",
                                   "best_rca_score", "best_remediation_score", "rca_success", "remediation_success",
                                   "joint_success", "aligned_rca", "metric_recovery", "strict_recovery")]
             for row in runs),
        ),
        "",
        "## Interpretation notes",
        "",
        "- SSR values are scenario/run-level macro rates, not job-level pass rates.",
        "- Remediation-SSR is score-based; strict recovery additionally requires the grader's final `good` outcome.",
        "- Completed runs that produced no qualifying job count as failures for that stage.",
        "- Failed and missing-metadata executions are excluded from grading denominators and reported in coverage.",
        "- Job-level distribution statistics are secondary because jobs from the same scenario are not independent.",
    ])
    return "\n".join(sections) + "\n"


def main() -> int:
    args = parse_args()
    if not 0 <= args.threshold <= 1:
        raise SystemExit("--threshold must be between 0 and 1")
    root = args.root.expanduser().resolve()
    grades = args.input.expanduser()
    if not grades.is_absolute():
        grades = root / grades
    grades = grades.resolve()
    results = args.results.expanduser()
    if not results.is_absolute():
        results = root / results
    results = results.resolve()
    output = (args.output or (grades / "summary.md")).expanduser()
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    report = render(results, grades, args.threshold)
    output.write_text(report, encoding="utf-8")
    print(f"Wrote {output} ({len(report.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
