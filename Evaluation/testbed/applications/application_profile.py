from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SAFE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SUPPORTED_INSTALLERS = {"kustomize", "helm", "script"}


def _safe_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not SAFE_NAME.fullmatch(value):
        raise ValueError(f"{field} must be a safe lowercase name")
    return value


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise ValueError(f"{field} must be an array of non-empty strings")
    return tuple(value)


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a non-negative integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a non-negative integer") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return parsed


@dataclass(frozen=True)
class InstallerProfile:
    type: str
    source_environment: str
    source_default: str
    path: str
    release: str | None = None
    script: str | None = None
    values: tuple[str, ...] = ()
    timeout: str = "30m"
    required_files: tuple[str, ...] = ()
    prerequisite_manifests: tuple[str, ...] = ()
    required_source_text: tuple[str, ...] = ()
    forbidden_source_text: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, raw: Any) -> "InstallerProfile":
        if not isinstance(raw, dict):
            raise ValueError("installer must be an object")
        installer_type = _string(raw.get("type"), "installer.type")
        if installer_type not in SUPPORTED_INSTALLERS:
            raise ValueError(f"unsupported installer type: {installer_type}")
        release = raw.get("release")
        script = raw.get("script")
        if installer_type == "helm":
            release = _safe_name(release, "installer.release")
        elif release is not None:
            raise ValueError("installer.release is only valid for Helm applications")
        if installer_type == "script":
            script = _string(script, "installer.script")
        elif script is not None:
            raise ValueError("installer.script is only valid for script applications")
        return cls(
            type=installer_type,
            source_environment=_string(
                raw.get("source_environment"), "installer.source_environment"
            ),
            source_default=_string(raw.get("source_default"), "installer.source_default"),
            path=_string(raw.get("path"), "installer.path"),
            release=release,
            script=script,
            values=_string_tuple(raw.get("values", []), "installer.values"),
            timeout=_string(raw.get("timeout", "30m"), "installer.timeout"),
            required_files=_string_tuple(
                raw.get("required_files", []), "installer.required_files"
            ),
            prerequisite_manifests=_string_tuple(
                raw.get("prerequisite_manifests", []),
                "installer.prerequisite_manifests",
            ),
            required_source_text=_string_tuple(
                raw.get("required_source_text", []),
                "installer.required_source_text",
            ),
            forbidden_source_text=_string_tuple(
                raw.get("forbidden_source_text", []),
                "installer.forbidden_source_text",
            ),
        )

    def source_root(self, workspace_root: Path) -> Path:
        configured = os.getenv(self.source_environment)
        candidate = Path(configured) if configured else workspace_root / self.source_default
        return candidate.expanduser().resolve()

    def install_source(self, workspace_root: Path) -> Path:
        return (self.source_root(workspace_root) / self.path).resolve()


@dataclass(frozen=True)
class PlacementSettings:
    mode: str
    root: str
    workload_names: tuple[str, ...]
    workload_prefixes: tuple[str, ...]
    label_key: str
    node_selector_key: str
    node_selector_value: str

    @classmethod
    def from_dict(cls, raw: Any) -> "PlacementSettings":
        if not isinstance(raw, dict):
            raise ValueError("placement must be an object")
        mode = _string(raw.get("mode"), "placement.mode")
        if mode not in {"rendered", "live"}:
            raise ValueError("placement.mode must be rendered or live")
        names = _string_tuple(raw.get("workload_names", []), "placement.workload_names")
        prefixes = _string_tuple(
            raw.get("workload_prefixes", []), "placement.workload_prefixes"
        )
        if not names and not prefixes:
            raise ValueError("placement must select workloads by name or prefix")
        return cls(
            mode=mode,
            root=_string(raw.get("root"), "placement.root"),
            workload_names=names,
            workload_prefixes=prefixes,
            label_key=_string(raw.get("label_key", "app"), "placement.label_key"),
            node_selector_key=_string(
                raw.get("node_selector_key", "role"), "placement.node_selector_key"
            ),
            node_selector_value=_string(
                raw.get("node_selector_value", "services"),
                "placement.node_selector_value",
            ),
        )

    def selects(self, workload: str) -> bool:
        return workload in self.workload_names or any(
            workload.startswith(prefix) for prefix in self.workload_prefixes
        )


@dataclass(frozen=True)
class ApplicationProfile:
    id: str
    namespace: str
    host: str
    port_forward_service: str
    port_forward_remote_port: int
    loadgenerator_module: str
    startup_delay_seconds: int
    installer: InstallerProfile
    placement: PlacementSettings
    source_path: Path

    @classmethod
    def from_dict(cls, raw: Any, source_path: Path) -> "ApplicationProfile":
        if not isinstance(raw, dict):
            raise ValueError(f"application profile must be an object: {source_path}")
        return cls(
            id=_safe_name(raw.get("id"), "application id"),
            namespace=_safe_name(raw.get("namespace"), "application namespace"),
            host=_string(raw.get("host"), "application host"),
            port_forward_service=_safe_name(
                raw.get("port_forward_service"), "application port_forward_service"
            ),
            port_forward_remote_port=int(raw.get("port_forward_remote_port")),
            loadgenerator_module=_string(
                raw.get("loadgenerator_module"), "application loadgenerator_module"
            ),
            startup_delay_seconds=_non_negative_int(
                raw.get("startup_delay_seconds", 0),
                "application startup_delay_seconds",
            ),
            installer=InstallerProfile.from_dict(raw.get("installer")),
            placement=PlacementSettings.from_dict(raw.get("placement")),
            source_path=Path(source_path).resolve(),
        )

    def placement_root(self, workspace_root: Path) -> Path:
        root = Path(self.placement.root)
        evaluation_root = self.source_path.parents[2]
        return (root if root.is_absolute() else evaluation_root / root).resolve()

    def to_metadata(self, workspace_root: Path) -> dict:
        return {
            "id": self.id,
            "namespace": self.namespace,
            "host": self.host,
            "startup_delay_seconds": self.startup_delay_seconds,
            "installer": self.installer.type,
            "source_root": str(self.installer.source_root(workspace_root)),
            "profile": str(self.source_path),
        }
