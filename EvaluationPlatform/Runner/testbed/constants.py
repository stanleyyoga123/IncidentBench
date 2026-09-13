import os
from pathlib import Path


DEFAULT_NAMESPACE = "online-boutique"
DEFAULT_AGENT_NAMESPACE = "agents"
DEFAULT_HOST = "http://localhost:8888"
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
INFRASTRUCTURE_ROOT = Path(
    os.getenv("INFRASTRUCTURE_ROOT", WORKSPACE_ROOT / "EvaluationPlatform/Initialization")
).resolve()
NODE_INVENTORY_PATH = Path(
    os.getenv(
        "CHAOS_NODE_INVENTORY",
        INFRASTRUCTURE_ROOT / "ansible" / "inventory.ini",
    )
).resolve()


def node_inventory_path():
    return Path(os.getenv("CHAOS_NODE_INVENTORY", INFRASTRUCTURE_ROOT / "ansible/inventory.ini")).resolve()
