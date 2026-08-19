import csv
from pathlib import Path
from typing import Any


_CATEGORY_HEADINGS = (
    ("helped", "Remediated the injected fault"),
    ("harmed", "Degraded the system"),
    ("no_impact", "No impactful change"),
)

_AGGREGATION_NOTE = (
    "RCA and remediation components credit the best injection match (80%) "
    "instead of averaging every false-alarm session. Operational health counts "
    "job/workflow failures only, not investigation HTTP timeouts."
)


def write_run_report(path: Path, record: dict[str, Any]) -> None:
    scores = record.get("scores") or {}
    errors = record.get("errors") or {}
    impact = record.get("impact") or {}
    holistic = scores.get("holistic") or {}
    components = scores.get("components") or {}
    highlights = scores.get("highlights") or {}
    categories = scores.get("categories") or {}
    lines = [
        f"# {record['run_id']}",
        "",
        f"- scenario: {record.get('scenario')}",
        f"- mode: {record.get('mode')}",
        f"- chaos t0 unix: {record.get('t0')}",
        f"- plots: {len(record.get('plots') or [])}",
        f"- agent operational errors: {errors.get('agent_error_count', 0)}",
        f"- metric impact observed: {impact.get('observed')}",
        "",
        "## End score",
        "",
    ]
    if scores.get("skipped"):
        lines.append("Judge skipped (`--skip-judge`). Plots and errors were still written.")
    else:
        lines.extend(
            [
                f"- end score: {_fmt(scores.get('end_score'))}",
                f"- impact (weight {scores.get('weights', {}).get('impact', 0.2)}): "
                f"{_fmt(1.0 if components.get('impact_observed') else 0.0)}",
                f"- RCA: {_fmt(components.get('rca'))}",
                f"- remediation: {_fmt(components.get('remediation'))}",
                f"- operational health: {_fmt(components.get('operational'))}",
                "",
                _AGGREGATION_NOTE,
                "",
                f"Successfully remediated: {holistic.get('successfully_remediated', 'n/a')}",
                f"RCA matched injected chaos: {holistic.get('rca_matched_injection', 'n/a')}",
                "",
                holistic.get("impact_narrative") or "",
                "",
                "## Highlights",
                "",
            ]
        )
        lines.extend(_highlight_lines(highlights.get("best"), "Most impactful"))
        lines.extend(_highlight_lines(highlights.get("worst"), "Worst"))
        lines.extend(["", "## Session categories", ""])
        for key, heading in _CATEGORY_HEADINGS:
            lines.append(f"### {heading}")
            lines.append("")
            items = categories.get(key) or []
            if not items:
                lines.append("None.")
            else:
                lines.extend(_category_table(items))
            lines.append("")
        lines.extend(
            [
                "## RCA sessions",
                "",
            ]
        )
        lines.extend(_rca_table(scores.get("rca") or []))
        lines.extend(["", "## Remediation sessions", ""])
        lines.extend(_remediation_table(scores.get("remediation") or []))
    lines.extend(["", "## Operational errors", ""])
    items = errors.get("errors") or []
    if not items:
        lines.append("None.")
    else:
        for item in items:
            lines.append(
                f"- `{item.get('kind')}` {item.get('source')} "
                f"{item.get('job_id') or ''} {item.get('message')}"
            )
    locust = errors.get("locust") or {}
    if locust.get("benign_stop"):
        lines.extend(
            [
                "",
                "Locust non-zero exit treated as a benign stop "
                f"(failure_pct={_fmt(locust.get('failure_pct'))}).",
            ]
        )
    path.write_text("\n".join(lines).rstrip() + "\n")


def write_summary(output_dir: Path, records: list[dict[str, Any]]) -> None:
    csv_path = output_dir / "summary.csv"
    md_path = output_dir / "summary.md"
    fieldnames = [
        "run",
        "scenario",
        "mode",
        "rca_score",
        "true_positive_count",
        "false_alarm_count",
        "rca_matched_injection",
        "remediation_score",
        "operational_health",
        "impact_observed",
        "successfully_remediated",
        "helped_count",
        "harmed_count",
        "no_impact_count",
        "best_session",
        "worst_session",
        "end_score",
        "agent_error_count",
        "judge_skipped",
    ]
    rows = [_summary_row(record) for record in records]
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        "# Evaluation analysis summary",
        "",
        "| " + " | ".join(fieldnames) + " |",
        "| " + " | ".join("---" for _ in fieldnames) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row[name]) for name in fieldnames) + " |")
    md_path.write_text("\n".join(lines) + "\n")


def _summary_row(record: dict[str, Any]) -> dict[str, Any]:
    scores = record.get("scores") or {}
    components = scores.get("components") or {}
    errors = record.get("errors") or {}
    holistic = scores.get("holistic") or {}
    return {
        "run": record["run_id"],
        "scenario": record.get("scenario") or "",
        "mode": record.get("mode") or "",
        "rca_score": _fmt(components.get("rca")),
        "true_positive_count": components.get("true_positive_count", ""),
        "false_alarm_count": components.get("false_alarm_count", ""),
        "rca_matched_injection": holistic.get("rca_matched_injection")
        or components.get("rca_matched_injection"),
        "remediation_score": _fmt(components.get("remediation")),
        "operational_health": _fmt(components.get("operational")),
        "impact_observed": components.get("impact_observed"),
        "successfully_remediated": holistic.get("successfully_remediated") or "",
        "helped_count": components.get("helped_count", ""),
        "harmed_count": components.get("harmed_count", ""),
        "no_impact_count": components.get("no_impact_count", ""),
        "best_session": components.get("best_session") or "",
        "worst_session": components.get("worst_session") or "",
        "end_score": _fmt(scores.get("end_score")),
        "agent_error_count": errors.get("agent_error_count", 0),
        "judge_skipped": bool(scores.get("skipped")),
    }


def _highlight_lines(item: dict[str, Any] | None, title: str) -> list[str]:
    if not item:
        return [f"- {title}: none"]
    return [
        f"- {title}: `{item.get('session_id')}` "
        f"({item.get('role')}, {item.get('impact_class')}, score={_fmt(item.get('score'))}) "
        f"— {_cell(item.get('reason'))}"
    ]


def _category_table(items: list[dict[str, Any]]) -> list[str]:
    headers = ["session", "role", "impact", "score", "reason"]
    rows = [
        [
            item.get("session_id"),
            item.get("role"),
            item.get("impact_class"),
            _fmt(item.get("score")),
            item.get("reason"),
        ]
        for item in items
    ]
    return _markdown_table(headers, rows)


def _rca_table(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["None."]
    headers = [
        "session",
        "kind",
        "matched",
        "impact",
        "score",
        "localization / FA recognition",
        "necessity",
        "evidence",
    ]
    rows = []
    for item in items:
        labels = item.get("labels") or {}
        kind = item.get("session_kind")
        recognition = (
            labels.get("localization")
            if kind == "true_positive"
            else labels.get("false_alarm_recognition")
        )
        rows.append(
            [
                item.get("session_id"),
                kind,
                item.get("matched_injection"),
                item.get("impact_class"),
                _fmt(item.get("score")),
                recognition,
                labels.get("necessity"),
                item.get("evidence") or item.get("impact_reason"),
            ]
        )
    return _markdown_table(headers, rows)


def _remediation_table(items: list[dict[str, Any]]) -> list[str]:
    if not items:
        return ["None."]
    headers = [
        "session",
        "addressed",
        "impact",
        "score",
        "target_correctness",
        "safety",
        "evidence",
    ]
    rows = [
        [
            item.get("session_id"),
            item.get("addressed_injection"),
            item.get("impact_class"),
            _fmt(item.get("score")),
            (item.get("labels") or {}).get("target_correctness"),
            (item.get("labels") or {}).get("safety"),
            item.get("evidence") or item.get("impact_reason"),
        ]
        for item in items
    ]
    return _markdown_table(headers, rows)


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
    return lines


def _cell(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", " ").replace("|", "/")
    if len(text) > 140:
        return text[:137] + "..."
    return text


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)
