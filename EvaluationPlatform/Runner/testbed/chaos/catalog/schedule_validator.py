import re
from typing import Any


SCHEDULE_TYPE_KEYS = {
    "AWSChaos": "awsChaos",
    "AzureChaos": "azureChaos",
    "BlockChaos": "blockChaos",
    "DNSChaos": "dnsChaos",
    "GCPChaos": "gcpChaos",
    "HTTPChaos": "httpChaos",
    "IOChaos": "ioChaos",
    "JVMChaos": "jvmChaos",
    "KernelChaos": "kernelChaos",
    "NetworkChaos": "networkChaos",
    "PhysicalMachineChaos": "physicalmachineChaos",
    "PodChaos": "podChaos",
    "StressChaos": "stressChaos",
    "TimeChaos": "timeChaos",
}
DNS_NAME = re.compile(r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
EVERY = re.compile(r"^@every\s+(.+)$")
DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|s|m|h)")


class ScheduleValidator:
    def validate(self, manifest: Any, source: str) -> dict:
        if not isinstance(manifest, dict):
            raise ValueError(f"{source}: YAML document must be an object")
        if manifest.get("apiVersion") != "chaos-mesh.org/v1alpha1":
            raise ValueError(f"{source}: unsupported apiVersion")
        if manifest.get("kind") != "Schedule":
            raise ValueError(f"{source}: kind must be Schedule")

        metadata = manifest.get("metadata")
        spec = manifest.get("spec")
        if not isinstance(metadata, dict) or not isinstance(spec, dict):
            raise ValueError(f"{source}: metadata and spec must be objects")
        name = metadata.get("name")
        if not isinstance(name, str) or not DNS_NAME.fullmatch(name):
            raise ValueError(f"{source}: metadata.name must be a DNS label")
        if len(name) > 57:
            raise ValueError(f"{source}: Schedule name must not exceed 57 characters")
        if metadata.get("namespace") != "chaos-mesh":
            raise ValueError(f"{source}: metadata.namespace must be chaos-mesh")
        if spec.get("historyLimit") != 1:
            raise ValueError(f"{source}: spec.historyLimit must be 1")
        if spec.get("concurrencyPolicy") != "Forbid":
            raise ValueError(f"{source}: spec.concurrencyPolicy must be Forbid")

        schedule = spec.get("schedule")
        match = EVERY.fullmatch(schedule) if isinstance(schedule, str) else None
        if match is None:
            raise ValueError(f"{source}: spec.schedule must use @every <duration>")
        interval = self.parse_duration(match.group(1), source, "schedule interval")
        child_type = spec.get("type")
        child_key = SCHEDULE_TYPE_KEYS.get(child_type)
        if child_key is None:
            raise ValueError(f"{source}: unsupported Schedule type: {child_type}")
        child = spec.get(child_key)
        if not isinstance(child, dict):
            raise ValueError(f"{source}: spec.{child_key} must be an object")
        duration = self.parse_duration(
            child.get("duration"), source, f"spec.{child_key}.duration"
        )
        if duration >= interval:
            raise ValueError(f"{source}: child duration must be less than interval")
        return {
            "interval_seconds": interval,
            "child_duration_seconds": duration,
            "child_type": child_type,
            "child_key": child_key,
            "action": child.get("action"),
        }

    @staticmethod
    def parse_duration(value: Any, source: str, field: str) -> float:
        if not isinstance(value, str) or not value:
            raise ValueError(f"{source}: {field} must be a duration string")
        position = 0
        seconds = 0.0
        units = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0}
        for match in DURATION_PART.finditer(value):
            if match.start() != position:
                raise ValueError(f"{source}: invalid {field}: {value}")
            seconds += float(match.group(1)) * units[match.group(2)]
            position = match.end()
        if position != len(value) or seconds <= 0:
            raise ValueError(f"{source}: invalid {field}: {value}")
        return seconds
