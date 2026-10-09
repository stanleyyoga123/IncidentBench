"""Behavior of the notebook's archive compiler and its scheduled-chaos scope."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def compile_run():
    notebook = Path(__file__).resolve().parents[3] / "eda" / "adhoc.ipynb"
    namespace = {}
    for cell in json.loads(notebook.read_text())["cells"]:
        source = "".join(cell["source"])
        if cell["cell_type"] == "code" and (source.startswith("import json") or source.startswith("def compile_single_run")):
            exec(compile(source, str(notebook), "exec"), namespace)
    return namespace["compile_single_run"]


def write_run(path, *, steps=None, jobs=None, anomalies=None):
    path.mkdir(exist_ok=True)
    (path / "sessions").mkdir(exist_ok=True)
    if steps is None:
        steps = [{"chaos": ["cpu"], "idle": False, "duration": 3600,
                  "active_started_at": "2026-09-01T00:00:00Z",
                  "cleanup_started_at": "2026-09-01T01:00:05Z"}]
    (path / "metadata.json").write_text(json.dumps({"chaos_steps": steps}))
    for filename in ("rca_session.json", "remediation_run.json", "learning_session.json"):
        (path / "sessions" / filename).write_text(json.dumps(jobs or []))
    (path / "sessions" / "anomaly.json").write_text(json.dumps(anomalies or []))
    return path


def test_jobs_use_completion_scope_and_preserve_records(compile_run, tmp_path):
    jobs = [
        {"id": "start", "status": "succeeded", "completed_at": "2026-09-01T00:00:00Z",
         "started_at": "2026-08-31T23:55:00Z", "result": {"report": "retained"}},
        {"id": "failed", "status": "failed", "completed_at": "2026-09-01T10:30:00+10:00"},
        {"id": "before", "status": "succeeded", "completed_at": "2026-08-31T23:59:59Z"},
        {"id": "end", "status": "succeeded", "completed_at": "2026-09-01T01:00:00Z"},
        {"id": "running", "status": "running", "completed_at": "2026-09-01T00:30:00Z"},
        {"id": "queued", "status": "queued", "completed_at": None},
        {"id": "missing", "status": "succeeded"},
    ]
    run = write_run(tmp_path / "run", jobs=jobs)
    # A trace export must never substitute for the remediation jobs.
    (run / "sessions" / "remediation_session.json").write_text('[{"id": "trace"}]')
    frames = compile_run(str(run))
    assert set(frames) == {"anomaly", "rca", "remediation", "learning"}
    for name in ("rca", "remediation", "learning"):
        assert frames[name]["id"].tolist() == ["start", "failed"]
        assert frames[name].iloc[0]["result"] == {"report": "retained"}
        assert frames[name].iloc[1]["completed_at"] == jobs[1]["completed_at"]


def test_multiple_intervals_exclude_gaps_and_early_cleanup(compile_run, tmp_path):
    steps = [
        {"chaos": ["cpu"], "duration": 3600, "active_started_at": "2026-09-01T00:00:00Z",
         "cleanup_started_at": "2026-09-01T00:15:00Z"},
        {"chaos": [], "idle": True},
        {"chaos": ["delay"], "duration": 600, "active_started_at": "2026-09-01T00:30:00Z",
         "cleanup_started_at": "2026-09-01T00:45:00Z"},
    ]
    anomalies = [{"id": i, "status": "pending", "detected_at": time}
                 for i, time in enumerate(["2026-09-01T00:00:00Z", "2026-09-01T00:15:00Z",
                                           "2026-09-01T00:20:00Z", "2026-09-01T00:30:00Z",
                                           "2026-09-01T00:40:00Z", None])]
    run = write_run(tmp_path / "run", steps=steps, anomalies=anomalies)
    frames = compile_run(run)
    assert frames["anomaly"]["id"].tolist() == [0, 3]
    assert all(frames[name].empty for name in ("rca", "remediation", "learning"))
