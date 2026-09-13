import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


WORKSPACE = Path(__file__).resolve().parents[3]
CASES = [
    (
        WORKSPACE / "EvaluationPlatform/Orchestrator/kubernetes/configmap.yaml",
        "agent-orchestrator-config",
        WORKSPACE / "EvaluationPlatform/Orchestrator",
        "from app.config import get_settings; get_settings()",
    ),
    (
        WORKSPACE / "Agents/AnomalyDetector/kubernetes/configmap.yaml",
        "anomaly-detector-config",
        WORKSPACE / "Agents/AnomalyDetector/src",
        "from config import SETTINGS; assert set(SETTINGS.collector.metadata.namespaces) == {'online-boutique', 'teastore', 'sock-shop'}",
    ),
    (
        WORKSPACE / "Agents/MCPTools/kubernetes/configmap.yaml",
        "mcp-tools-investigation-config",
        WORKSPACE / "Agents/MCPTools",
        "from app.config import get_settings; get_settings()",
    ),
    (
        WORKSPACE / "Agents/MCPTools/kubernetes/configmap.yaml",
        "mcp-tools-remediation-config",
        WORKSPACE / "Agents/MCPTools",
        "from app.config import get_settings; get_settings()",
    ),
    (
        WORKSPACE / "Agents/RCAAgent/kubernetes/configmap.yaml",
        "rca-agent-config",
        WORKSPACE / "Agents/RCAAgent",
        "from app.config import get_settings; assert set(get_settings().workloads.namespaces) == {'online-boutique', 'teastore', 'sock-shop'}",
    ),
    (
        WORKSPACE / "Agents/RemediatorAgent/kubernetes/configmap.yaml",
        "remediator-agent-config",
        WORKSPACE / "Agents/RemediatorAgent",
        "from app.config import get_settings; get_settings()",
    ),
]


def configmap_env(path: Path, name: str) -> str:
    documents = [document for document in yaml.safe_load_all(path.read_text()) if document]
    return next(
        document["data"][".env"]
        for document in documents
        if document["metadata"]["name"] == name
    )


def test_configmap_env_files_load_with_injected_secret_values(tmp_path):
    for path, name, python_path, statement in CASES:
        env_text = configmap_env(path, name)
        runtime_env = os.environ.copy()
        for variable in re.findall(r"\$\{([A-Z_]+)\}", env_text):
            if variable == "DATABASE_DSN":
                value = "postgresql://test:test@postgres/agents"
            elif variable == "CLIENT_URL":
                value = "http://model.test/v1"
            else:
                value = "test-value"
            runtime_env[variable] = value

        case_directory = tmp_path / name
        case_directory.mkdir()
        (case_directory / ".env").write_text(env_text)
        runtime_env["PYTHONPATH"] = str(python_path)

        result = subprocess.run(
            [sys.executable, "-c", statement],
            cwd=case_directory,
            env=runtime_env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{name}: {result.stderr}"
