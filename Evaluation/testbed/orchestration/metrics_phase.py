from datetime import datetime, timezone

from ..domain.phase_result import PhaseResult
from .phase_support import PhaseSupport


class MetricsPhase(PhaseSupport):
    name = "metrics"

    def execute(self, context):
        self.log("metrics phase: collecting Prometheus metrics")
        context.metadata["metrics"] = context.evaluator.collect_metrics(
            start=context.run_started_wall,
            end=context.experiment_finished_wall or datetime.now(timezone.utc),
            rate_window="1m",
            step_seconds=15,
        )
        context.metrics_collected = True
        return self.record(context, PhaseResult.success(self.name))
