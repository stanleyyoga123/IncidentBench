from collections.abc import Iterator
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType


@contextmanager
def isolated_runtime() -> Iterator[ModuleType]:
    """Load the second service without retaining its conflicting module names."""
    roots = {"api", "config", "features", "infrastructure"}

    def owned(name: str) -> bool:
        return name.split(".")[0] in roots

    saved = {name: module for name, module in sys.modules.items() if owned(name)}
    original_path = sys.path[:]
    workspace = Path(__file__).resolve().parents[5]
    try:
        for name in saved:
            del sys.modules[name]
        sys.path.insert(0, str(workspace / "Agents/Orchestrator/app"))
        yield import_module("features.agent_workflow.workflow_coordinator")
    finally:
        for name in list(sys.modules):
            if owned(name):
                del sys.modules[name]
        sys.modules.update(saved)
        sys.path[:] = original_path
