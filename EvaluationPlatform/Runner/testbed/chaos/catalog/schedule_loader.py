import hashlib
from pathlib import Path

import yaml

from ...domain.chaos_schedule import ChaosSchedule
from .schedule_validator import ScheduleValidator


class ScheduleLoader:
    def __init__(self, validator: ScheduleValidator | None = None, node_ips=None) -> None:
        self.node_ips = node_ips
        self.validator = validator or ScheduleValidator()

    def load(self, path: Path) -> ChaosSchedule:
        source = Path(path).resolve()
        raw = source.read_bytes()
        if self.node_ips is not None:
            import re
            import ipaddress
            def replace(match):
                name = match.group(1)
                if name not in self.node_ips:
                    raise ValueError(f"environment.node_ips is missing {name}")
                return str(ipaddress.ip_address(self.node_ips[name]))
            raw = re.sub(r"\$\{node_ip:([^}]+)\}", replace, raw.decode()).encode()

        try:
            documents = list(yaml.safe_load_all(raw.decode("utf-8")))
        except yaml.YAMLError as exc:
            raise ValueError(f"{source}: invalid YAML: {exc}") from exc
        if len(documents) != 1:
            raise ValueError(f"{source}: expected exactly one YAML document")
        manifest = documents[0]
        if self.node_ips is not None and b"${node_ip:" in source.read_bytes():
            raw = yaml.safe_dump(manifest, sort_keys=False).encode()
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
