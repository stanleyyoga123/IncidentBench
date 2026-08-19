import argparse
import os
from pathlib import Path

from .judge.client import VLLMJudge
from .log import configure_logging, progress
from .pipeline import analyze

DEFAULT_JUDGE_URL = "http://localhost:8000/v1"
DEFAULT_JUDGE_MODEL = "Qwen/Qwen3.6-35B-A3B"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze Evaluation run folders: plots, operational errors, and LLM-as-judge scores."
    )
    parser.add_argument("--input", type=Path, default=Path("results"))
    parser.add_argument("--output", type=Path, default=Path("analysis"))
    parser.add_argument(
        "--base-url",
        default=os.environ.get("JUDGE_URL", DEFAULT_JUDGE_URL),
        help="vLLM OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("JUDGE_MODEL", DEFAULT_JUDGE_MODEL),
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("JUDGE_TOKEN", "EMPTY"),
        help="Bearer token for the vLLM endpoint; defaults to EMPTY",
    )
    parser.add_argument("--skip-judge", action="store_true")
    parser.add_argument(
        "--reuse-judge",
        action="store_true",
        help="Rescore from analysis/runs/*/judge.json without calling vLLM",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.skip_judge and args.reuse_judge:
        raise SystemExit("cannot combine --skip-judge and --reuse-judge")
    configure_logging()
    judge = None
    if args.reuse_judge:
        progress("judge: reusing existing judge.json labels")
    elif not args.skip_judge:
        progress(f"judge: vLLM {args.model} at {args.base_url}")
        judge = VLLMJudge(args.model, args.base_url, args.token)
    else:
        progress("judge: skipped")
    records = analyze(
        args.input,
        args.output,
        judge=judge,
        skip_judge=args.skip_judge,
        reuse_judge=args.reuse_judge,
    )
    progress(f"done: analyzed {len(records)} run(s) into {args.output}")
    return 0
