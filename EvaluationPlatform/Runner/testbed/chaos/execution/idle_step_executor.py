import time

from ...domain.scenario import ScenarioStep
from .execution_context import ChaosExecutionContext
from .result_factory import finish_step, new_step_result


class IdleStepExecutor:
    def execute(self, step: ScenarioStep, context: ChaosExecutionContext) -> dict:
        result = new_step_result(step)
        context.log(f"chaos step {step.index}: idle for {step.duration}s")
        try:
            context.wait_until(step.duration, time.monotonic())
        except KeyboardInterrupt:
            result["error"] = "interrupted by user"
            return finish_step(result, "interrupted")
        return finish_step(result, "completed")
