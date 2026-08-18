from pathlib import Path


class RunDiscovery:
    def discover(self, folder: Path) -> list[Path]:
        folder = Path(folder)
        if (folder / "metadata.json").is_file():
            return [folder]
        return sorted({path.parent for path in folder.glob("*/metadata.json")})
