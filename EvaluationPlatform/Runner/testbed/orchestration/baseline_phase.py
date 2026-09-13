import time
from datetime import datetime, timezone

from ..domain.phase_result import PhaseResult
from ..loadgenerator.baseline_health import assess_baseline
from .phase_support import PhaseSupport


class BaselinePhase(PhaseSupport):
    name = "baseline"

    def __init__(self, load_launcher, wait_until, metadata, log, sleep=time.sleep) -> None:
        super().__init__(metadata, log)
        self.load_launcher = load_launcher
        self.wait_until = wait_until
        self.sleep = sleep

    def execute(self, context):
        delay = context.config.startup_delay_seconds
        if delay:
            self.log(
                f"baseline phase: waiting {delay}s for "
                f"{context.config.application} startup warm-up"
            )
            self.sleep(delay)
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
            application_module=context.config.loadgenerator_module,
            host=context.config.host,
            duration_seconds=context.total_load_duration,
            parameters=getattr(context.config, "load_parameters", None),
        )
        context.metadata["loadgenerator"]["command"] = context.load_process.command
        started_at = time.monotonic()
        context.run_started_wall = datetime.now(timezone.utc)
        message = f"baseline phase: running load for {context.config.baseline_seconds}s"
        if context.config.agents_enabled:
            message += " before agents start"
        self.log(message)
        self.wait_until(context.config.baseline_seconds, started_at)
        if context.config.application in {"teastore", "sock-shop"}:
            health = assess_baseline(
                context.config.output_dir / "loadgenerator"
                / f"{context.config.loadgenerator}_stats_history.csv",
                time.time(),
            )
            if context.load_process.process.poll() is not None:
                health["passed"] = False
                health["errors"].append("load generator exited before baseline validation")
            context.metadata["baseline_health"] = health
            if not health["passed"]:
                self.log(
                    f"{context.config.application} baseline rejected: "
                    + "; ".join(health["errors"])
                )
                return self.record(context, PhaseResult.failure(self.name, health=health))
        return self.record(context, PhaseResult.success(self.name))
