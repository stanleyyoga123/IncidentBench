from ..domain.phase_result import PhaseResult
from ..kubernetes.application_deployments import ApplicationDeploymentController
from .phase_support import PhaseSupport


class ApplicationResetPhase(PhaseSupport):
    name = "application_reset"

    def __init__(
        self,
        controller: ApplicationDeploymentController,
        placement,
        metadata,
        log,
    ) -> None:
        super().__init__(metadata, log)
        self.controller = controller
        self.placement = placement

    def execute(self, context):
        self.log(
            f"placement normalization: uncordoning {self.placement.reference} nodes"
        )
        normalization = self.controller.normalize_nodes(self.placement)
        context.metadata["placement"]["normalization"] = normalization
        context.metadata["commands"]["placement_normalization"] = normalization
        if normalization["returncode"] != 0:
            return self.record(
                context,
                PhaseResult.failure(
                    self.name,
                    normalization["returncode"],
                    command=normalization,
                ),
            )
        self.log(
            f"placement preflight: validating {self.placement.reference} nodes"
        )
        preflight = self.controller.preflight(self.placement)
        context.metadata["placement"]["preflight"] = preflight
        context.metadata["commands"]["placement_preflight"] = preflight
        if preflight["returncode"] != 0:
            return self.record(
                context,
                PhaseResult.failure(
                    self.name,
                    preflight["returncode"],
                    command=preflight,
                ),
            )
        self.log("rollout phase: waiting for deployments to become ready")
        rollout = self.controller.wait_for_rollouts(context.config.namespace)
        context.metadata["commands"]["rollout_status"] = rollout
        if rollout["returncode"] != 0:
            return self.record(
                context,
                PhaseResult.failure(
                    self.name,
                    rollout["returncode"],
                    command=rollout,
                ),
            )
        self.log("placement verification: checking live Deployments and pods")
        verification = self.controller.verify_placement(
            self.placement,
            context.config.namespace,
        )
        context.metadata["placement"]["verification"] = verification
        context.metadata["placement"]["observed_placement"] = verification.get(
            "observed_placement"
        )
        context.metadata["placement"][
            "observed_placement_fingerprint"
        ] = verification.get("observed_placement_fingerprint")
        context.metadata["commands"]["placement_verification"] = verification.get(
            "commands", {}
        )
        if verification["returncode"] != 0:
            return self.record(
                context,
                PhaseResult.failure(
                    self.name,
                    verification["returncode"],
                    command=verification,
                ),
            )
        self.log("application reset completed")
        return self.record(context, PhaseResult.success(self.name))
