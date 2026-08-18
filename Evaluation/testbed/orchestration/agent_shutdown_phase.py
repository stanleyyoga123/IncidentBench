from ..domain.phase_result import PhaseResult
from ..kubernetes.agent_deployments import AgentDeploymentController
from .phase_support import PhaseSupport, failed_command


class AgentShutdownPhase(PhaseSupport):
    name = "agent_shutdown"

    def __init__(self, controller: AgentDeploymentController, metadata, log) -> None:
        super().__init__(metadata, log)
        self.controller = controller

    def execute(self, context):
        namespace = context.config.agent_namespace
        self.log(f"agent phase: scaling the split agent platform to 0 in namespace {namespace}")
        scale = self.controller.scale(namespace, 0)
        context.metadata["commands"]["agents_scale_down"] = scale
        failure = failed_command(scale)
        if failure:
            return self.record(context, PhaseResult.failure(self.name, failure["returncode"], command=failure))
        wait = self.controller.wait(namespace, 0)
        context.metadata["commands"]["agents_wait_down"] = wait
        if wait["returncode"] != 0:
            return self.record(context, PhaseResult.failure(self.name, wait["returncode"], command=wait))
        return self.record(context, PhaseResult.success(self.name))
