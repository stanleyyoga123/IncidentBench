from __future__ import annotations

from pathlib import Path


DEFAULT_GROUND_TRUTH_DIR = Path(__file__).resolve().parents[1] / "resources" / "ground_truth"


def load_ground_truth(path: Path | None = None) -> dict[str, dict[str, str]]:
    source = Path(path or DEFAULT_GROUND_TRUTH_DIR)
    if not source.is_dir():
        raise FileNotFoundError(f"ground-truth directory not found: {source}")
    files = sorted(source.glob("*.md"))
    if not files:
        raise FileNotFoundError(f"no Markdown ground truth under: {source}")
    return {item.stem: load_ground_truth_file(item) for item in files}


def load_ground_truth_file(path: Path) -> dict[str, str]:
    current: str | None = None
    sections: dict[str, list[str]] = {"rca": [], "remediation": []}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if line.startswith("## ") and not line.startswith("### "):
            heading = line[3:].strip().lower()
            if heading == "rca":
                current = "rca"
            elif heading == "recommended remediation":
                current = "remediation"
            else:
                current = None
            continue
        if current:
            sections[current].append(line)
    result = {key: "\n".join(value).strip() for key, value in sections.items()}
    missing = [key for key, value in result.items() if not value]
    if missing:
        raise ValueError(
            f"ground truth {path} is missing required section content: "
            + ", ".join(missing)
        )
    return result
