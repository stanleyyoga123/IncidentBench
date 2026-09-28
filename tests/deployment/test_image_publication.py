"""Offline checks for the first-party image build and deployment contract."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


WORKSPACE = Path(__file__).resolve().parents[2]
IMAGE_CONFIG = WORKSPACE / "deployment/image_config.sh"
BUILD_SCRIPTS = {
    "mcp-tools": "Agents/MCPTools/build.sh",
    "learning-agent": "Agents/LearningAgent/build.sh",
    "rca-agent": "Agents/RCAAgent/build.sh",
    "remediator-agent": "Agents/RemediatorAgent/build.sh",
    "agent-orchestrator": "EvaluationPlatform/Orchestrator/build.sh",
    "anomaly-detector": "Agents/AnomalyDetector/build.sh",
    "database-job": "EvaluationPlatform/Orchestrator/Database/build.sh",
    "evaluation": "EvaluationPlatform/Runner/scripts/build.sh",
}
MANIFESTS = {
    "mcp-tools": [
        "Agents/MCPTools/kubernetes/investigation.yaml",
        "Agents/MCPTools/kubernetes/remediation.yaml",
    ],
    "learning-agent": ["Agents/LearningAgent/kubernetes/manifest.yaml"],
    "rca-agent": ["Agents/RCAAgent/kubernetes/manifest.yaml"],
    "remediator-agent": ["Agents/RemediatorAgent/kubernetes/manifest.yaml"],
    "agent-orchestrator": ["EvaluationPlatform/Orchestrator/kubernetes/manifest.yaml"],
    "anomaly-detector": ["Agents/AnomalyDetector/kubernetes/manifest.yaml"],
    "database-job": ["EvaluationPlatform/Orchestrator/Database/kubernetes/job.yaml"],
    "evaluation": ["EvaluationPlatform/Runner/kubernetes/pod.yaml"],
}
REGISTRY = "registry.example.test:5000/research"
TAG = "release_1.2"


def image_environment(**overrides):
    return {**os.environ, "IMAGE_REGISTRY": REGISTRY, "IMAGE_TAG": TAG, **overrides}


def test_build_scripts_push_the_configured_image_for_every_component(tmp_path):
    docker_log = tmp_path / "docker.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text('#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "$DOCKER_LOG"\n')
    fake_docker.chmod(0o755)
    env = image_environment(
        PATH=f"{fake_bin}:{os.environ['PATH']}", DOCKER_LOG=str(docker_log)
    )

    for component, script in BUILD_SCRIPTS.items():
        result = subprocess.run(
            ["bash", str(WORKSPACE / script)], env=env, capture_output=True, text=True
        )
        assert result.returncode == 0, f"{script}: {result.stderr}"

    calls = docker_log.read_text().splitlines()
    assert len(calls) == len(BUILD_SCRIPTS)
    for call, component in zip(calls, BUILD_SCRIPTS):
        assert call.startswith("buildx build ")
        assert f"--tag {REGISTRY}/{component}:{TAG}" in call
        assert "--push" in call


@pytest.mark.parametrize(
    "settings",
    [
        {"IMAGE_REGISTRY": "", "IMAGE_TAG": TAG},
        {"IMAGE_REGISTRY": REGISTRY, "IMAGE_TAG": ""},
        {"IMAGE_REGISTRY": "registry.example.test/team;bad", "IMAGE_TAG": TAG},
        {"IMAGE_REGISTRY": REGISTRY, "IMAGE_TAG": "bad tag"},
    ],
)
def test_build_rejects_missing_or_invalid_image_settings_before_docker(tmp_path, settings):
    docker_log = tmp_path / "docker.log"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_docker = fake_bin / "docker"
    fake_docker.write_text('#!/usr/bin/env bash\necho called >> "$DOCKER_LOG"\n')
    fake_docker.chmod(0o755)
    env = image_environment(
        PATH=f"{fake_bin}:{os.environ['PATH']}", DOCKER_LOG=str(docker_log), **settings
    )

    result = subprocess.run(
        ["bash", str(WORKSPACE / "build.sh"), "mcp-tools"],
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "IMAGE_" in result.stderr
    assert not docker_log.exists()


def test_rendered_manifests_use_configured_images_and_keep_upstream_images():
    for component, manifest_paths in MANIFESTS.items():
        for manifest_path in manifest_paths:
            source = WORKSPACE / manifest_path
            original = [doc for doc in yaml.safe_load_all(source.read_text()) if doc]
            script = 'source "$1"; validate_image_settings; render_image_manifest "$2" "$3"'
            result = subprocess.run(
                ["bash", "-c", script, "bash", str(IMAGE_CONFIG), str(source), component],
                env=image_environment(),
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, f"{manifest_path}: {result.stderr}"
            rendered = [doc for doc in yaml.safe_load_all(result.stdout) if doc]
            assert len(rendered) == len(original)

            original_images = _images(original)
            rendered_images = _images(rendered)
            marker = f"incidentbench.invalid/{component}:configure-me"
            assert marker in original_images
            assert rendered_images == [
                f"{REGISTRY}/{component}:{TAG}" if image == marker else image
                for image in original_images
            ]


def test_render_finishes_when_configured_image_equals_manifest_marker():
    manifest = WORKSPACE / MANIFESTS["mcp-tools"][0]
    script = 'source "$1"; validate_image_settings; render_image_manifest "$2" "$3"'

    result = subprocess.run(
        ["bash", "-c", script, "bash", str(IMAGE_CONFIG), str(manifest), "mcp-tools"],
        env=image_environment(IMAGE_REGISTRY="incidentbench.invalid", IMAGE_TAG="configure-me"),
        capture_output=True,
        text=True,
        timeout=3,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == manifest.read_text()


@pytest.mark.parametrize(
    ("component", "folder", "script"),
    [
        ("mcp-tools", "Agents/MCPTools", "deploy.sh"),
        ("learning-agent", "Agents/LearningAgent", "deploy.sh"),
        ("rca-agent", "Agents/RCAAgent", "deploy.sh"),
        ("remediator-agent", "Agents/RemediatorAgent", "deploy.sh"),
        ("agent-orchestrator", "EvaluationPlatform/Orchestrator", "deploy.sh"),
        ("anomaly-detector", "Agents/AnomalyDetector", "deploy.sh"),
        ("database-job", "EvaluationPlatform/Orchestrator/Database", "deploy.sh"),
        ("evaluation", "EvaluationPlatform/Runner", "scripts/deploy.sh"),
    ],
)
@pytest.mark.parametrize("missing_marker", [False, True])
def test_deploy_scripts_apply_rendered_image_or_fail_before_kubectl(
    tmp_path, component, folder, script, missing_marker
):
    sandbox = tmp_path / "workspace"
    source = WORKSPACE / folder
    target = sandbox / folder
    (sandbox / "deployment").mkdir(parents=True)
    shutil.copyfile(IMAGE_CONFIG, sandbox / "deployment/image_config.sh")
    (target / "kubernetes").mkdir(parents=True)
    for manifest in (source / "kubernetes").glob("*.yaml"):
        shutil.copyfile(manifest, target / "kubernetes" / manifest.name)
    for manifest in (source / "kubernetes").glob("*.yml"):
        if manifest.name != "secret.yml":
            shutil.copyfile(manifest, target / "kubernetes" / manifest.name)
    (target / script).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source / script, target / script)
    example_secret = (target / "kubernetes/secret.example.yml").read_text()
    (target / "kubernetes/secret.yml").write_text(
        example_secret.replace("++++++++", "test-value")
    )
    if component == "evaluation":
        inventory = sandbox / "EvaluationPlatform/Initialization/ansible/inventory.ini"
        inventory.parent.mkdir(parents=True)
        inventory.write_text("[servers]\nnode-1 ansible_host=192.0.2.1\n")
    if missing_marker:
        manifest = sandbox / MANIFESTS[component][0]
        marker = f"incidentbench.invalid/{component}:configure-me"
        assert marker in manifest.read_text()
        manifest.write_text(manifest.read_text().replace(marker, "example.invalid/absent:v1"))

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_kubectl = fake_bin / "kubectl"
    fake_kubectl.write_text(
        '#!/usr/bin/env bash\n'
        'printf "%s\\n" "$*" >> "$KUBECTL_LOG"\n'
        'if [[ "$*" == "config current-context" ]]; then echo test-context; exit 0; fi\n'
        'if [[ "$*" == "get deployment cloudagent -n agents" ]]; then exit 1; fi\n'
        'if [[ "$*" == *"create configmap"* ]]; then '
        'printf "apiVersion: v1\\nkind: ConfigMap\\nmetadata:\\n  name: test\\n"; exit 0; fi\n'
        'if [[ "$*" == *"apply"* && "$*" == *"-f -"* ]]; then '
        'cat >> "$APPLIED_MANIFESTS"; printf "\\n---\\n" >> "$APPLIED_MANIFESTS"; fi\n'
    )
    fake_kubectl.chmod(0o755)
    kubectl_log = tmp_path / "kubectl.log"
    applied = tmp_path / "applied.yaml"
    env = image_environment(
        PATH=f"{fake_bin}:{os.environ['PATH']}",
        KUBECTL_LOG=str(kubectl_log),
        APPLIED_MANIFESTS=str(applied),
    )

    result = subprocess.run(
        ["bash", str(target / script)], env=env, capture_output=True, text=True
    )

    if missing_marker:
        assert result.returncode != 0, folder
        assert "expected image marker" in result.stderr
        assert not kubectl_log.exists(), folder
        return

    assert result.returncode == 0, f"{folder}: {result.stderr}"
    assert "apply -f -" in kubectl_log.read_text()
    documents = [item for item in yaml.safe_load_all(applied.read_text()) if item]
    assert f"{REGISTRY}/{component}:{TAG}" in _images(documents)
    assert "configure-me" not in applied.read_text()
    for manifest_path in MANIFESTS[component]:
        assert "configure-me" in (sandbox / manifest_path).read_text()


def _images(documents):
    images = []
    for document in documents:
        spec = document.get("spec", {})
        if document["kind"] == "Pod":
            pod_spec = spec
        elif document["kind"] == "Job":
            pod_spec = spec["template"]["spec"]
        else:
            pod_spec = spec["template"]["spec"] if "template" in spec else {}
        images.extend(item["image"] for item in pod_spec.get("containers", []))
    return images
