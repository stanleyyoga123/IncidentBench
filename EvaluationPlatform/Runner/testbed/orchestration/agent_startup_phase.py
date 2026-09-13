import time

from ..domain.phase_result import PhaseResult
from hooks.lifecycle import IntegrationController
from .phase_support import PhaseSupport, failed_command


class AgentStartupPhase(PhaseSupport):
    name = "agent_startup"

    def __init__(self, controller: IntegrationController, metadata, log, sleep=time.sleep) -> None:
        super().__init__(metadata, log)
        self.controller = controller
        self.sleep = sleep

    def execute(self, context):
        if not context.config.agents_enabled:
            self.log("agent phase skipped: agents remain scaled to 0")
            return self.record(context, PhaseResult.success(self.name, skipped=True))
        namespace = context.config.agent_namespace
        self.log(f"agent phase: scaling the split agent platform to 1 in namespace {namespace}")
        scale = self.controller.scale(namespace, 1)
        context.metadata["commands"]["agents_scale_up"] = scale
        failure = failed_command(scale)
        if failure:
            return self.record(context, PhaseResult.failure(self.name, failure["returncode"], command=failure))
        wait = self.controller.wait(namespace, 1)
        context.metadata["commands"]["agents_wait_up"] = wait
        if wait["returncode"] != 0:
            return self.record(context, PhaseResult.failure(self.name, wait["returncode"], command=wait))
        self.log(f"grace phase: waiting {context.config.grace_period}s")
        self.sleep(context.config.grace_period)
        return self.record(context, PhaseResult.success(self.name))
