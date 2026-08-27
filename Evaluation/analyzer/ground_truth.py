from pathlib import Path
from typing import Any


DEFAULT_GROUND_TRUTH_DIR = Path(__file__).resolve().parent / "ground_truth"


def load_ground_truth(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Load one human-editable Markdown answer key per scenario."""
    source = Path(path or DEFAULT_GROUND_TRUTH_DIR)
    if not source.is_dir():
        raise FileNotFoundError(f"ground-truth directory not found: {source}")
    files = sorted(source.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no ground-truth Markdown files under: {source}")
    return {item.stem: _load_scenario_file(item) for item in files}


def _load_scenario_file(path: Path) -> dict[str, str]:
    field: str | None = None
    buffers: dict[str, list[str]] = {"rca": [], "remediation": []}
    for raw_line in path.read_text().splitlines():
        line = raw_line.rstrip()
        if line.startswith("## ") and not line.startswith("### "):
            heading = line[3:].strip().lower()
            if heading == "rca":
                field = "rca"
            elif heading in {"remediation", "recommended remediation"}:
                field = "remediation"
            else:
                field = None
            continue
        if field is not None:
            buffers[field].append(line)
    entry = _finish_entry(buffers)
    if not entry.get("rca") or not entry.get("remediation"):
        raise ValueError(
            f"ground-truth file requires RCA and Recommended remediation: {path}"
        )
    return entry


def scenario_ground_truth(
    entries: dict[str, dict[str, str]], scenario: str | None
) -> dict[str, Any]:
    if not scenario or scenario not in entries:
        raise KeyError(f"no ground-truth entry for scenario {scenario!r}")
    return {"scenario": scenario, **entries[scenario]}


def _finish_entry(buffers: dict[str, list[str]]) -> dict[str, str]:
    return {
        key: "\n".join(lines).strip()
        for key, lines in buffers.items()
    }
