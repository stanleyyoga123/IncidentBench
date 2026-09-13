from collections.abc import Iterable

from ...domain.scenario import ScenarioStep
from .execution_context import ChaosExecutionContext
from .idle_step_executor import IdleStepExecutor
from .scheduled_step_executor import ScheduledStepExecutor


class ChaosPhaseExecutor:
    def __init__(self, scheduled: ScheduledStepExecutor) -> None:
        self.idle = IdleStepExecutor()
        self.scheduled = scheduled

    def execute(
        self,
        steps: Iterable[ScenarioStep],
        context: ChaosExecutionContext,
    ) -> list[dict]:
        results = []
        for step in steps:
            result = (
                self.idle.execute(step, context)
                if step.idle
                else self.scheduled.execute(step, context)
            )
            results.append(result)
            context.record_step(result)
            if result["status"] != "completed":
                break
        return results
