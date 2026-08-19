import json
from pathlib import Path
from typing import Any

from testbed.reporting.metadata_reader import MetadataReader
from testbed.reporting.run_discovery import RunDiscovery

from .errors import collect_errors
from .impact import metric_impact
from .judge.client import JudgeClient
from .judge.run import judge_run, score_labeled_run
from .log import progress
from .plots import plot_run
from .reports import write_run_report, write_summary
from .timebase import chaos_t0


def analyze(
    input_dir: Path,
    output_dir: Path,
    *,
    judge: JudgeClient | None,
    skip_judge: bool = False,
    reuse_judge: bool = False,
) -> list[dict[str, Any]]:
    if skip_judge and reuse_judge:
        raise ValueError("skip_judge and reuse_judge cannot be combined")
    runs = RunDiscovery().discover(input_dir)
    if not runs:
        raise FileNotFoundError(f"no metadata.json runs under {input_dir}")
    progress(f"discovered {len(runs)} run(s) under {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for index, run in enumerate(runs, start=1):
        progress(f"run {index}/{len(runs)}: {run.name}")
        records.append(
            _analyze_run(
                run,
                output_dir / "runs" / run.name,
                judge,
                skip_judge,
                reuse_judge,
                run_label=f"{index}/{len(runs)}",
            )
        )
    progress("writing summary.csv and summary.md")
    write_summary(output_dir, records)
    return records


def _analyze_run(
    run: Path,
    destination: Path,
    judge: JudgeClient | None,
    skip_judge: bool,
    reuse_judge: bool = False,
    run_label: str = "1/1",
) -> dict[str, Any]:
    destination.mkdir(parents=True, exist_ok=True)
    prefix = f"run {run_label} {run.name}"
    progress(f"{prefix}: reading metadata")
    metadata = MetadataReader().read(run)
    origin = chaos_t0(metadata)
    plots = []
    if origin is not None:
        progress(f"{prefix}: plotting metrics (t0={origin:.0f})")
        plots = [str(path) for path in plot_run(run, origin, destination / "plots")]
        progress(f"{prefix}: wrote {len(plots)} plot(s)")
    else:
        progress(f"{prefix}: skipping plots (no chaos start timestamp)")
    progress(f"{prefix}: scanning operational errors")
    errors = collect_errors(run, metadata)
    (destination / "errors.json").write_text(json.dumps(errors, indent=2, default=str))
    progress(
        f"{prefix}: {errors.get('agent_error_count', 0)} agent error(s), "
        f"{errors.get('failed_tool_count', 0)} failed tool(s)"
    )
    progress(f"{prefix}: computing metric impact")
    impact = metric_impact(run, metadata, origin)
    progress(f"{prefix}: metric impact observed={impact.get('observed')}")
    if skip_judge or (judge is None and not reuse_judge):
        progress(f"{prefix}: skipping LLM judge")
        scores = {"skipped": True}
        raw = {}
    elif reuse_judge:
        judge_path = destination / "judge.json"
        if not judge_path.is_file():
            raise FileNotFoundError(
                f"no judge.json to reuse at {judge_path}; run the analyzer once without --reuse-judge"
            )
        progress(f"{prefix}: rescoring from existing judge.json")
        raw = json.loads(judge_path.read_text())
        scores = score_labeled_run(run, metadata, errors, impact, raw)
        raw = scores.pop("raw", raw)
        progress(f"{prefix}: end_score={scores.get('end_score')}")
    else:
        progress(f"{prefix}: starting LLM judge")
        scores = judge_run(
            run, metadata, errors, impact, judge, checkpoint=destination / "judge.json"
        )
        raw = scores.pop("raw", {})
        progress(f"{prefix}: end_score={scores.get('end_score')}")
    (destination / "scores.json").write_text(json.dumps(scores, indent=2, default=str))
    (destination / "judge.json").write_text(json.dumps(raw, indent=2, default=str))
    record = {
        "run_id": run.name,
        "run_folder": str(run),
        "scenario": (metadata.get("scenario") or {}).get("name"),
        "mode": "agent" if metadata.get("agents_enabled") else "non-agent",
        "t0": origin,
        "plots": plots,
        "errors": errors,
        "impact": impact,
        "scores": scores,
    }
    write_run_report(destination / "report.md", record)
    progress(f"{prefix}: wrote report")
    return record
