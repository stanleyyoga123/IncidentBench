import json
from pathlib import Path


class MetadataRepository:
    def __init__(self, path: Path) -> None:
        self.path = path

    def write(self, metadata: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(metadata, indent=2, default=str))
        temporary.replace(self.path)

    def read(self) -> dict:
        return json.loads(self.path.read_text())
