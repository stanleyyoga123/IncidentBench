from datetime import datetime, timezone

from ..chaos.execution.chaos_phase_executor import ChaosPhaseExecutor
from ..chaos.execution.execution_context import ChaosExecutionContext
from ..domain.phase_result import PhaseResult
from ..domain.run_status import RunStatus
from .phase_support import PhaseSupport


class ChaosPhase(PhaseSupport):
    name = "chaos"

    def __init__(self, executor: ChaosPhaseExecutor, execution_context: ChaosExecutionContext, metadata, log) -> None:
        super().__init__(metadata, log)
        self.executor = executor
        self.execution_context = execution_context

    def execute(self, context):
        self.log(f"chaos phase: executing {len(context.scenario.steps)} scenario steps")
        context.metadata["snapshots"].append(context.evaluator.collect_snapshot("before-chaos"))
        results = self.executor.execute(context.scenario.steps, self.execution_context)
        context.metadata["chaos_steps"] = results
        failed = next((step for step in results if step["status"] != "completed"), None)
        if failed:
            if failed["status"] == "cleanup_failed":
                status, returncode = RunStatus.CLEANUP_FAILED, 3
            elif failed["status"] == "interrupted":
                status, returncode = RunStatus.INTERRUPTED, 130
            else:
                status, returncode = RunStatus.FAILED, 1
            return self.record(
                context,
                PhaseResult.failure(
                    self.name,
                    returncode,
                    status=status,
                    step=failed,
                ),
            )
        context.experiment_finished_wall = datetime.now(timezone.utc)
        return self.record(context, PhaseResult.success(self.name))
