import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_run_all_dispatches_real_constant_then_long_daily():
    environment = os.environ.copy()
    environment["RUN_SINGLE_SCRIPT"] = "/bin/echo"

    result = subprocess.run(
        [str(ROOT / "run_all.sh")],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    boutique = f"{ROOT}/collections/online-boutique-scenario constant"
    teastore = f"{ROOT}/collections/teastore-scenario constant"
    long = f"{ROOT}/collections/long-scenario daily"
    assert boutique in result.stdout
    assert teastore in result.stdout
    assert long in result.stdout
    assert result.stdout.index(teastore) < result.stdout.index(boutique)
    assert result.stdout.index(boutique) < result.stdout.index(long)


def test_run_single_rejects_unknown_load_generator_before_execution():
    result = subprocess.run(
        [
            str(ROOT / "run_single.sh"),
            str(ROOT / "collections" / "online-boutique-scenario"),
            "unknown",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "Unsupported load generator: unknown" in result.stderr
