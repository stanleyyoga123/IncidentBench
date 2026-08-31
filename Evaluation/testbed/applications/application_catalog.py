from pathlib import Path

import yaml

from .application_profile import ApplicationProfile, SAFE_NAME


class ApplicationCatalog:
    def __init__(self, applications_root: Path, workspace_root: Path) -> None:
        self.applications_root = Path(applications_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()
        self._profiles = self._discover()

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def resolve(self, reference: str) -> ApplicationProfile:
        if not isinstance(reference, str) or not SAFE_NAME.fullmatch(reference):
            raise ValueError("application reference must be a safe lowercase name")
        try:
            return self._profiles[reference]
        except KeyError as exc:
            raise ValueError(f"unknown application: {reference}") from exc

    def other_namespaces(self, reference: str) -> tuple[str, ...]:
        selected = self.resolve(reference)
        namespaces = []
        seen = set()
        for name in self.references:
            namespace = self._profiles[name].namespace
            if name == selected.id or namespace == selected.namespace or namespace in seen:
                continue
            seen.add(namespace)
            namespaces.append(namespace)
        return tuple(namespaces)

    def _discover(self) -> dict[str, ApplicationProfile]:
        if not self.applications_root.is_dir():
            raise FileNotFoundError(
                f"application profile directory not found: {self.applications_root}"
            )
        profiles = {}
        for path in sorted(self.applications_root.glob("*/profile.yaml")):
            profile = ApplicationProfile.from_dict(yaml.safe_load(path.read_text()), path)
            if profile.id != path.parent.name:
                raise ValueError(
                    f"application id {profile.id!r} must match directory {path.parent.name!r}"
                )
            if profile.id in profiles:
                raise ValueError(f"duplicate application profile: {profile.id}")
            profiles[profile.id] = profile
        if not profiles:
            raise ValueError(f"application profile directory is empty: {self.applications_root}")
        return profiles
