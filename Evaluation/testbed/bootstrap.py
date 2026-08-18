import subprocess
import time
from pathlib import Path

from .artifacts.artifact_layout import ArtifactLayout
from .artifacts.input_artifact_archiver import InputArtifactArchiver
from .artifacts.metadata_factory import MetadataFactory
from .artifacts.metadata_repository import MetadataRepository
from .chaos.execution.chaos_phase_executor import ChaosPhaseExecutor
from .chaos.execution.cluster_chaos_state_cleaner import ClusterChaosStateCleaner
from .chaos.execution.execution_context import ChaosExecutionContext
from .chaos.execution.schedule_cleaner import ScheduleCleaner
from .chaos.execution.physical_machine_state_cleaner import (
    PhysicalMachineStateCleaner,
)
from .chaos.execution.scheduled_step_executor import ScheduledStepExecutor
from .chaos.catalog.chaos_catalog import ChaosCatalog
from .cli import default_output_dir
from .command.command_logger import CommandLogger
from .command.command_runner import CommandRunner
from .constants import INFRASTRUCTURE_ROOT, ONLINE_BOUTIQUE_KUSTOMIZE_ROOT
from .domain.experiment_config import ExperimentConfig
from .domain.experiment_context import ExperimentContext
from .domain.errors import UnsafeCleanupError
from .kubernetes.agent_deployments import AgentDeploymentController
from .kubernetes.application_deployments import ApplicationDeploymentController
from .kubernetes.chaos_schedule_client import ChaosScheduleClient
from .kubernetes.kubectl_client import KubectlClient
from .kubernetes.port_forward import PortForwardController
from .orchestration.agent_shutdown_phase import AgentShutdownPhase
from .orchestration.agent_startup_phase import AgentStartupPhase
from .orchestration.application_reset_phase import ApplicationResetPhase
from .orchestration.baseline_phase import BaselinePhase
from .orchestration.chaos_phase import ChaosPhase
from .orchestration.experiment_runner import ExperimentRunner
from .orchestration.finalization_phase import FinalizationPhase
from .orchestration.metrics_phase import MetricsPhase
from .orchestration.port_forward_phase import PortForwardPhase
from .placement import (
    PlacementCatalog,
    PlacementRenderer,
    validate_pod_chaos_selectors,
)
from .scenarios.scenario_loader import ScenarioLoader


def build_and_run(
    args,
    *,
    evaluator_factory,
    load_launcher,
    wait_until,
    log,
    run_function=subprocess.run,
    popen=subprocess.Popen,
    sleep=time.sleep,
) -> int:
    repo_root = Path(__file__).resolve().parents[1]
    if args.port_forward and args.host == "http://localhost:8888":
        args.host = f"http://localhost:{args.port_forward_port}"
    command_runner = CommandRunner(run_function)
    catalog = ChaosCatalog(repo_root / "collections" / "chaos")
    placement_catalog = PlacementCatalog(
        ONLINE_BOUTIQUE_KUSTOMIZE_ROOT / "overlays"
    )
    scenario = ScenarioLoader(repo_root, catalog, placement_catalog).load(args.scenario)
    placement_source = placement_catalog.resolve(scenario.placement)
    placement_renderer = PlacementRenderer(command_runner, repo_root)
    placement = placement_renderer.render(
        scenario.placement,
        placement_source,
    )
    default_placement = placement_renderer.render(
        scenario.placement,
        ONLINE_BOUTIQUE_KUSTOMIZE_ROOT,
    )
    if default_placement.rendered_sha256 != placement.rendered_sha256:
        raise ValueError(
            "Infrastructure/kubernetes/online-boutique/kustomize does not "
            "render the scenario-selected "
            f"placement: {scenario.placement}"
        )
    validate_pod_chaos_selectors(placement, catalog.schedules)
    output_dir = args.output_dir or default_output_dir(repo_root, args.loadgenerator)
    if not output_dir.is_absolute():
        output_dir = repo_root / output_dir
    artifacts = ArtifactLayout(output_dir)
    artifacts.ensure_root()
    command_logger = CommandLogger()
    cluster_chaos_cleaner = ClusterChaosStateCleaner(
        command_runner,
        repo_root,
        command_logger,
    )
    startup_chaos_cleanup = cluster_chaos_cleaner.clean(
        artifacts.phase_commands("chaos-startup-full-cleanup"),
    )
    if startup_chaos_cleanup["returncode"] != 0:
        raise UnsafeCleanupError(
            "cluster or worker-node chaos cleanup failed before startup; "
            f"see {artifacts.phase_commands('chaos-startup-full-cleanup')}"
        )
    physical_machine_cleaner = PhysicalMachineStateCleaner(
        command_runner,
        repo_root,
        command_logger,
    )
    referenced_schedules = tuple(
        dict.fromkeys(
            reference
            for step in scenario.steps
            for reference in step.chaos
        )
    )
    schedules = catalog.resolve_many(referenced_schedules)
    archived_schedules = InputArtifactArchiver(artifacts).archive(
        scenario,
        schedules,
        placement,
    )
    config = ExperimentConfig.from_namespace(args, repo_root, output_dir)
    metadata_store = MetadataRepository(artifacts.metadata)
    metadata = MetadataFactory.create(
        config,
        scenario,
        args,
        schedules,
        archived_schedules,
        placement,
        artifacts.archived_placement_source,
        artifacts.archived_placement_render,
    )
    metadata_store.write(metadata)
    evaluator = evaluator_factory(
        output_dir=output_dir,
        namespace=config.namespace,
        prometheus_url=config.prometheus_url,
    )
    kubectl = KubectlClient(command_runner, repo_root)
    agents = AgentDeploymentController(
        kubectl,
        artifacts,
        command_logger,
        sleep=sleep,
    )
    application = ApplicationDeploymentController(
        command_runner,
        kubectl,
        artifacts,
        command_logger,
        repo_root,
        infrastructure_root=INFRASTRUCTURE_ROOT,
    )
    port_forward = PortForwardController(
        repo_root,
        artifacts,
        popen=popen,
        sleep=sleep,
    )
    schedule_client = ChaosScheduleClient(
        command_runner,
        repo_root,
        manifest_paths=archived_schedules,
    )
    schedule_cleaner = ScheduleCleaner(
        schedule_client,
        command_logger,
        physical_machine_cleaner,
        sleep=sleep,
    )
    scheduled_executor = ScheduledStepExecutor(
        catalog,
        schedule_client,
        schedule_cleaner,
        command_logger,
    )
    chaos_context = ChaosExecutionContext(
        artifacts=artifacts,
        wait_until=wait_until,
        log=log,
        record_step=lambda result: _record_chaos_step(
            metadata,
            metadata_store,
            result,
        ),
    )
    phases = [
        AgentShutdownPhase(agents, metadata_store, log),
        ApplicationResetPhase(
            application,
            placement,
            metadata_store,
            log,
        ),
        PortForwardPhase(port_forward, metadata_store, log),
        BaselinePhase(load_launcher, wait_until, metadata_store, log),
        AgentStartupPhase(agents, metadata_store, log, sleep=sleep),
        ChaosPhase(
            ChaosPhaseExecutor(scheduled_executor),
            chaos_context,
            metadata_store,
            log,
        ),
        MetricsPhase(metadata_store, log),
    ]
    finalizer = FinalizationPhase(
        agents,
        cluster_chaos_cleaner,
        metadata_store,
        log,
    )
    context = ExperimentContext(
        config=config,
        scenario=scenario,
        metadata=metadata,
        evaluator=evaluator,
    )
    log(
        f"starting experiment: loadgenerator={config.loadgenerator}, "
        f"scenario={scenario.name}, output_dir={output_dir}"
    )
    return ExperimentRunner(phases, finalizer, metadata_store, log).run(context)


def _record_chaos_step(metadata, repository, result) -> None:
    metadata["chaos_steps"].append(result)
    repository.write(metadata)
