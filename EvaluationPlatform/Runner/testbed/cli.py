import argparse
from datetime import datetime
from pathlib import Path

from testbed.loadgenerator.runner import SCENARIO_MODULES

from .constants import DEFAULT_AGENT_NAMESPACE


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run application load, chaos injection, and evaluation capture."
    )
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--scenario", type=Path)
    selection.add_argument("--suite", type=Path)
    parser.add_argument("--environment", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args(argv)


def default_output_dir(repo_root: Path, loadgenerator: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return repo_root / "results" / f"{timestamp}-{loadgenerator}"
