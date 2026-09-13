import re
from pathlib import Path

from ...domain.chaos_schedule import ChaosSchedule
from .schedule_loader import ScheduleLoader


SAFE_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class ChaosCatalog:
    def __init__(self, root: Path, loader: ScheduleLoader | None = None) -> None:
        self.root = Path(root).resolve()
        self.loader = loader or ScheduleLoader()
        if not self.root.is_dir():
            raise FileNotFoundError(f"chaos collection not found: {self.root}")
        self._schedules = self._load_all()

    def _load_all(self) -> dict[str, ChaosSchedule]:
        schedules: dict[str, ChaosSchedule] = {}
        identities: dict[tuple[str, str, str], str] = {}
        for path in sorted(self.root.glob("*.yaml")):
            inspection = ScheduleLoader(self.loader.validator) if self.loader.node_ips is not None else self.loader
            schedule = inspection.load(path)
            identity_owner = identities.get(schedule.identity)
            if identity_owner is not None:
                raise ValueError(
                    f"duplicate Schedule identity {schedule.identity}: "
                    f"{identity_owner}, {schedule.reference}"
                )
            identities[schedule.identity] = schedule.reference
            schedules[schedule.reference] = schedule
        return schedules

    def resolve(self, reference: str) -> ChaosSchedule:
        if not isinstance(reference, str) or not SAFE_REFERENCE.fullmatch(reference):
            raise ValueError(f"unsafe chaos reference: {reference!r}")
        try:
            schedule = self._schedules[reference]
            return self.loader.load(schedule.source_path) if self.loader.node_ips is not None else schedule
        except KeyError as exc:
            raise ValueError(
                f"unknown chaos reference {reference!r}; expected "
                f"{self.root / (reference + '.yaml')}"
            ) from exc

    def resolve_many(self, references) -> tuple[ChaosSchedule, ...]:
        return tuple(self.resolve(reference) for reference in references)

    @property
    def schedules(self) -> tuple[ChaosSchedule, ...]:
        return tuple(self._schedules.values())
