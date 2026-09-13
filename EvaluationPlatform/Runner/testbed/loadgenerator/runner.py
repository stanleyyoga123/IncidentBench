import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


import json
SHAPES = json.loads((Path(__file__).resolve().parents[2] / "config/load-shapes.json").read_text())
SCENARIO_MODULES = {name: item["module"].replace(".", "/") + ".py" for name, item in SHAPES.items()}


@dataclass
class LoadGeneratorProcess:
    scenario: str
    command: list[str]
    process: subprocess.Popen
    returncode: int | None = None

    def stop(self, timeout_seconds: int = 30) -> int:
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait()

        self.returncode = self.process.returncode
        return self.returncode


def scenario_file(repo_root: Path, scenario: str) -> Path:
    try:
        relative_path = SCENARIO_MODULES[scenario]
    except KeyError as exc:
        raise ValueError(f"unknown loadgenerator scenario: {scenario}") from exc

    return repo_root / relative_path


def start_locust(
    repo_root: Path,
    output_dir: Path,
    scenario: str,
    application_module: str,
    host: str,
    duration_seconds: int,
    parameters: dict | None = None,
) -> LoadGeneratorProcess:
    shape_file = scenario_file(repo_root, scenario)
    if not shape_file.exists():
        raise FileNotFoundError(f"locust shape file not found: {shape_file}")

    load_dir = output_dir / "loadgenerator"
    load_dir.mkdir(parents=True, exist_ok=True)

    locustfile = load_dir / "locustfile.py"
    from .settings import defaults
    import json
    settings = {**defaults(scenario), **(parameters or {}), "run_time_seconds": duration_seconds}
    shape_class = SHAPES[scenario]["class"]
    locustfile.write_text(
        f"from {application_module} import *\n"
        f"from {SHAPES[scenario]['module']} import {shape_class}\n"
        "import json\n"
        f"for key, value in json.loads({json.dumps(settings)!r}).items():\n"
        f"    setattr({shape_class}, key, value)\n"
    )

    csv_prefix = load_dir / scenario
    html_report = load_dir / f"{scenario}.html"
    log_file = load_dir / f"{scenario}.log"
    stdout_file = load_dir / f"{scenario}.stdout"

    command = [
        sys.executable,
        "-m",
        "locust",
        "-f",
        str(locustfile),
        "--headless",
        "--host",
        host,
        "--csv",
        str(csv_prefix),
        "--html",
        str(html_report),
        "--logfile",
        str(log_file),
        "--run-time",
        f"{duration_seconds}s",
    ]

    env = os.environ.copy()
    stdout_handle = stdout_file.open("w")
    process = subprocess.Popen(
        command,
        cwd=repo_root,
        env=env,
        stdout=stdout_handle,
        stderr=subprocess.STDOUT,
        text=True,
    )
    stdout_handle.close()
    return LoadGeneratorProcess(scenario=scenario, command=command, process=process)
