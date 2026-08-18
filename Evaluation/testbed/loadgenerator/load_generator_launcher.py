from pathlib import Path

from testbed.loadgenerator.runner import start_locust


class LoadGeneratorLauncher:
    """Object adapter around the stable Locust process launcher."""

    def launch(
        self,
        repo_root: Path,
        output_dir: Path,
        scenario: str,
        host: str,
        duration_seconds: int,
    ):
        return start_locust(
            repo_root=repo_root,
            output_dir=output_dir,
            scenario=scenario,
            host=host,
            duration_seconds=duration_seconds,
        )
