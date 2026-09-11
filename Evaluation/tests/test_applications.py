import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import yaml

from testbed.applications import ApplicationCatalog
from testbed.applications.application_profile import (
    ApplicationProfile,
    InstallerProfile,
    PlacementSettings,
)
from testbed.applications.installers import ApplicationInstaller
from testbed.domain import CommandResult
from testbed.loadgenerator.runner import start_locust
from testbed.scenarios.scenario_loader import ScenarioLoader


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        if command[:3] == ["kubectl", "get", "deployments"]:
            return CommandResult(tuple(command), 0, json.dumps({"items": []}), "")
        return CommandResult(tuple(command), 0, "", "")


def _script_profile(tmp: Path, required_files=("chart/Chart.yaml",)) -> ApplicationProfile:
    app_dir = Path(tmp) / "applications" / "demo-app"
    app_dir.mkdir(parents=True)
    (app_dir / "install.sh").write_text("#!/bin/bash\n")
    profile_path = app_dir / "profile.yaml"
    profile_path.write_text("id: demo-app\n")
    return ApplicationProfile(
        id="demo-app",
        namespace="demo-app",
        host="http://demo-app",
        port_forward_service="demo-ui",
        port_forward_remote_port=8080,
        loadgenerator_module="applications.demo_app",
        startup_delay_seconds=0,
        installer=InstallerProfile(
            type="script",
            source_environment="DEMO_APP_ROOT",
            source_default="unused",
            path=".",
            script="install.sh",
            timeout="60m",
            required_files=required_files,
        ),
        placement=PlacementSettings(
            mode="rendered",
            root="applications/demo-app/placements",
            workload_names=("demo-ui",),
            workload_prefixes=(),
            label_key="app",
            node_selector_key="role",
            node_selector_value="services",
        ),
        source_path=profile_path,
    )


def test_application_catalog_exposes_online_boutique_and_teastore():
    catalog = ApplicationCatalog(ROOT / "applications", WORKSPACE)
    assert catalog.references == ("online-boutique", "teastore")
    boutique = catalog.resolve("online-boutique")
    assert boutique.installer.type == "kustomize"
    assert boutique.installer.source_root(WORKSPACE) == (
        ROOT / "applications" / "online-boutique"
    )
    teastore = catalog.resolve("teastore")
    assert teastore.installer.type == "kustomize"
    assert teastore.namespace == "teastore"
    assert teastore.port_forward_service == "teastore-webui"
    assert teastore.host.endswith("/tools.descartes.teastore.webui")
    assert teastore.loadgenerator_module == "applications.teastore"
    assert teastore.startup_delay_seconds == 180
    assert boutique.startup_delay_seconds == 0
    assert teastore.installer.source_root(WORKSPACE) == (
        ROOT / "applications" / "teastore"
    )


def test_teastore_uses_clusterip_and_unique_app_labels():
    from testbed.command.command_runner import CommandRunner
    from testbed.placement import PlacementRenderer

    catalog = ApplicationCatalog(ROOT / "applications", WORKSPACE)
    profile = catalog.resolve("teastore")
    overlay = (
        ROOT / "applications" / "teastore" / "kustomize" / "overlays"
        / "canonical-six-node"
    )
    placement = PlacementRenderer(
        CommandRunner(), ROOT, application_profile=profile
    ).render("canonical-six-node", overlay)
    assert "USE_POD_IP" not in placement.rendered_manifest
    documents = [
        document
        for document in yaml.safe_load_all(placement.rendered_manifest)
        if document
    ]
    services = {
        document["metadata"]["name"]: document
        for document in documents
        if document.get("kind") == "Service"
    }
    assert services["teastore-webui"]["spec"]["type"] == "ClusterIP"
    assert services["teastore-webui-external"]["spec"]["type"] == "NodePort"
    assert services["teastore-webui-external"]["spec"]["ports"][0]["nodePort"] == 30081
    for name in profile.placement.workload_names:
        if name == "teastore-webui":
            continue
        assert services[name]["spec"]["type"] == "ClusterIP"
        assert services[name]["spec"]["selector"] == {"app": name}
    deployments = {
        document["metadata"]["name"]: document
        for document in documents
        if document.get("kind") == "Deployment"
    }
    assert deployments["teastore-webui"]["spec"]["replicas"] == 6
    assert deployments["teastore-db"]["spec"]["replicas"] == 1
    assert deployments["teastore-registry"]["spec"]["replicas"] == 1
    assert deployments["teastore-db"]["spec"]["template"]["metadata"]["annotations"][
        "sidecar.istio.io/inject"
    ] == "false"
    hpas = {
        document["metadata"]["name"]
        for document in documents
        if document.get("kind") == "HorizontalPodAutoscaler"
    }
    assert "teastore-registry-hpa" not in hpas
    assert "teastore-db-hpa" not in hpas
    expected_resources = {
        "teastore-webui": (("500m", "1Gi"), ("1000m", "2Gi")),
        "teastore-auth": (("250m", "1Gi"), ("500m", "2Gi")),
        "teastore-registry": (("250m", "512Mi"), ("500m", "1Gi")),
        "teastore-db": (("250m", "512Mi"), ("500m", "1Gi")),
        "teastore-persistence": (("500m", "1Gi"), ("1000m", "2Gi")),
        "teastore-image": (("750m", "1Gi"), ("1500m", "2Gi")),
        "teastore-recommender": (("250m", "1Gi"), ("500m", "2Gi")),
    }
    for name, ((cpu_req, mem_req), (cpu_lim, mem_lim)) in expected_resources.items():
        resources = deployments[name]["spec"]["template"]["spec"]["containers"][0][
            "resources"
        ]
        assert resources["requests"] == {"cpu": cpu_req, "memory": mem_req}, name
        assert resources["limits"] == {"cpu": cpu_lim, "memory": mem_lim}, name

    webui_hpa = next(
        document
        for document in documents
        if document.get("kind") == "HorizontalPodAutoscaler"
        and document["metadata"]["name"] == "teastore-webui-hpa"
    )
    assert webui_hpa["spec"]["minReplicas"] == 6
    assert webui_hpa["spec"]["maxReplicas"] == 30



def test_evaluation_image_includes_namespace_access_policy():
    dockerfile = (ROOT / "Dockerfile").read_text()
    assert (
        "COPY MCPTools/kubernetes/application-role-binding.yaml "
        "/MCPTools/kubernetes/application-role-binding.yaml"
    ) in dockerfile


def test_existing_scenario_defaults_to_online_boutique_application():
    assert ScenarioLoader.application_reference(
        ROOT,
        ROOT / "collections" / "online-boutique-scenario" / "01-node-delay-worker-3.json",
    ) == "online-boutique"
    with tempfile.TemporaryDirectory() as tmp:
        scenario = Path(tmp) / "scenario.json"
        scenario.write_text(
            json.dumps({"name": "legacy", "placement": "canonical-six-node", "steps": []})
        )
        assert ScenarioLoader.application_reference(ROOT, scenario) == "online-boutique"


def test_script_installer_missing_source_fails_before_any_cluster_command():
    with tempfile.TemporaryDirectory() as tmp:
        profile = _script_profile(Path(tmp))
        runner = FakeRunner()
        with patch.dict(os.environ, {"DEMO_APP_ROOT": str(Path(tmp) / "missing")}):
            installer = ApplicationInstaller(runner, ROOT, WORKSPACE)
            try:
                installer.validate(profile, "canonical-six-node")
            except FileNotFoundError as exc:
                assert "DEMO_APP_ROOT" in str(exc)
            else:
                raise AssertionError("missing script-installer source was accepted")
        assert runner.calls == []


def test_script_installer_rejects_incomplete_source():
    with tempfile.TemporaryDirectory() as tmp:
        required = ("a.yaml", "b.yaml")
        profile = _script_profile(Path(tmp), required_files=required)
        source = Path(tmp) / "source"
        (source / "a.yaml").parent.mkdir(parents=True, exist_ok=True)
        (source / "a.yaml").write_text("safe\n")
        with patch.dict(os.environ, {"DEMO_APP_ROOT": str(source)}), patch(
            "testbed.applications.installers.shutil.which", return_value="/usr/bin/helm"
        ):
            installer = ApplicationInstaller(FakeRunner(), ROOT, WORKSPACE)
            try:
                installer.validate(profile, "canonical-six-node")
            except FileNotFoundError as exc:
                assert "source is incomplete" in str(exc)
            else:
                raise AssertionError("incomplete script-installer source was accepted")


def test_script_installer_runs_owned_script_and_binds_namespace_access():
    with tempfile.TemporaryDirectory() as tmp:
        required = ("chart/Chart.yaml",)
        profile = _script_profile(Path(tmp), required_files=required)
        source = Path(tmp) / "source"
        for relative in required:
            path = source / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("safe\n")
        runner = FakeRunner()
        with patch.dict(os.environ, {"DEMO_APP_ROOT": str(source)}), patch(
            "testbed.applications.installers.shutil.which", return_value="/usr/bin/helm"
        ):
            ApplicationInstaller(runner, ROOT, WORKSPACE).install(
                profile,
                "canonical-six-node",
            )
        script = next(
            command
            for command, _ in runner.calls
            if command and command[0] == "bash"
        )
        assert script == [
            "bash",
            str(profile.source_path.parent / "install.sh"),
            str(source.resolve()),
            "demo-app",
        ]
        timeout = next(
            kwargs.get("timeout")
            for command, kwargs in runner.calls
            if command and command[0] == "bash"
        )
        assert timeout == 3660
        assert [
            "kubectl", "apply", "--namespace", "demo-app", "-f",
            str(WORKSPACE / "MCPTools/kubernetes/application-role-binding.yaml"),
        ] in [command for command, _ in runner.calls]
        commands = [command for command, _ in runner.calls]
        for resource in (
            "deployments.apps",
            "horizontalpodautoscalers.autoscaling",
        ):
            assert [
                "kubectl", "auth", "can-i", "patch", resource,
                "--namespace", "demo-app", "--as",
                "system:serviceaccount:agents:mcp-tools-remediation", "--quiet",
            ] in commands


def test_kustomize_installs_the_scenario_selected_overlay():
    catalog = ApplicationCatalog(ROOT / "applications", WORKSPACE)
    original = catalog.resolve("online-boutique")
    with tempfile.TemporaryDirectory() as tmp:
        application_root = Path(tmp)
        overlay = (
            application_root
            / "kustomize"
            / "overlays"
            / "selected"
        )
        overlay.mkdir(parents=True)
        (overlay / "kustomization.yaml").write_text("kind: Kustomization\n")
        root = application_root / "kustomize"
        (root / "kustomization.yaml").write_text("kind: Kustomization\n")
        installer_profile = replace(
            original.installer,
            source_environment="TEST_ONLINE_BOUTIQUE_ROOT",
            source_default="unused",
        )
        profile = replace(original, installer=installer_profile)
        runner = FakeRunner()
        with patch.dict(
            os.environ,
            {"TEST_ONLINE_BOUTIQUE_ROOT": str(application_root)},
        ), patch("testbed.applications.installers.shutil.which", return_value="/usr/bin/kubectl"):
            ApplicationInstaller(runner, ROOT, WORKSPACE).install(profile, "selected")
        commands = [call[0] for call in runner.calls]
        assert [
            "kubectl",
            "apply",
            "-k",
            str(overlay.resolve()),
            "--namespace",
            "online-boutique",
        ] in commands


def test_catalog_other_namespaces_excludes_the_selected_application():
    catalog = ApplicationCatalog(ROOT / "applications", WORKSPACE)
    assert catalog.other_namespaces("teastore") == ("online-boutique",)
    assert catalog.other_namespaces("online-boutique") == ("teastore",)


def test_kustomize_install_deletes_sibling_application_namespaces_first():
    catalog = ApplicationCatalog(ROOT / "applications", WORKSPACE)
    original = catalog.resolve("teastore")
    with tempfile.TemporaryDirectory() as tmp:
        application_root = Path(tmp)
        overlay = application_root / "kustomize" / "overlays" / "selected"
        overlay.mkdir(parents=True)
        (overlay / "kustomization.yaml").write_text("kind: Kustomization\n")
        (application_root / "kustomize" / "kustomization.yaml").write_text(
            "kind: Kustomization\n"
        )
        profile = replace(
            original,
            installer=replace(
                original.installer,
                source_environment="TEST_TEASTORE_ROOT",
                source_default="unused",
            ),
        )
        runner = FakeRunner()
        with patch.dict(
            os.environ,
            {"TEST_TEASTORE_ROOT": str(application_root)},
        ), patch(
            "testbed.applications.installers.shutil.which",
            return_value="/usr/bin/kubectl",
        ):
            ApplicationInstaller(runner, ROOT, WORKSPACE).install(
                profile,
                "selected",
                clear_namespaces=("online-boutique",),
            )
        commands = [call[0] for call in runner.calls]
        assert commands.index(
            [
                "kubectl",
                "delete",
                "namespace",
                "online-boutique",
                "--ignore-not-found=true",
                "--wait=true",
                "--timeout=10m",
            ]
        ) < commands.index(
            [
                "kubectl",
                "delete",
                "namespace",
                "teastore",
                "--ignore-not-found=true",
                "--wait=true",
                "--timeout=10m",
            ]
        )


def test_locust_launcher_composes_shape_with_application_behavior():
    class Process:
        returncode = None

        def poll(self):
            return None

    with tempfile.TemporaryDirectory() as tmp, patch(
        "testbed.loadgenerator.runner.subprocess.Popen", return_value=Process()
    ):
        output = Path(tmp)
        start_locust(
            ROOT,
            output,
            "constant",
            "applications.teastore",
            "http://teastore",
            60,
        )
        locustfile = output / "loadgenerator" / "locustfile.py"
        text = locustfile.read_text()
        assert "from applications.teastore import *" in text
        assert "loadgenerator.constant" in text
