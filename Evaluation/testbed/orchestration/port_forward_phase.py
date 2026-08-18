from ..domain.phase_result import PhaseResult
from ..kubernetes.port_forward import PortForwardController
from .phase_support import PhaseSupport


class PortForwardPhase(PhaseSupport):
    name = "port_forward"

    def __init__(self, controller: PortForwardController, metadata, log) -> None:
        super().__init__(metadata, log)
        self.controller = controller

    def execute(self, context):
        if not context.config.port_forward:
            self.log("port-forward phase skipped")
            return self.record(context, PhaseResult.success(self.name, skipped=True))
        port = context.config.port_forward_port
        self.log(f"port-forward phase: forwarding svc/frontend to localhost:{port}")
        process, result = self.controller.start(context.config.namespace, port)
        context.port_forward_process = process
        context.metadata["commands"]["port_forward_frontend"] = result
        if result["returncode"] != 0:
            return self.record(context, PhaseResult.failure(self.name, result["returncode"], command=result))
        return self.record(context, PhaseResult.success(self.name, already_running=result["already_running"]))
