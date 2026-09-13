import subprocess
from datetime import datetime, timezone

from ..domain.errors import UnsafeCleanupError
from ..domain.phase_result import PhaseResult
from hooks.lifecycle import IntegrationController
from .phase_support import PhaseSupport, failed_command


class FinalizationPhase(PhaseSupport):
    name = "finalization"

    def __init__(
        self,
        agents: IntegrationController,
        chaos_cleaner,
        metadata,
        log,
    ) -> None:
        super().__init__(metadata, log)
        self.agents = agents
        self.chaos_cleaner = chaos_cleaner

    def execute(self, context):
        if context.load_process is not None:
            self.log("stopping locust")
            try:
                context.metadata["loadgenerator"]["returncode"] = (
                    context.load_process.stop()
                )
            except Exception as exc:
                context.metadata["loadgenerator_stop_error"] = repr(exc)
        process = context.port_forward_process
        if process is not None and process.poll() is None:
            self.log("stopping frontend port-forward")
            try:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            except Exception as exc:
                context.metadata["port_forward_stop_error"] = repr(exc)
        cleanup_error = None
        try:
            self.log("final phase: removing all cluster and worker-node chaos state")
            output = context.config.output_dir / "commands" / "chaos-final-full-cleanup"
            cleanup = self.chaos_cleaner.clean(output)
            context.metadata.setdefault("commands", {})[
                "chaos_final_full_cleanup"
            ] = cleanup
            if cleanup["returncode"] != 0:
                cleanup_error = (
                    "cluster or worker-node chaos cleanup failed "
                    f"with exit {cleanup['returncode']}; see {output}"
                )
                context.metadata["chaos_final_cleanup_error"] = cleanup_error
        except Exception as exc:
            cleanup_error = f"cluster or worker-node chaos cleanup raised {exc!r}"
            context.metadata["chaos_final_cleanup_error"] = cleanup_error
        try:
            self.log("final phase: collecting snapshot")
            context.metadata["snapshots"].append(context.evaluator.collect_snapshot("final"))
        except Exception as exc:
            context.metadata["final_snapshot_error"] = repr(exc)
        if context.run_started_wall is not None and not context.metrics_collected:
            try:
                self.log("final phase: collecting Prometheus metrics")
                context.metadata["metrics"] = context.evaluator.collect_metrics(
                    start=context.run_started_wall,
                    end=context.experiment_finished_wall or datetime.now(timezone.utc),
                    rate_window="1m",
                    step_seconds=15,
                )
            except Exception as exc:
                context.metadata["final_metrics_error"] = repr(exc)
        try:
            self.log(f"final agent phase: scaling the split agent platform to 0 in namespace {context.config.agent_namespace}")
            output = context.config.output_dir / "commands" / "final-agent-scale-down"
            scale = self.agents.scale(context.config.agent_namespace, 0, output)
            context.metadata["commands"]["agents_final_scale_down"] = scale
            if failed_command(scale):
                context.metadata["final_agent_scale_down_error"] = scale.get("error", "integration stop failed")
            else:
                wait = self.agents.wait(context.config.agent_namespace, 0, output)
                context.metadata["commands"]["agents_final_wait_down"] = wait
                if failed_command(wait):
                    context.metadata["final_agent_scale_down_error"] = "integration stop wait failed"
        except Exception as exc:
            context.metadata["final_agent_scale_down_error"] = repr(exc)
        context.metadata["finished_at"] = datetime.now(timezone.utc).isoformat()
        if cleanup_error is not None or context.metadata.get("final_agent_scale_down_error"):
            raise UnsafeCleanupError(cleanup_error or context.metadata["final_agent_scale_down_error"])
        return self.record(context, PhaseResult.success(self.name))
