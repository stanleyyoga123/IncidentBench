import csv
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from testbed.loadgenerator.baseline_health import assess_baseline


def write_samples(path, samples):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["Timestamp", "Name", "Total Request Count", "Total Failure Count"])
        writer.writerows((t, "Aggregated", n, f) for t, n, f in samples)


@pytest.mark.parametrize("samples,now,passed", [
    ([(1000, 0, 0), (1300, 1000, 0)], 1301, True),
    ([(1000, 0, 0), (1300, 1000, 11)], 1301, False),
    ([(1000, 0, 0), (1300, 99, 0)], 1301, False),
    ([(1000, 0, 0), (1299, 1000, 0)], 1300, False),
    ([(1000, 0, 0), (1300, 1000, 0)], 1400, False),
    ([(1000, 0, 0), (1300, 1000, 0)], 1290, False),
    ([(1000, 0, 0), (1300, 1000, 200), (1600, 2000, 200)], 1601, False),
    ([(1000, 0, 0), (1300, 1000, 0), (1600, 2000, 30)], 1601, False),
    ([(1000, 100, 0), (1300, 90, 0)], 1301, False),
])
def test_baseline_admission(tmp_path, samples, now, passed):
    path = tmp_path / "stats.csv"
    write_samples(path, samples)
    assert assess_baseline(path, now)["passed"] is passed


def test_missing_statistics_fail_closed(tmp_path):
    assert not assess_baseline(tmp_path / "missing", 1300)["passed"]


def test_rejected_baseline_prevents_downstream_phases_and_still_finalizes(tmp_path):
    from testbed.orchestration.baseline_phase import BaselinePhase
    from testbed.orchestration.experiment_runner import ExperimentRunner

    events = []
    metadata = SimpleNamespace(write=lambda _: None, path=tmp_path / "metadata.json")
    context = SimpleNamespace(
        config=SimpleNamespace(startup_delay_seconds=0, application="teastore",
            repo_root=tmp_path, output_dir=tmp_path, loadgenerator="constant",
            loadgenerator_module="resources.applications.teastore", host="http://example",
            baseline_seconds=600, agents_enabled=True),
        metadata={"snapshots": [], "loadgenerator": {}}, phase_results=[],
        total_load_duration=1200,
        evaluator=SimpleNamespace(collect_snapshot=lambda _: {}),
    )
    process = SimpleNamespace(command=["locust"], process=SimpleNamespace(poll=lambda: None))
    def launch(**kwargs):
        assert kwargs['duration_seconds'] is None
        return process
    baseline = BaselinePhase(launch, lambda *_: None, metadata, lambda _: None)
    downstream = SimpleNamespace(execute=lambda _: events.append("agents-or-chaos"))
    finalizer = SimpleNamespace(execute=lambda _: events.append("finalization"))
    runner = ExperimentRunner([baseline, downstream], finalizer, metadata, lambda _: None)
    assert runner.run(context) == 1
    assert context.metadata["status"] == "failed"
    assert context.metadata["baseline_health"]["passed"] is False
    assert events == ["finalization"]


@pytest.fixture
def behavior():
    class RescheduleTask(Exception):
        pass

    # Keep these tests independent of gevent monkey patching and test-suite
    # stubs installed by the existing load-shape tests.
    stubs = {
        "locust": SimpleNamespace(FastHttpUser=object, TaskSet=object,
                                  between=lambda *_: None, task=lambda f: f),
        "locust.exception": SimpleNamespace(RescheduleTask=RescheduleTask),
        "testbed.loadgenerator.common": SimpleNamespace(request=None),
    }
    spec = importlib.util.spec_from_file_location(
        "teastore_test_workload", Path(__file__).parents[1] / "resources/applications/teastore.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    instance = module.TeaStoreBehavior()
    instance.client = SimpleNamespace(cookiejar=SimpleNamespace(clear=lambda: None))
    instance.wait = lambda: None
    return module, instance


def test_checkout_supplies_required_address_fields_and_confirmation(behavior):
    _, instance = behavior
    calls = []
    instance.checked_request = lambda *a, **kw: calls.append((a, kw))
    instance.checkout()
    options = calls[0][1]
    assert options["params"]["address1"] == "Road"
    assert options["params"]["address2"] == "City"
    assert "adress1" not in options["params"]
    assert options["expected_text"] == "Your order is confirmed!"


def test_http_200_failed_login_is_counted_as_failure(behavior):
    module, instance = behavior
    failures = []

    class Response:
        status_code = 200
        text = "You used wrong credentials!"
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def failure(self, message): failures.append(message)

    module.request = lambda *a, **kw: Response()
    with pytest.raises(module.RescheduleTask):
        instance.checked_request("post", "/loginAction", expected_text="You are logged in!")
    assert failures == ["TeaStore semantic check failed: /loginAction"]


def test_sessions_clear_cookies_even_after_failed_checkout(behavior):
    module, instance = behavior
    clears = []
    instance.client.cookiejar.clear = lambda: clears.append(True)
    instance.login = instance.browse = instance.add_to_cart = lambda: None
    instance.checkout = lambda: (_ for _ in ()).throw(module.RescheduleTask())
    for _ in range(3):
        with pytest.raises(module.RescheduleTask):
            instance.shopping_session()
    assert len(clears) == 6


def test_completed_session_logs_out_and_has_bounded_cart(behavior):
    _, instance = behavior
    calls = []
    instance.checked_request = lambda *a, **kw: calls.append((a, kw))
    instance.shopping_session()
    adds = [kw for a, kw in calls if "addToCart" in kw.get("params", {})]
    assert len(adds) == 1
    assert calls[-1][1]["params"] == {"logout": ""}
