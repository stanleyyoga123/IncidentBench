from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ArtifactLayout:
    root: Path

    @property
    def metadata(self) -> Path:
        return self.root / "metadata.json"

    @property
    def commands(self) -> Path:
        return self.root / "commands"

    @property
    def metrics(self) -> Path:
        return self.root / "metrics"

    @property
    def snapshots(self) -> Path:
        return self.root / "snapshots"

    @property
    def inputs(self) -> Path:
        return self.root / "inputs"

    @property
    def archived_scenario(self) -> Path:
        return self.inputs / "scenario.json"

    @property
    def archived_chaos(self) -> Path:
        return self.inputs / "chaos"

    @property
    def archived_placement(self) -> Path:
        return self.inputs / "placement"

    @property
    def archived_placement_source(self) -> Path:
        return self.archived_placement / "source"

    @property
    def archived_placement_render(self) -> Path:
        return self.archived_placement / "rendered.yaml"

    def chaos_step(self, index: int, name: str) -> Path:
        return self.root / "injector" / f"{index:02d}-{name}"

    def chaos_schedule(self, index: int, step_name: str, reference: str) -> Path:
        return self.chaos_step(index, step_name) / reference

    def phase_commands(self, phase: str) -> Path:
        return self.commands / phase

    def ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
