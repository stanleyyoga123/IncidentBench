from __future__ import annotations

import argparse
import os
from pathlib import Path

from .ground_truth import DEFAULT_GROUND_TRUTH_DIR
from .judge import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_URL,
    DEFAULT_MAX_TOKENS,
    DEFAULT_TIMEOUT_SECONDS,
    OpenAICompatibleJudge,
)
from .logging_utils import configure_logging
from .pipeline import GraderConfig, grade_runs
from .penalty import DEFAULT_PENALTIES_DIR
from .rubric import DEFAULT_RUBRIC_PATH, load_rubric


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Grade final RCA/remediation outputs and remediation metrics."
    )
    parser.add_argument("--input", type=Path, default=Path("results"))
    parser.add_argument("--output", type=Path, default=Path("grades"))
    parser.add_argument(
        "--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH_DIR
    )
    parser.add_argument("--rubric", type=Path, default=DEFAULT_RUBRIC_PATH)
    parser.add_argument("--penalties", type=Path, default=DEFAULT_PENALTIES_DIR)
    parser.add_argument(
        "--base-url", default=os.getenv("JUDGE_URL", DEFAULT_JUDGE_URL)
    )
    parser.add_argument(
        "--model", default=os.getenv("JUDGE_MODEL", DEFAULT_JUDGE_MODEL)
    )
    parser.add_argument("--token", default=os.getenv("JUDGE_TOKEN", "EMPTY"))
    parser.add_argument(
        "--judge-timeout-seconds",
        type=float,
        default=float(os.getenv("JUDGE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
    )
    parser.add_argument(
        "--judge-max-tokens",
        type=int,
        default=int(os.getenv("JUDGE_MAX_TOKENS", DEFAULT_MAX_TOKENS)),
    )
    parser.add_argument("--window-minutes", type=float, default=5.0)
    parser.add_argument("--threshold", type=float, default=0.15)
    parser.add_argument("--refresh-judge", action="store_true")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show detailed progress; a verbose grader.log is always written",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.judge_max_tokens <= 0:
        raise SystemExit("--judge-max-tokens must be positive")
    configure_logging(args.output, verbose=args.verbose)
    rubric = load_rubric(args.rubric)
    judge = OpenAICompatibleJudge(
        model=args.model,
        base_url=args.base_url,
        rubric=rubric,
        token=args.token,
        timeout_seconds=args.judge_timeout_seconds,
        max_tokens=args.judge_max_tokens,
    )
    grades = grade_runs(
        GraderConfig(
            input_path=args.input,
            output_path=args.output,
            ground_truth_path=args.ground_truth,
            rubric_path=args.rubric,
            penalties_path=args.penalties,
            model=args.model,
            judge_max_tokens=args.judge_max_tokens,
            window_minutes=args.window_minutes,
            threshold=args.threshold,
            refresh_judge=args.refresh_judge,
        ),
        judge,
    )
    graded = sum(item["status"] == "graded" for item in grades)
    print(
        f"graded {graded}/{len(grades)} runs; reports written to "
        f"{args.output.resolve()}"
    )
    judge_failures = sum(
        1
        for grade in grades
        for jobs in (grade.get("rca_jobs") or [], grade.get("remediation_jobs") or [])
        for job in jobs
        if str((job.get("alignment") or {}).get("reason") or "").startswith(
            "judge failed:"
        )
    )
    if judge_failures:
        raise SystemExit(
            f"grading completed with {judge_failures} judge failure(s); "
            f"inspect {args.output / 'grader.log'}"
        )
    return 0
