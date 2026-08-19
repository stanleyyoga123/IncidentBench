import os
from pathlib import Path


DEFAULT_NAMESPACE = "online-boutique"
DEFAULT_AGENT_NAMESPACE = "agents"
DEFAULT_HOST = "http://localhost:8888"
AGENT_DEPLOYMENTS = (
    "anomaly-detector",
    "agent-orchestrator",
    "learning-agent",
    "rca-agent",
    "remediator-agent",
    "mcp-tools-investigation",
    "mcp-tools-remediation",
)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
INFRASTRUCTURE_ROOT = Path(
    os.getenv("INFRASTRUCTURE_ROOT", WORKSPACE_ROOT / "Infrastructure")
).resolve()
ONLINE_BOUTIQUE_KUSTOMIZE_ROOT = (
    INFRASTRUCTURE_ROOT / "kubernetes" / "online-boutique" / "kustomize"
)
NODE_INVENTORY_PATH = Path(
    os.getenv(
        "CHAOS_NODE_INVENTORY",
        INFRASTRUCTURE_ROOT / "ansible" / "inventory.ini",
    )
).resolve()
