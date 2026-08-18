from dataclasses import dataclass
from typing import Callable

from ...artifacts.artifact_layout import ArtifactLayout


@dataclass(frozen=True)
class ChaosExecutionContext:
    artifacts: ArtifactLayout
    wait_until: Callable[[int, float], None]
    log: Callable[[str], None]
    record_step: Callable[[dict], None]
