from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .experiment_config import ExperimentConfig
from .phase_result import PhaseResult
from .scenario import Scenario


@dataclass
class ExperimentContext:
    config: ExperimentConfig
    scenario: Scenario
    metadata: dict
    evaluator: Any
    load_process: Any = None
    port_forward_process: Any = None
    run_started_wall: datetime | None = None
    experiment_finished_wall: datetime | None = None
    metrics_collected: bool = False
    phase_results: list[PhaseResult] = field(default_factory=list)

    @property
    def scenario_duration(self) -> int:
        return sum(step.duration for step in self.scenario.steps)

    @property
    def total_load_duration(self) -> int:
        return (
            self.config.baseline_seconds
            + self.config.grace_period
            + self.scenario_duration
        )
