from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ScenarioStep:
    index: int
    name: str
    chaos: tuple[str, ...]
    duration: int

    @property
    def idle(self) -> bool:
        return not self.chaos

    def to_dict(self) -> dict:
        value = asdict(self)
        value["chaos"] = list(self.chaos)
        value["idle"] = self.idle
        return value


@dataclass(frozen=True)
class Scenario:
    name: str
    placement: str
    steps: tuple[ScenarioStep, ...]
    path: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "placement": self.placement,
            "path": self.path,
            "steps": [step.to_dict() for step in self.steps],
        }
