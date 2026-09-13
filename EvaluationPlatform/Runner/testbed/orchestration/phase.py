from typing import Protocol

from ..domain.experiment_context import ExperimentContext
from ..domain.phase_result import PhaseResult


class ExperimentPhase(Protocol):
    name: str

    def execute(self, context: ExperimentContext) -> PhaseResult:
        ...
