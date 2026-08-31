import re
from pathlib import Path


SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class PlacementCatalog:
    def __init__(self, collection_dir: Path, marker: str = "kustomization.yaml") -> None:
        self.collection_dir = Path(collection_dir).resolve()
        self.marker = marker
        self._profiles = self._discover()

    @property
    def references(self) -> tuple[str, ...]:
        return tuple(sorted(self._profiles))

    def resolve(self, reference: str) -> Path:
        if not isinstance(reference, str) or not SAFE_NAME.fullmatch(reference):
            raise ValueError("placement reference must be a safe non-empty name")
        try:
            return self._profiles[reference]
        except KeyError as exc:
            raise ValueError(f"unknown placement reference: {reference}") from exc

    def _discover(self) -> dict[str, Path]:
        if not self.collection_dir.is_dir():
            raise FileNotFoundError(
                f"placement collection not found: {self.collection_dir}"
            )
        profiles = {}
        for path in sorted(self.collection_dir.iterdir()):
            if not path.is_dir():
                continue
            if not SAFE_NAME.fullmatch(path.name):
                raise ValueError(f"unsafe placement profile name: {path.name}")
            if not (path / self.marker).is_file():
                raise ValueError(
                    f"placement profile is missing {self.marker}: {path.name}"
                )
            profiles[path.name] = path.resolve()
        if not profiles:
            raise ValueError(f"placement collection is empty: {self.collection_dir}")
        return profiles
