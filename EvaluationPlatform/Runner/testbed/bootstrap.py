import subprocess
import time
from pathlib import Path

from .artifacts.artifact_layout import ArtifactLayout
from .artifacts.input_artifact_archiver import InputArtifactArchiver
from .artifacts.metadata_factory import MetadataFactory
from .artifacts.metadata_repository import MetadataRepository
from .applications import ApplicationCatalog
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
from .constants import INFRASTRUCTURE_ROOT
from .domain.experiment_config import ExperimentConfig
from .domain.experiment_context import ExperimentContext
from .domain.errors import UnsafeCleanupError
from hooks.lifecycle import IntegrationController
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
    workspace_root = repo_root.parents[1]
    application_catalog = ApplicationCatalog(
        repo_root / "resources/applications",
        workspace_root,
    )
    application_reference = ScenarioLoader.application_reference(
        repo_root,
        args.scenario,
    )
    application_profile = application_catalog.resolve(application_reference)
    args.application = application_profile.id
    args.loadgenerator_module = application_profile.loadgenerator_module
    args.startup_delay_seconds = application_profile.startup_delay_seconds
    args.port_forward_service = application_profile.port_forward_service
    args.port_forward_remote_port = application_profile.port_forward_remote_port
    if args.namespace is None:
        args.namespace = application_profile.namespace
    elif args.namespace != application_profile.namespace:
        raise ValueError(
            f"scenario application {application_profile.id} requires namespace "
            f"{application_profile.namespace}; got {args.namespace}"
        )
    if args.host is None:
        args.host = (
            f"http://localhost:{args.port_forward_port}"
            if args.port_forward
            else application_profile.host
        )
    command_runner = CommandRunner(run_function)
    from .chaos.catalog.schedule_loader import ScheduleLoader
    catalog = ChaosCatalog(repo_root / "resources" / "chaos", ScheduleLoader(node_ips=args.node_ips))
    if application_profile.placement.mode == "rendered":
        placement_root = (
            application_profile.installer.install_source(workspace_root) / "overlays"
        )
        placement_marker = "kustomization.yaml"
    else:
        placement_root = application_profile.placement_root(workspace_root)
        placement_marker = "profile.yaml"
    placement_catalog = PlacementCatalog(placement_root, marker=placement_marker)
    scenario = ScenarioLoader(
        repo_root,
        catalog,
        placement_catalog,
        application_catalog,
    ).load(args.scenario)
    placement_source = placement_catalog.resolve(scenario.placement)
    placement_renderer = PlacementRenderer(
        command_runner,
        repo_root,
        application_profile=application_profile,
    )
    placement = (
        placement_renderer.render(scenario.placement, placement_source)
        if application_profile.placement.mode == "rendered"
        else placement_renderer.render_live(
            scenario.placement,
            placement_source,
            application_profile.namespace,
        )
    )
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
    validate_pod_chaos_selectors(
        placement,
        schedules,
        application_profile.placement.label_key,
    )
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
    metadata["application_profile"] = application_profile.to_metadata(workspace_root)
    install_artifact = output_dir / "application-install.json"
    metadata["application_install_artifact"] = (
        str(install_artifact) if install_artifact.is_file() else None
    )
    metadata_store.write(metadata)
    evaluator = evaluator_factory(
        output_dir=output_dir,
        namespace=config.namespace,
        prometheus_url=config.prometheus_url,
    )
    kubectl = KubectlClient(command_runner, repo_root)
    agents = IntegrationController(args.lifecycle)
    application = ApplicationDeploymentController(
        command_runner,
        kubectl,
        artifacts,
        command_logger,
        repo_root,
        application_profile=application_profile,
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
        ApplicationResetPhase(
            application,
            placement,
            metadata_store,
            log,
        ),
        PortForwardPhase(port_forward, metadata_store, log),
        BaselinePhase(load_launcher, wait_until, metadata_store, log, sleep=sleep),
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
