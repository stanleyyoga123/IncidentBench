from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .rubric import KindRubric, Rubric


SUMMARY_FIELDS = (
    "methodology_version",
    "policy_hash",
    "run",
    "scenario",
    "kind",
    "job_id",
    "workflow_id",
    "status",
    "is_failed",
    "alignment",
    "overall_score",
    "metric_outcome",
    "final_grade",
    "reason",
)

RUBRIC_IDENTITY_FIELDS = (
    "methodology_version",
    "policy_hash",
    "run",
    "scenario",
    "job_id",
    "workflow_id",
    "status",
    "is_failed",
    "alignment",
)


def write_summary_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_rubric_score_csv(
    path: Path, grades: list[dict[str, Any]], kind_rubric: KindRubric
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(RUBRIC_IDENTITY_FIELDS)
    for criterion in kind_rubric.criteria:
        fieldnames.append(f"{criterion.id}_class")
        fieldnames.append(criterion.id)
    if kind_rubric.kind == "remediation":
        fieldnames.extend(["rubric_score", "penalty_total"])
    fieldnames.append("overall_score")
    rows = rubric_score_rows(grades, kind_rubric)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def rubric_score_rows(
    grades: list[dict[str, Any]], kind_rubric: KindRubric
) -> list[dict[str, Any]]:
    key = "rca_jobs" if kind_rubric.kind == "rca" else "remediation_jobs"
    rows: list[dict[str, Any]] = []
    for grade in grades:
        for job in grade.get(key) or []:
            rows.append(_rubric_score_row(grade, job, kind_rubric))
    return rows


def write_run_report(path: Path, grade: dict[str, Any], rubric: Rubric) -> None:
    lines = [f"# Semantic diagnostics: {grade['run']}", '',
             f"Scenario: `{grade.get('scenario')}`. Semantic status: `{grade['status']}`.", '',
             str(grade.get('reason') or ''), '',
             'Semantic scores describe evaluable final outputs only. Service recovery provenance is retained separately in grade.json.']
    for kind in ('rca', 'remediation'):
        jobs = grade.get(kind + '_jobs') or []
        lines.extend(_score_matrix_section(grade, rubric.kind(kind), kind.upper() + ' rubric scores'))
        lines.extend(_criterion_sections(jobs, kind.upper()))
        if kind == 'remediation':
            lines.extend(_penalty_sections(jobs))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def write_global_report(path: Path, grades: list[dict[str, Any]], rubric: Rubric) -> None:
    lines = ['# Semantic diagnostics', '',
             'Evaluable-output means exclude missing and unfinished results; they are not incident success rates.', '']
    for kind in ('rca', 'remediation'):
        jobs = [j for g in grades for j in g.get(kind + '_jobs', [])]
        missing = sum(j.get('rubric') is None for j in jobs)
        lines.extend([f"{kind.upper()}: {len(jobs)} exported jobs; {missing} without evaluable semantic scores.", ''])
        lines.extend(_score_table_section(grades, rubric.kind(kind), kind.upper() + ' rubric scores', heading='###'))
    lines.extend(_global_penalty_section(grades))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def _job_table(jobs: list[dict[str, Any]], *, remediation: bool) -> list[str]:
    if not jobs:
        return ["No outputs were present."]
    if remediation:
        lines = [
            "| Job | Status | Alignment | Overall | Metric outcome | Final grade | Reason |",
            "| --- | --- | --- | ---: | --- | --- | --- |",
        ]
        for job in jobs:
            lines.append(
                "| "
                + " | ".join(
                    (
                        _cell(job.get("id")),
                        _cell(job.get("status")),
                        _cell(job.get("alignment", {}).get("verdict")),
                        _score((job.get("rubric") or {}).get("overall_score")),
                        _cell(job.get("metrics", {}).get("outcome")),
                        _cell(job.get("final_grade")),
                        _cell(job.get("alignment", {}).get("reason")),
                    )
                )
                + " |"
            )
        return lines
    lines = [
        "| Job | Status | Alignment | Overall | Reason |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for job in jobs:
        lines.append(
            "| "
            + " | ".join(
                (
                    _cell(job.get("id")),
                    _cell(job.get("status")),
                    _cell(job.get("alignment", {}).get("verdict")),
                    _score((job.get("rubric") or {}).get("overall_score")),
                    _cell(job.get("alignment", {}).get("reason")),
                )
            )
            + " |"
        )
    return lines


def _score_matrix_section(
    grade: dict[str, Any], kind_rubric: KindRubric, title: str
) -> list[str]:
    rows = rubric_score_rows([grade], kind_rubric)
    if not rows:
        return []
    return ["", f"### {title}", ""] + _score_markdown_table(rows, kind_rubric)


def _score_table_section(
    grades: list[dict[str, Any]],
    kind_rubric: KindRubric,
    title: str,
    *,
    heading: str = "##",
) -> list[str]:
    rows = rubric_score_rows(grades, kind_rubric)
    if not rows:
        return []
    return ["", f"{heading} {title}", ""] + _score_markdown_table(rows, kind_rubric)


def _combined_remediation_section(
    grades: list[dict[str, Any]],
    kind_rubric: KindRubric,
    title: str,
    *,
    heading: str,
) -> list[str]:
    jobs = [
        (grade, job)
        for grade in grades
        for job in grade.get("remediation_jobs") or []
    ]
    if not jobs:
        return []
    headers = ["Run", "Job", *[item.symbol for item in kind_rubric.criteria]]
    headers.extend(
        [
            "Rubric",
            "Penalty",
            "Total",
            "P95 before",
            "P95 after",
            "P95 change",
            "P95 assessment",
            "5xx before",
            "5xx after",
            "5xx change",
            "5xx assessment",
            "Metric outcome",
            "Final grade",
        ]
    )
    alignments = [" --- ", " --- "]
    alignments.extend(" ---: " for _ in kind_rubric.criteria)
    alignments.extend(
        [
            " ---: ", " ---: ", " ---: ",
            " ---: ", " ---: ", " ---: ", " --- ",
            " ---: ", " ---: ", " ---: ", " --- ",
            " --- ", " --- ",
        ]
    )
    lines = [
        "",
        f"{heading} {title}",
        "",
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(alignments) + "|",
    ]
    for grade, job in jobs:
        row = _rubric_score_row(grade, job, kind_rubric)
        families = (job.get("metrics") or {}).get("families") or {}
        p95 = families.get("response_time_p95_seconds") or {}
        http_5xx = families.get("http_5xx_rate") or {}
        values = [_cell(row.get("run")), _cell(row.get("job_id"))]
        values.extend(_score(row.get(item.id)) for item in kind_rubric.criteria)
        values.extend(
            [
                _score(row.get("rubric_score")),
                _score(row.get("penalty_total")),
                _score(row.get("overall_score")),
                _number(p95.get("before_median")),
                _number(p95.get("after_median")),
                _percent(p95.get("relative_change")),
                _cell(p95.get("assessment")),
                _number(http_5xx.get("before_median")),
                _number(http_5xx.get("after_median")),
                _percent(http_5xx.get("relative_change")),
                _cell(http_5xx.get("assessment")),
                _cell((job.get("metrics") or {}).get("outcome")),
                _cell(job.get("final_grade")),
            ]
        )
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _score_markdown_table(
    rows: list[dict[str, Any]], kind_rubric: KindRubric
) -> list[str]:
    headers = ["Run", "Job"]
    alignments = [" --- ", " --- "]
    for criterion in kind_rubric.criteria:
        headers.append(criterion.symbol)
        alignments.append(" ---: ")
    if kind_rubric.kind == "remediation":
        headers.extend(["Rubric", "Penalty", "Total"])
        alignments.extend([" ---: ", " ---: ", " ---: "])
    else:
        headers.append("Total")
        alignments.append(" ---: ")
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(alignments) + "|",
    ]
    for row in rows:
        values = [_cell(row.get("run")), _cell(row.get("job_id"))]
        for criterion in kind_rubric.criteria:
            values.append(_score(row.get(criterion.id)))
        if kind_rubric.kind == "remediation":
            values.append(_score(row.get("rubric_score")))
            values.append(_score(row.get("penalty_total")))
        values.append(_score(row.get("overall_score")))
        lines.append("| " + " | ".join(values) + " |")
    mean_values = ["", "mean"]
    for criterion in kind_rubric.criteria:
        mean_values.append(_mean_field(rows, criterion.id))
    if kind_rubric.kind == "remediation":
        mean_values.append(_mean_field(rows, "rubric_score"))
        mean_values.append(_mean_field(rows, "penalty_total"))
    mean_values.append(_mean_field(rows, "overall_score"))
    lines.append("| " + " | ".join(mean_values) + " |")
    return lines


def _criterion_sections(jobs: list[dict[str, Any]], title: str) -> list[str]:
    sections: list[str] = []
    for job in jobs:
        criteria = ((job.get("rubric") or {}).get("criteria")) or {}
        if not criteria:
            continue
        sections.extend(
            [
                "",
                f"### {title} criteria for `{job.get('id') or 'unknown'}`",
                "",
                "| Criterion | Class | Score | Weight | Reason |",
                "| --- | --- | ---: | ---: | --- |",
            ]
        )
        for item in criteria.values():
            sections.append(
                "| "
                + " | ".join(
                    (
                        _cell(item.get("name") or item.get("symbol")),
                        _cell(item.get("class")),
                        _score(item.get("score")),
                        _score(item.get("weight")),
                        _cell(item.get("reason")),
                    )
                )
                + " |"
            )
    return sections


def _penalty_sections(jobs: list[dict[str, Any]]) -> list[str]:
    sections: list[str] = []
    for job in jobs:
        items = ((job.get("rubric") or {}).get("penalties")) or []
        if not items:
            continue
        sections.extend(
            [
                "",
                f"### Remediation penalties for `{job.get('id') or 'unknown'}`",
                "",
                f"Rubric score: `{_score((job.get('rubric') or {}).get('rubric_score'))}`; "
                f"penalty total: `{_score((job.get('rubric') or {}).get('penalty_total'))}`; "
                f"overall: `{_score((job.get('rubric') or {}).get('overall_score'))}`.",
                "",
                "| Criteria | Penalty | Applied | Reason |",
                "| --- | ---: | --- | --- |",
            ]
        )
        for item in items:
            sections.append(
                "| "
                + " | ".join(
                    (
                        _cell(item.get("criteria")),
                        _score(item.get("penalty")),
                        _cell(item.get("applied")),
                        _cell(item.get("reason")),
                    )
                )
                + " |"
            )
    return sections


def _global_penalty_section(grades: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for grade in grades:
        for job in grade.get("remediation_jobs") or []:
            items = [
                item
                for item in ((job.get("rubric") or {}).get("penalties") or [])
                if item.get("applied")
            ]
            if not items:
                continue
            for item in items:
                rows.append(
                    "| "
                    + " | ".join(
                        (
                            _cell(grade.get("run")),
                            _cell(job.get("id")),
                            _cell(item.get("criteria")),
                            _score(item.get("penalty")),
                            _cell(item.get("reason")),
                        )
                    )
                    + " |"
                )
    if not rows:
        return []
    return [
        "",
        "## Remediation penalties applied",
        "",
        "| Run | Job | Criteria | Penalty | Reason |",
        "| --- | --- | --- | ---: | --- |",
        *rows,
    ]


def _rubric_score_row(
    grade: dict[str, Any], job: dict[str, Any], kind_rubric: KindRubric
) -> dict[str, Any]:
    scored = job.get("rubric") or {}
    criteria = scored.get("criteria") or {}
    row: dict[str, Any] = {
        "methodology_version": (grade.get("research") or {}).get("methodology_version"),
        "policy_hash": (grade.get("research") or {}).get("policy_hash"),
        "run": grade.get("run"),
        "scenario": grade.get("scenario"),
        "job_id": job.get("id"),
        "workflow_id": job.get("workflow_id"),
        "status": job.get("status"),
        "is_failed": job.get("status") == "failed",
        "alignment": (job.get("alignment") or {}).get("verdict"),
        "overall_score": scored.get("overall_score"),
        "rubric_score": scored.get("rubric_score"),
        "penalty_total": scored.get("penalty_total"),
    }
    for criterion in kind_rubric.criteria:
        item = criteria.get(criterion.id) or {}
        row[f"{criterion.id}_class"] = item.get("class")
        row[criterion.id] = item.get("score")
    return row


def _mean_criterion_bullets(
    grades: list[dict[str, Any]], kind_rubric: KindRubric, label: str
) -> list[str]:
    rows = rubric_score_rows(grades, kind_rubric)
    bullets = []
    for criterion in kind_rubric.criteria:
        mean = _mean_field(rows, criterion.id)
        if mean:
            bullets.append(
                f"- {label} mean {criterion.name} ({criterion.symbol}): {mean}"
            )
    return bullets


def _count(items: list[dict[str, Any]], field: str, expected: str) -> int:
    count = 0
    for item in items:
        value: Any = item.get(field)
        if isinstance(value, dict):
            value = value.get("verdict")
        if value == expected:
            count += 1
    return count


def _count_nested(
    items: list[dict[str, Any]], field: str, nested: str, expected: str
) -> int:
    return sum(
        1
        for item in items
        if isinstance(item.get(field), dict)
        and item[field].get(nested) == expected
    )


def _mean_score(jobs: list[dict[str, Any]]) -> str:
    scores = [
        float(job["rubric"]["overall_score"])
        for job in jobs
        if isinstance(job.get("rubric"), dict)
        and isinstance(job["rubric"].get("overall_score"), (int, float))
    ]
    if not scores:
        return ""
    return f"{sum(scores) / len(scores):.4f}"


def _mean_field(rows: list[dict[str, Any]], field: str) -> str:
    scores = [
        float(row[field])
        for row in rows
        if isinstance(row.get(field), (int, float))
    ]
    if not scores:
        return ""
    return f"{sum(scores) / len(scores):.4f}"


def _cell(value: Any) -> str:
    return _text(value).replace("|", "\\|")


def _text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").split())


def _number(value: Any) -> str:
    return "" if value is None else f"{float(value):.6g}"


def _score(value: Any) -> str:
    return "" if value is None else f"{float(value):.4f}"


def _percent(value: Any) -> str:
    return "" if value is None else f"{100 * float(value):.2f}%"
