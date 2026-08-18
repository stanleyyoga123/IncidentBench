import hashlib
from pathlib import Path

import yaml

from ...domain.chaos_schedule import ChaosSchedule
from .schedule_validator import ScheduleValidator


class ScheduleLoader:
    def __init__(self, validator: ScheduleValidator | None = None) -> None:
        self.validator = validator or ScheduleValidator()

    def load(self, path: Path) -> ChaosSchedule:
        source = Path(path).resolve()
        raw = source.read_bytes()
        try:
            documents = list(yaml.safe_load_all(raw.decode("utf-8")))
        except yaml.YAMLError as exc:
            raise ValueError(f"{source}: invalid YAML: {exc}") from exc
        if len(documents) != 1:
            raise ValueError(f"{source}: expected exactly one YAML document")
        manifest = documents[0]
        details = self.validator.validate(manifest, str(source))
        metadata = manifest["metadata"]
        return ChaosSchedule(
            reference=source.stem,
            source_path=source,
            manifest=manifest,
            digest=hashlib.sha256(raw).hexdigest(),
            api_version=manifest["apiVersion"],
            kind=manifest["kind"],
            name=metadata["name"],
            namespace=metadata["namespace"],
            **details,
        )
