import time
from datetime import datetime, timezone

from ..domain.phase_result import PhaseResult
from .phase_support import PhaseSupport


class BaselinePhase(PhaseSupport):
    name = "baseline"

    def __init__(self, load_launcher, wait_until, metadata, log) -> None:
        super().__init__(metadata, log)
        self.load_launcher = load_launcher
        self.wait_until = wait_until

    def execute(self, context):
        self.log("baseline phase: collecting snapshot before load")
        context.metadata["snapshots"].append(context.evaluator.collect_snapshot("baseline-before-load"))
        self.log(
            f"spawning locust: scenario={context.config.loadgenerator}, "
            f"host={context.config.host}, duration={context.total_load_duration}s"
        )
        context.load_process = self.load_launcher(
            repo_root=context.config.repo_root,
            output_dir=context.config.output_dir,
            scenario=context.config.loadgenerator,
            host=context.config.host,
            duration_seconds=context.total_load_duration,
        )
        context.metadata["loadgenerator"]["command"] = context.load_process.command
        started_at = time.monotonic()
        context.run_started_wall = datetime.now(timezone.utc)
        message = f"baseline phase: running load for {context.config.baseline_seconds}s"
        if context.config.agents_enabled:
            message += " before agents start"
        self.log(message)
        self.wait_until(context.config.baseline_seconds, started_at)
        return self.record(context, PhaseResult.success(self.name))
