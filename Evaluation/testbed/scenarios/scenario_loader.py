import json
import re
from pathlib import Path
from typing import Any

from ..chaos.catalog.chaos_catalog import ChaosCatalog
from ..domain.scenario import Scenario, ScenarioStep
from ..placement.placement_catalog import PlacementCatalog


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
STEP_FIELDS = {"name", "chaos", "duration"}


class ScenarioLoader:
    def __init__(
        self,
        repo_root: Path,
        catalog: ChaosCatalog,
        placement_catalog: PlacementCatalog,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.catalog = catalog
        self.placement_catalog = placement_catalog

    def load(self, path: Path) -> Scenario:
        source = Path(path).expanduser()
        if not source.is_absolute():
            source = self.repo_root / source
        source = source.resolve()
        if not source.is_file():
            raise FileNotFoundError(f"scenario not found: {source}")
        raw = json.loads(source.read_text())
        if not isinstance(raw, dict):
            raise ValueError("scenario must be a JSON object")
        unknown = set(raw) - {"name", "placement", "steps"}
        if unknown:
            raise ValueError(f"scenario has unknown fields: {', '.join(sorted(unknown))}")
        name = self._safe_name(raw.get("name"), "scenario name")
        placement = self._safe_name(raw.get("placement"), "placement reference")
        self.placement_catalog.resolve(placement)
        raw_steps = raw.get("steps")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError("scenario must contain a non-empty steps array")
        steps = tuple(
            self._parse_step(index, value)
            for index, value in enumerate(raw_steps, start=1)
        )
        return Scenario(
            name=name,
            placement=placement,
            steps=steps,
            path=str(source),
        )

    def _parse_step(self, index: int, raw: Any) -> ScenarioStep:
        if not isinstance(raw, dict):
            raise ValueError(f"step {index} must be an object")
        unknown = set(raw) - STEP_FIELDS
        missing = STEP_FIELDS - set(raw)
        if unknown:
            raise ValueError(f"step {index} has unknown fields: {', '.join(sorted(unknown))}")
        if missing:
            raise ValueError(f"step {index} is missing fields: {', '.join(sorted(missing))}")
        name = self._safe_name(raw["name"], f"step {index} name")
        duration = raw["duration"]
        if type(duration) is not int or duration <= 0:
            raise ValueError(f"step {index} duration must be a positive integer")
        references = raw["chaos"]
        if not isinstance(references, list) or any(
            not isinstance(value, str) for value in references
        ):
            raise ValueError(f"step {index} chaos must be an array of strings")
        if len(references) != len(set(references)):
            raise ValueError(f"step {index} chaos references must be unique")
        schedules = self.catalog.resolve_many(references)
        too_slow = [
            schedule.reference
            for schedule in schedules
            if schedule.interval_seconds > duration
        ]
        if too_slow:
            raise ValueError(
                f"step {index} duration is shorter than Schedule interval: "
                f"{', '.join(too_slow)}"
            )
        return ScenarioStep(index, name, tuple(references), duration)

    @staticmethod
    def _safe_name(value: Any, field: str) -> str:
        if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
            raise ValueError(f"{field} must be a safe non-empty name")
        return value
