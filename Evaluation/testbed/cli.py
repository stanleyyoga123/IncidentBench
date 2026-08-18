import argparse
from datetime import datetime
from pathlib import Path

from testbed.loadgenerator.runner import SCENARIO_MODULES

from .constants import DEFAULT_AGENT_NAMESPACE, DEFAULT_HOST, DEFAULT_NAMESPACE


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
        description="Run Online Boutique load, chaos injection, and evaluation capture."
    )
    parser.add_argument("--loadgenerator", choices=sorted(SCENARIO_MODULES), required=True)
    parser.add_argument("--scenario", type=Path, required=True)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--duration", type=positive_int, default=900)
    parser.add_argument("--baseline-minutes", type=positive_float)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--agent-namespace", default=DEFAULT_AGENT_NAMESPACE)
    parser.add_argument("--grace-period", type=non_negative_int, default=60)
    parser.add_argument("--prometheus-url")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument("--port-forward", action="store_true")
    parser.add_argument("--port-forward-port", type=positive_int, default=8888)
    return parser.parse_args(argv)


def default_output_dir(repo_root: Path, loadgenerator: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return repo_root / "results" / f"{timestamp}-{loadgenerator}"
