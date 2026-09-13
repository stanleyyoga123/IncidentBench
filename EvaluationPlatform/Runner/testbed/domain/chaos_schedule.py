from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ChaosSchedule:
    reference: str
    source_path: Path
    manifest: dict[str, Any]
    digest: str
    api_version: str
    kind: str
    name: str
    namespace: str
    interval_seconds: float
    child_duration_seconds: float
    child_type: str
    child_key: str
    action: str | None

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.namespace, self.kind, self.name

    def to_metadata(self, archived_path: Path | None = None) -> dict:
        return {
            "reference": self.reference,
            "source_path": str(self.source_path),
            "archived_path": str(archived_path) if archived_path else None,
            "sha256": self.digest,
            "resource": {
                "apiVersion": self.api_version,
                "kind": self.kind,
                "name": self.name,
                "namespace": self.namespace,
            },
            "schedule": self.manifest["spec"]["schedule"],
            "interval_seconds": self.interval_seconds,
            "child_duration_seconds": self.child_duration_seconds,
            "child_type": self.child_type,
            "action": self.action,
        }
