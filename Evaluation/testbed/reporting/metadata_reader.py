import json
from pathlib import Path


class MetadataReader:
    def read(self, run_folder: Path) -> dict:
        metadata = json.loads((Path(run_folder) / "metadata.json").read_text())
        if metadata.get("schema_version") != 2:
            raise ValueError(
                f"unsupported metadata schema: {metadata.get('schema_version')!r}; "
                "expected version 2"
            )
        return metadata
