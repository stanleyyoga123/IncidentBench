"""Image build contexts keep local credentials out and include Docker COPY inputs."""

from pathlib import Path
import re

import pytest


WORKSPACE = Path(__file__).resolve().parents[2]
COMPONENTS = [
    "Agents/AnomalyDetector",
    "Agents/LearningAgent",
    "Agents/MCPTools",
    "Agents/RCAAgent",
    "Agents/RemediatorAgent",
    "EvaluationPlatform/Orchestrator",
    "EvaluationPlatform/Orchestrator/Database",
]


def test_root_runner_context_excludes_local_environment_variants_and_vault_password():
    ignore = (WORKSPACE / ".dockerignore").read_text().splitlines()

    assert "**/.env" in ignore
    assert "**/.env.*" in ignore
    assert "**/.vault-password" in ignore
    assert "**/kubernetes/secret.yml" in ignore


@pytest.mark.parametrize("component", COMPONENTS)
def test_component_allowlist_includes_every_docker_copy_input(component):
    root = WORKSPACE / component
    ignore = (root / ".dockerignore").read_text().splitlines()
    dockerfile = (root / "Dockerfile").read_text()

    assert ignore[0].startswith("#")
    assert "*" in ignore
    assert "**/.env.*" in ignore
    assert "**/secret.yml" in ignore
    sources = re.findall(r"^COPY\s+(\S+)", dockerfile, flags=re.MULTILINE)
    assert sources
    for source in sources:
        path = root / source
        assert path.exists(), (component, source)
        if path.is_dir():
            assert f"!{source}/" in ignore, (component, source)
            assert f"!{source}/**" in ignore, (component, source)
        else:
            assert f"!{source}" in ignore, (component, source)
