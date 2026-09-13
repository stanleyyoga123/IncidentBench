from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import threading

import pytest
import yaml

from grader.cli import build_parser
from grader.ground_truth import (
    DEFAULT_GROUND_TRUTH_DIR,
    load_ground_truth,
    load_ground_truth_file,
)
from grader.judge import build_payload, build_penalty_payload, parse_judge_response
from grader.logging_utils import close_logging, configure_logging
from grader.metrics import (
    HIGHER,
    LOWER,
    METRIC_POLICIES,
    STABLE,
    assess_change,
    evaluate_metrics,
    metric_outcome,
)
from grader.penalty import (
    DEFAULT_PENALTIES_DIR,
    apply_penalties,
    load_penalties,
    load_penalty_file,
)
from grader.pipeline import GraderConfig, grade_runs
from grader.rubric import (
    DEFAULT_RUBRIC_PATH,
    build_policy,
    derived_alignment,
    load_rubric,
    parse_classifications,
    score_classifications,
)


EVALUATION_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_NAME = "real-node-delay-worker-3-one-hour"
ANCHOR = "1970-01-01T00:16:40+00:00"
EXCLUDED_PAPER_SCENARIOS = {
    "e2e-node-cpu-worker-1-twenty-minutes",
    "e2e-online-boutique-cartservice-cpu-smoke",
    "e2e-teastore-auth-cpu-smoke",
    "long-multi-fault-one-day",
}
PRODUCTION_GROUND_TRUTH_FORBIDDEN = re.compile(
    r"chaos|inject\w*|schedule|simulation|selector|experiment|"
    r"stress workers?|cpu workers?|\b\d+\s*(?:s|seconds?)\s+(?:in|of)\s+every\s+\d+",
    re.IGNORECASE,
)


def _scenario_catalog() -> dict[str, dict]:
    scenarios = {}
    for folder in (
        "online-boutique-scenario",
        "teastore-scenario",
        "sock-shop-scenario",
        "long-scenario",
    ):
        for path in sorted((EVALUATION_ROOT.parent / "Runner/resources/scenarios" / folder).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            scenarios[payload["name"]] = payload
    return scenarios


def _active_scenario_catalog() -> dict[str, dict]:
    scenarios = {}
    for folder in ("online-boutique-scenario", "teastore-scenario", "sock-shop-scenario"):
        for path in sorted((EVALUATION_ROOT.parent / "Runner/resources/scenarios" / folder).glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            scenarios[payload["name"]] = payload
    return scenarios


def _first_chaos_target(scenario: dict) -> str:
    reference = next(
        reference
        for step in scenario["steps"]
        for reference in step.get("chaos", [])
    )
    path = EVALUATION_ROOT.parent / "Runner/resources/chaos" / f"{reference}.yaml"
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = manifest["spec"]
    chaos_type = spec["type"]
    body = next(
        value for key, value in spec.items() if key.lower() == chaos_type.lower()
    )
    selector = body["selector"]
    expressions = selector.get("expressionSelectors") or []
    if expressions:
        return expressions[0]["values"][0]
    return selector["physicalMachines"]["chaos-mesh"][0]


def _highest_classifications(kind: str) -> dict[str, dict[str, str]]:
    return {
        criterion.id: {
            "class": criterion.class_ids()[-1],
            "reason": f"{kind} {criterion.id} matches expected condition",
        }
        for criterion in load_rubric().kind(kind).criteria
    }


class StaticJudge:
    model = "static-model"

    def __init__(
        self,
        *,
        fail: bool = False,
        fail_penalties: bool = False,
        applied_penalties: set[str] | None = None,
    ) -> None:
        self.fail = fail
        self.fail_penalties = fail_penalties
        self.applied_penalties = applied_penalties or set()
        self.calls: list[tuple[str, dict]] = []
        self.penalty_calls: list[dict] = []

    def grade(self, kind: str, payload: dict) -> dict[str, dict[str, str]]:
        self.calls.append((kind, payload))
        if self.fail:
            raise RuntimeError("mock judge unavailable")
        return _highest_classifications(kind)

    def grade_penalties(self, penalty_set, payload: dict) -> dict[str, dict]:
        self.penalty_calls.append(payload)
        if self.fail_penalties:
            raise RuntimeError("mock penalty judge unavailable")
        return {
            item.key: {
                "applied": item.key in self.applied_penalties,
                "reason": f"{item.key} {'applied' if item.key in self.applied_penalties else 'not applied'}",
            }
            for item in penalty_set.items
        }


class ConcurrentJudge(StaticJudge):
    def __init__(self) -> None:
        super().__init__()
        self.barrier = threading.Barrier(2, timeout=2)
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0

    def grade(self, kind: str, payload: dict) -> dict[str, dict[str, str]]:
        if kind != "rca":
            return super().grade(kind, payload)
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            self.barrier.wait()
            return super().grade(kind, payload)
        finally:
            with self.lock:
                self.active -= 1


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_penalties(folder: Path, scenario: str, items: list[dict]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{scenario}.json").write_text(
        json.dumps(items), encoding="utf-8"
    )


def _write_ground_truth(folder: Path, scenario: str = SCENARIO_NAME) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{scenario}.md").write_text(
        "# Scenario\n\n## RCA\n\nNetwork delay on worker-node-3.\n\n"
        "## Recommended remediation\n\nCordon and drain worker-node-3.\n",
        encoding="utf-8",
    )


def _write_run(run: Path, *, scenario: str = SCENARIO_NAME, chaos: bool = True) -> None:
    _write_json(run / "metadata.json", {"schema_version": 2})
    _write_json(
        run / "inputs" / "scenario.json",
        {
            "name": scenario,
            "steps": [{"name": "fault", "chaos": ["node-delay"], "duration": 60}],
        },
    )
    if chaos:
        chaos_path = run / "inputs" / "chaos" / "node-delay.yaml"
        chaos_path.parent.mkdir(parents=True, exist_ok=True)
        chaos_path.write_text(
            "apiVersion: chaos-mesh.org/v1alpha1\n"
            "kind: Schedule\n"
            "metadata:\n  name: node-delay\n"
            "spec:\n  type: PhysicalMachineChaos\n"
            "  physicalMachineChaos:\n    action: network-delay\n"
            "    address: [worker-node-3]\n",
            encoding="utf-8",
        )


def _write_jobs(run: Path) -> None:
    _write_json(
        run / "sessions" / "rca_session.json",
        [
            {
                "id": "rca-1",
                "workflow_id": "wf-1",
                "status": "succeeded",
                "created_at": "1970-01-01T00:10:00+00:00",
                "completed_at": "1970-01-01T00:15:00+00:00",
                "request": {"must_not_reach_judge": True},
                "raw_output": "must not reach judge",
                "tool_calls": [{"must_not_reach_judge": True}],
                "result": {"cause": "network delay on worker-node-3"},
            },
            {
                "id": "rca-running",
                "workflow_id": "wf-2",
                "status": "running",
                "created_at": "1970-01-01T00:16:00+00:00",
                "result": None,
            },
        ],
    )
    _write_json(
        run / "sessions" / "remediation_run.json",
        [
            {
                "id": "rem-1",
                "workflow_id": "wf-1",
                "status": "succeeded",
                "completed_at": ANCHOR,
                "request": {"must_not_reach_judge": True},
                "raw_output": "must not reach judge",
                "tool_calls": [{"must_not_reach_judge": True}],
                "result": {"action": "cordoned and drained worker-node-3"},
            },
            {
                "id": "rem-running",
                "workflow_id": "wf-2",
                "status": "running",
                "created_at": "1970-01-01T00:17:00+00:00",
                "completed_at": None,
                "result": None,
            },
        ],
    )


def _metric_values(before: float, after: float) -> list[list[object]]:
    return [
        [699, "9999"],
        [700, str(before)],
        [999, str(before)],
        [1000, str(after)],
        [1300, str(after)],
        [1301, "9999"],
        [1100, "NaN"],
    ]


def _write_metrics(run: Path) -> None:
    for metric in METRIC_POLICIES:
        before = 100.0
        after = 100.0
        if metric == "response_time_p95_seconds":
            after = 80.0
        payload = {
            "status": "success",
            "data": {
                "resultType": "matrix",
                "result": [
                    {
                        "metric": {"deployment": "frontend"},
                        "values": _metric_values(before, after),
                    },
                    {
                        "metric": {"deployment": "checkoutservice"},
                        "values": _metric_values(before, after),
                    },
                ],
            },
        }
        _write_json(run / "metrics" / f"{metric}.json", payload)


def test_current_and_historical_scenarios_have_valid_ground_truth() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    scenarios = _scenario_catalog()
    assert len(scenarios) == 48
    assert set(scenarios) <= set(truth)
    assert set(truth) - set(scenarios) == EXCLUDED_PAPER_SCENARIOS - {"long-multi-fault-one-day"}
    assert all(truth[name]["rca"] and truth[name]["remediation"] for name in scenarios)


def test_ground_truth_policy_and_targets_match_scenarios() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    scenarios = _active_scenario_catalog()
    assert len(scenarios) == 47
    assert set(_scenario_catalog()) - set(scenarios) == {"long-multi-fault-one-day"}
    for name, scenario in scenarios.items():
        entry = truth[name]
        assert "### Expected incident condition" in entry["rca"]
        assert "### Expected diagnosis and evidence" in entry["rca"]
        assert "### Fully correct" in entry["remediation"]
        assert "### Helpful but incomplete" in entry["remediation"]
        assert "### Rejected approaches" in entry["remediation"]
        assert "### Verification" in entry["remediation"]
        assert "Version rollback" in entry["remediation"]
        assert "outbound" in entry["remediation"]
        assert "response-time P95" in entry["remediation"]
        assert "HTTP 5xx" in entry["remediation"]
        assert _first_chaos_target(scenario) in entry["rca"]
        combined = entry["rca"] + "\n" + entry["remediation"]
        assert PRODUCTION_GROUND_TRUTH_FORBIDDEN.search(combined.replace("new pod schedules", "new pod becomes ready")) is None, name


def test_special_service_and_fault_policies_are_consistent() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    penalties = load_penalties(DEFAULT_PENALTIES_DIR)

    registry_capacity = truth["teastore-pod-registry-capacity-loss-one-hour"]
    assert "Do not add replicas or an HPA" in registry_capacity["remediation"]
    assert "After current pod and endpoint evidence demonstrates stability" in registry_capacity["remediation"]
    registry_penalties = " ".join(
        item.criteria
        for item in penalties["teastore-pod-registry-capacity-loss-one-hour"].items
    )
    assert "split registrations" in registry_penalties
    assert "after the fault ends does not count" in registry_penalties

    for name in (
        "real-pod-redis-cart-memory-all-one-hour",
        "teastore-pod-db-memory-all-one-hour",
    ):
        joined = " ".join(item.criteria for item in penalties[name].items)
        assert "stateful/singleton" in joined

    for name, entry in truth.items():
        if "bandwidth-all" in name:
            assert "bounded HPA patch" in entry["remediation"]
        if "capacity-loss" in name and "registry" not in name:
            assert "N+1 capacity" in entry["remediation"]
        if "cpu-headroom" in name:
            assert "limit-only increase" in entry["remediation"]
            joined = " ".join(item.criteria for item in penalties[name].items)
            assert "safe limit-only increase is incomplete but is not penalized" in joined

    expected_headroom = {
        "real-pod-emailservice-cpu-headroom-all-one-hour": "250m",
        "real-pod-checkoutservice-cpu-headroom-all-one-hour": "250m",
        "real-pod-productcatalogservice-cpu-headroom-all-one-hour": "250m",
        "teastore-pod-webui-cpu-headroom-all-one-hour": "500m",
        "teastore-pod-persistence-cpu-headroom-all-one-hour": "500m",
        "teastore-pod-image-cpu-headroom-all-one-hour": "750m",
    }
    for name, cpu in expected_headroom.items():
        assert cpu in truth[name]["rca"]


def test_active_ground_truth_uses_expected_production_abstractions() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    for name in _active_scenario_catalog():
        rca = truth[name]["rca"]
        if "cpu" in name:
            combined = rca + "\n" + truth[name]["remediation"]
            assert "throttl" not in combined.lower()
        if "node-delay" in name:
            assert "node-level network latency" in rca
        elif "node-loss" in name:
            assert "node-level packet loss" in rca
        elif "node-cpu" in name:
            assert "node-level CPU saturation" in rca
        elif "node-memory" in name:
            assert "node-level memory pressure" in rca
        elif "capacity-loss" in name:
            assert "Recurring loss" in rca
        elif "bandwidth" in name:
            assert "per-pod network throughput constraint" in rca
        elif "cpu-headroom" in name:
            assert "Insufficient per-pod CPU headroom" in rca
        elif "memory" in name:
            assert "per-pod memory pressure" in rca
        elif "cpu-all" in name:
            assert "service-wide CPU saturation" in rca
        else:
            pytest.fail(f"unclassified active scenario: {name}")


def test_transactional_and_stateful_service_context_is_preserved() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    assert "transaction completion" in truth[
        "real-pod-checkoutservice-cpu-all-one-hour"
    ]["rca"]
    assert "transaction-safe handling" in truth[
        "real-pod-paymentservice-cpu-all-one-hour"
    ]["rca"]
    assert "non-sharded cart state store" in truth[
        "real-pod-redis-cart-memory-all-one-hour"
    ]["rca"]
    assert "singleton MySQL data tier" in truth[
        "teastore-pod-db-memory-all-one-hour"
    ]["rca"]
    assert "singleton in-memory service registry" in truth[
        "teastore-pod-registry-capacity-loss-one-hour"
    ]["rca"]


def test_ground_truth_requires_recommended_remediation_heading(tmp_path: Path) -> None:
    path = tmp_path / "scenario.md"
    path.write_text(
        "## RCA\n\nExpected cause.\n\n## Remediation\n\nExpected action.\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="remediation"):
        load_ground_truth_file(path)


def test_judge_payload_contains_only_allowed_final_inputs() -> None:
    payload = build_payload(
        kind="rca",
        scenario="scenario",
        ground_truth={"rca": "expected", "remediation": "fix"},
        result={"summary": "final"},
    )
    assert set(payload) == {
        "scenario",
        "ground_truth",
        "agent_result",
    }
    serialized = json.dumps(payload)
    assert "request" not in serialized
    assert "raw_output" not in serialized
    assert "tool_calls" not in serialized
    assert "learning" not in serialized


def test_penalty_payload_retains_archived_manifests() -> None:
    payload = build_payload(
        kind="remediation",
        scenario=SCENARIO_NAME,
        ground_truth={"rca": "expected", "remediation": "fix"},
        result={"summary": "final"},
    )
    penalty_set = load_penalties()[SCENARIO_NAME]
    penalty_payload = build_penalty_payload(
        payload,
        penalty_set,
        [{"manifest": {"kind": "Schedule"}}],
    )
    assert set(penalty_payload) == {
        "scenario",
        "ground_truth",
        "chaos_manifests",
        "agent_result",
        "penalties",
    }
    assert penalty_payload["chaos_manifests"][0]["manifest"]["kind"] == "Schedule"


def test_semantic_policy_treats_evaluation_mechanisms_as_neutral() -> None:
    policy = build_policy(load_rubric().kind("rca"))
    assert "Do not require or reward identification of an evaluation mechanism" in policy
    assert "treat that terminology as neutral" in policy
    assert "neither award nor deduct" in policy
    assert "CHAOS_MANIFESTS" not in policy


def test_default_rubric_weights_and_required_kinds() -> None:
    rubric = load_rubric(DEFAULT_RUBRIC_PATH)
    assert set(rubric.kinds) == {"rca", "remediation"}
    assert len(rubric.source_hash) == 64
    for kind in ("rca", "remediation"):
        kind_rubric = rubric.kind(kind)
        assert len(kind_rubric.criteria) == 5
        assert abs(sum(item.weight for item in kind_rubric.criteria) - 1.0) < 1e-9
        for criterion in kind_rubric.criteria:
            assert criterion.class_ids()
            assert all(0 <= item.score <= 1 for item in criterion.classes)


def test_rubric_rejects_weights_that_do_not_sum_to_one(tmp_path: Path) -> None:
    source = tmp_path / "rubric.json"
    payload = json.loads(DEFAULT_RUBRIC_PATH.read_text(encoding="utf-8"))
    payload["kinds"]["rca"]["criteria"][0]["weight"] = 0.99
    source.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        load_rubric(source)


def test_unknown_classification_is_rejected() -> None:
    kind_rubric = load_rubric().kind("rca")
    payload = _highest_classifications("rca")
    payload["root_cause_correctness"] = {
        "class": "NOT_A_CLASS",
        "reason": "invalid",
    }
    with pytest.raises(ValueError, match="invalid class"):
        parse_classifications(kind_rubric, payload)


def test_classifications_convert_to_weighted_overall_score() -> None:
    kind_rubric = load_rubric().kind("rca")
    scored = score_classifications(
        kind_rubric,
        {
            "root_cause_correctness": {"class": "CORRECT", "reason": "cause"},
            "causal_reasoning_quality": {"class": "STRONG", "reason": "chain"},
            "evidence_grounding": {"class": "PARTIALLY_GROUNDED", "reason": "some"},
            "localization_accuracy": {"class": "MOSTLY_PRECISE", "reason": "node"},
            "diagnostic_completeness": {"class": "PARTIAL", "reason": "gaps"},
        },
    )
    assert scored["criteria"]["root_cause_correctness"]["score"] == 1.0
    assert scored["criteria"]["causal_reasoning_quality"]["score"] == 0.75
    assert scored["criteria"]["evidence_grounding"]["score"] == 0.5
    assert scored["criteria"]["localization_accuracy"]["score"] == 0.75
    assert scored["criteria"]["diagnostic_completeness"]["score"] == 0.5
    assert scored["overall_score"] == 0.75
    assert derived_alignment(scored) == "aligned"


def test_derived_alignment_uses_correctness_threshold() -> None:
    kind_rubric = load_rubric().kind("rca")
    classified = _highest_classifications("rca")
    classified["root_cause_correctness"] = {
        "class": "PARTIALLY_CORRECT",
        "reason": "category only",
    }
    scored = score_classifications(kind_rubric, classified)
    assert scored["alignment_score"] == 0.5
    assert derived_alignment(scored) == "not_aligned"
    classified["root_cause_correctness"] = {
        "class": "MOSTLY_CORRECT",
        "reason": "minor gaps",
    }
    scored = score_classifications(kind_rubric, classified)
    assert scored["alignment_score"] == 0.75
    assert derived_alignment(scored) == "aligned"


def test_all_ground_truth_scenarios_have_penalty_files() -> None:
    truth = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
    penalties = load_penalties(DEFAULT_PENALTIES_DIR)
    assert set(_scenario_catalog()) <= set(truth)
    assert set(truth) <= set(penalties)  # Historical penalty files may remain.
    for penalty_set in penalties.values():
        assert penalty_set.items
        assert all(0 < item.penalty <= 1 for item in penalty_set.items)


def test_every_penalty_set_has_simulation_guardrails() -> None:
    for penalty_set in load_penalties(DEFAULT_PENALTIES_DIR).values():
        assert penalty_set.items[0].penalty == 1.0
        joined = " ".join(item.criteria for item in penalty_set.items)
        assert "Chaos Mesh" in joined
        assert "evaluation runner" in joined
        assert "version rollback" in joined
        assert "outbound/dependency requests" in joined
        assert "scale a workload or traffic source to zero" in joined
        assert "rollback artifact" in joined
        assert "Delete a node, namespace" in joined


def test_penalty_file_rejects_out_of_range_values(tmp_path: Path) -> None:
    path = tmp_path / "scenario.json"
    path.write_text(
        json.dumps([{"criteria": "wrong node", "penalty": 1.5}]),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="penalty must be in"):
        load_penalty_file(path)


def test_applied_penalties_subtract_and_floor_at_zero() -> None:
    penalty_set = load_penalties()["real-node-delay-worker-3-one-hour"]
    judgements = {
        item.key: {
            "applied": item.key in {"p0", "p1"},
            "reason": "matched",
        }
        for item in penalty_set.items
    }
    applied = apply_penalties(0.75, penalty_set, judgements)
    assert applied["rubric_score"] == 0.75
    assert applied["penalty_total"] == 1.5
    assert applied["overall_score"] == 0.0
    none_applied = {
        item.key: {"applied": False, "reason": "ok"}
        for item in penalty_set.items
    }
    clean = apply_penalties(0.75, penalty_set, none_applied)
    assert clean["penalty_total"] == 0.0
    assert clean["overall_score"] == 0.75


def test_pipeline_applies_remediation_penalties_only(tmp_path: Path) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    penalties = tmp_path / "penalties"
    _write_ground_truth(truth)
    _write_penalties(
        penalties,
        SCENARIO_NAME,
        [
            {"criteria": "Uncordon a node other than worker-node-3.", "penalty": 0.5},
            {"criteria": "Delete the node.", "penalty": 0.5},
        ],
    )
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)
    judge = StaticJudge(applied_penalties={"p0"})
    grades = grade_runs(
        GraderConfig(
            input_path=tmp_path / "results",
            output_path=tmp_path / "grades",
            ground_truth_path=truth,
            penalties_path=penalties,
            model="static-model",
        ),
        judge,
    )
    rca = grades[0]["rca_jobs"][0]
    rem = grades[0]["remediation_jobs"][0]
    assert "penalties" not in rca["rubric"]
    assert rem["rubric"]["rubric_score"] == 1.0
    assert rem["rubric"]["penalty_total"] == 0.5
    assert rem["rubric"]["overall_score"] == 0.5
    assert rem["alignment"]["verdict"] == "aligned"
    assert rem["rubric"]["penalties"][0]["applied"] is True
    assert rem["rubric"]["penalties"][1]["applied"] is False
    assert len(judge.penalty_calls) == 1
    report = (tmp_path / "grades" / "report.md").read_text(encoding="utf-8")
    assert "## Remediation penalties applied" in report
    assert "| Rubric | Penalty | Total |" in report


def test_missing_penalty_file_skips_second_judge_call(tmp_path: Path) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    empty = tmp_path / "penalties"
    empty.mkdir()
    _write_ground_truth(truth)
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)
    judge = StaticJudge()
    grades = grade_runs(
        GraderConfig(
            input_path=tmp_path / "results",
            output_path=tmp_path / "grades",
            ground_truth_path=truth,
            penalties_path=empty,
            model="static-model",
        ),
        judge,
    )
    assert judge.penalty_calls == []
    rem = grades[0]["remediation_jobs"][0]
    assert rem["rubric"]["penalty_total"] == 0.0
    assert rem["rubric"]["penalties"] == []
    assert rem["rubric"]["overall_score"] == 1.0


def test_strict_judge_response_parsing() -> None:
    kind_rubric = load_rubric().kind("rca")
    payload = _highest_classifications("rca")
    parsed = parse_judge_response(kind_rubric, json.dumps(payload))
    assert parsed == payload
    extra = dict(payload)
    extra["score"] = 1
    with pytest.raises(ValueError):
        parse_judge_response(kind_rubric, json.dumps(extra))
    invalid = dict(payload)
    invalid["root_cause_correctness"] = {"class": "maybe", "reason": "unclear"}
    with pytest.raises(ValueError):
        parse_judge_response(kind_rubric, json.dumps(invalid))


@pytest.mark.parametrize(
    ("before", "after", "policy", "expected"),
    [
        (100, 85, LOWER, "improved"),
        (100, 115, LOWER, "worsened"),
        (100, 115, HIGHER, "improved"),
        (100, 85, HIGHER, "worsened"),
        (100, 115, STABLE, "worsened"),
        (100, 114.99, STABLE, "stable"),
        (0, 0, LOWER, "stable"),
        (0, 1, LOWER, "worsened"),
        (0, 1, HIGHER, "improved"),
        (1, 0, LOWER, "improved"),
        (1, 0, HIGHER, "worsened"),
        (0, 1, STABLE, "worsened"),
    ],
)
def test_metric_direction_threshold_and_zero_rules(
    before: float, after: float, policy: str, expected: str
) -> None:
    assert assess_change(before, after, policy, 0.15) == expected


def test_metric_catalog_and_core_health_gate() -> None:
    assert METRIC_POLICIES == {
        "http_5xx_rate": LOWER,
        "response_time_p95_seconds": LOWER,
    }
    families = {
        name: {"assessment": "stable"}
        for name in METRIC_POLICIES
    }
    assert metric_outcome(families)[0] == "not_good"
    families["response_time_p95_seconds"]["assessment"] = "improved"
    assert metric_outcome(families)[0] == "good"
    families["http_5xx_rate"]["assessment"] = "worsened"
    assert metric_outcome(families)[0] == "not_good"
    families["http_5xx_rate"]["assessment"] = "not_evaluable"
    assert metric_outcome(families)[0] == "not_evaluable"


def test_all_metric_families_series_and_window_boundaries(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_metrics(run)
    result = evaluate_metrics(run, ANCHOR)
    assert len(result["families"]) == 2
    assert result["outcome"] == "good"
    response = result["families"]["response_time_p95_seconds"]
    assert response["before_median"] == 100
    assert response["after_median"] == 80
    assert response["assessment"] == "improved"
    assert len(response["series"]) == 2
    assert response["series"][0]["before_samples"] == 2
    assert response["series"][0]["after_samples"] == 2


def test_missing_core_window_is_not_evaluable(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_metrics(run)
    (run / "metrics" / "http_5xx_rate.json").unlink()
    result = evaluate_metrics(run, ANCHOR)
    assert result["outcome"] == "not_evaluable"
    assert "http_5xx_rate" in result["reason"]


def test_non_grading_metric_files_are_ignored(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write_metrics(run)
    _write_json(run / "metrics" / "traffic_rps.json", {"invalid": "for grading"})

    result = evaluate_metrics(run, ANCHOR)

    assert result["outcome"] == "good"
    assert set(result["families"]) == {
        "http_5xx_rate",
        "response_time_p95_seconds",
    }


def test_concurrency_cli_default_environment_and_override(monkeypatch) -> None:
    monkeypatch.delenv("GRADER_CONCURRENCY", raising=False)
    assert build_parser().parse_args([]).concurrency == 5
    monkeypatch.setenv("GRADER_CONCURRENCY", "3")
    assert build_parser().parse_args([]).concurrency == 3
    assert build_parser().parse_args(["--concurrency", "2"]).concurrency == 2


def test_pipeline_grades_runs_concurrently_in_sorted_order(tmp_path: Path) -> None:
    truth = tmp_path / "truth"
    _write_ground_truth(truth)
    for run_name in ("run-2", "run-1"):
        run = tmp_path / "results" / run_name
        _write_run(run)
        _write_jobs(run)
        _write_metrics(run)

    judge = ConcurrentJudge()
    grades = grade_runs(
        GraderConfig(
            input_path=tmp_path / "results",
            output_path=tmp_path / "grades",
            ground_truth_path=truth,
            model="static-model",
            concurrency=2,
        ),
        judge,
    )

    assert judge.max_active == 2
    assert [grade["run"] for grade in grades] == ["run-1", "run-2"]
    assert all(grade["configuration"]["concurrency"] == 2 for grade in grades)
    assert (tmp_path / "grades" / "runs" / "run-1" / "grade.json").is_file()
    assert (tmp_path / "grades" / "runs" / "run-2" / "grade.json").is_file()


def test_pipeline_rejects_non_positive_concurrency(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="concurrency must be positive"):
        grade_runs(
            GraderConfig(
                input_path=tmp_path / "results",
                output_path=tmp_path / "grades",
                concurrency=0,
            ),
            StaticJudge(),
        )


def test_pipeline_grades_jobs_writes_artifacts_and_reuses_cache(tmp_path: Path) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    output = tmp_path / "grades"
    _write_ground_truth(truth)
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)

    config = GraderConfig(
        input_path=tmp_path / "results",
        output_path=output,
        ground_truth_path=truth,
        model="static-model",
    )
    judge = StaticJudge()
    grades = grade_runs(config, judge)
    assert len(judge.calls) == 2
    assert {kind for kind, _ in judge.calls} == {"rca", "remediation"}
    assert all(
        set(payload) == {"scenario", "ground_truth", "agent_result"}
        for _, payload in judge.calls
    )
    assert grades[0]["rca_jobs"][1]["alignment"]["verdict"] == "not_evaluable"
    assert grades[0]["rca_jobs"][1]["rubric"] is None
    rca = grades[0]["rca_jobs"][0]
    assert rca["alignment"]["verdict"] == "aligned"
    assert rca["rubric"]["overall_score"] == 1.0
    assert "penalties" not in rca["rubric"]
    assert grades[0]["configuration"]["rubric_hash"] == load_rubric().source_hash
    remediation = grades[0]["remediation_jobs"][0]
    assert remediation["metrics"]["outcome"] == "good"
    assert remediation["final_grade"] == "good"
    assert remediation["rubric"]["overall_score"] == 1.0
    assert remediation["rubric"]["rubric_score"] == 1.0
    assert remediation["rubric"]["penalty_total"] == 0.0
    assert len(judge.penalty_calls) == 1
    assert set(judge.penalty_calls[0]) == {
        "scenario",
        "ground_truth",
        "chaos_manifests",
        "agent_result",
        "penalties",
    }
    assert "penalty" not in json.dumps(judge.penalty_calls[0]["penalties"])
    assert grades[0]["remediation_jobs"][1]["final_grade"] == "not_evaluable"
    assert (output / "runs" / "run-1" / "grade.json").is_file()
    assert (output / "runs" / "run-1" / "report.md").is_file()
    assert (output / "runs" / "run-1" / "judge-cache.json").is_file()
    assert (output / "summary.csv").is_file()
    assert (output / "rca_rubric_score.csv").is_file()
    assert (output / "remediation_rubric_score.csv").is_file()
    assert (output / "report.md").is_file()
    with (output / "summary.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 4
    assert "overall_score" in rows[0]
    assert rows[0]["overall_score"] == "1.0"
    with (output / "rca_rubric_score.csv").open(newline="", encoding="utf-8") as handle:
        rca_rows = list(csv.DictReader(handle))
    assert [row["job_id"] for row in rca_rows] == ["rca-1", "rca-running"]
    assert rca_rows[0]["root_cause_correctness"] == "1.0"
    assert rca_rows[0]["root_cause_correctness_class"] == "CORRECT"
    assert rca_rows[0]["overall_score"] == "1.0"
    assert rca_rows[1]["overall_score"] == ""
    with (output / "remediation_rubric_score.csv").open(
        newline="", encoding="utf-8"
    ) as handle:
        rem_rows = list(csv.DictReader(handle))
    assert rem_rows[0]["remediation_correctness"] == "1.0"
    assert rem_rows[0]["overall_score"] == "1.0"
    assert rem_rows[0]["rubric_score"] == "1.0"
    assert rem_rows[0]["penalty_total"] == "0.0"
    assert "penalty_total" not in rca_rows[0]
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "## Summary" in report
    assert "### RCA rubric scores" in report
    assert "### Remediation rubric scores and metrics" in report
    assert report.index("## Summary") < report.index("## Overview")
    assert "| RC | CR | EG | LA | DC | Total |" in report
    assert (
        "| P95 before | P95 after | P95 change | P95 assessment | "
        "5xx before | 5xx after | 5xx change | 5xx assessment | "
        "Metric outcome | Final grade |"
    ) in report
    assert "| 100 | 80 | -20.00% | improved | 100 | 100 | 0.00% | stable | good | good |" in report
    run_report = (output / "runs" / "run-1" / "report.md").read_text(encoding="utf-8")
    assert "## Summary" in run_report
    assert "### RCA rubric scores" in run_report
    assert "### Remediation rubric scores and metrics" in run_report
    assert run_report.index("## Summary") < run_report.index("## RCA outputs")

    unavailable = StaticJudge(fail=True, fail_penalties=True)
    cached = grade_runs(config, unavailable)
    assert unavailable.calls == []
    assert unavailable.penalty_calls == []
    assert cached[0]["rca_jobs"][0]["alignment"]["cached"] is True

    refreshed = StaticJudge()
    grade_runs(
        GraderConfig(**{**config.__dict__, "refresh_judge": True}), refreshed
    )
    assert len(refreshed.calls) == 2
    assert len(refreshed.penalty_calls) == 1


def test_old_binary_cache_entries_are_not_reused(tmp_path: Path) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    output = tmp_path / "grades"
    _write_ground_truth(truth)
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)
    config = GraderConfig(
        input_path=tmp_path / "results",
        output_path=output,
        ground_truth_path=truth,
        model="static-model",
    )
    grade_runs(config, StaticJudge())
    cache_path = output / "runs" / "run-1" / "judge-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache["entries"] = {
        key: {"verdict": "aligned", "reason": "legacy binary cache"}
        for key in cache["entries"]
    }
    cache_path.write_text(json.dumps(cache), encoding="utf-8")
    retry = StaticJudge()
    grades = grade_runs(config, retry)
    assert len(retry.calls) == 2
    assert len(retry.penalty_calls) == 1
    assert grades[0]["rca_jobs"][0]["alignment"]["cached"] is False
    assert grades[0]["rca_jobs"][0]["rubric"]["overall_score"] == 1.0


def test_judge_failure_does_not_suppress_metric_grade(tmp_path: Path) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    _write_ground_truth(truth)
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)
    grades = grade_runs(
        GraderConfig(
            input_path=tmp_path / "results",
            output_path=tmp_path / "grades",
            ground_truth_path=truth,
            model="static-model",
        ),
        StaticJudge(fail=True),
    )
    remediation = grades[0]["remediation_jobs"][0]
    assert remediation["alignment"]["verdict"] == "not_evaluable"
    assert remediation["rubric"] is None
    assert remediation["metrics"]["outcome"] == "good"
    assert remediation["final_grade"] == "not_evaluable"


def test_verbose_file_log_records_progress_without_payload_contents(
    tmp_path: Path,
) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    output = tmp_path / "grades"
    _write_ground_truth(truth)
    _write_run(run)
    _write_jobs(run)
    _write_metrics(run)
    log_path = configure_logging(output, verbose=False)
    try:
        grade_runs(
            GraderConfig(
                input_path=tmp_path / "results",
                output_path=output,
                ground_truth_path=truth,
                model="static-model",
            ),
            StaticJudge(),
        )
    finally:
        close_logging()
    log = log_path.read_text(encoding="utf-8")
    assert "run started run=run-1" in log
    assert "judge call started kind=rca job_id=rca-1" in log
    assert "metric family run=run-1 job_id=rem-1" in log
    assert "grading completed runs=1 graded=1 ungraded=0 jobs=4" in log
    assert "must not reach judge" not in log
    assert "network delay on worker-node-3" not in log
    assert "cordoned and drained worker-node-3" not in log


@pytest.mark.parametrize("missing", ["ground_truth", "chaos"])
def test_missing_authoritative_input_skips_only_the_run(
    tmp_path: Path, missing: str
) -> None:
    run = tmp_path / "results" / "run-1"
    truth = tmp_path / "truth"
    valid_scenario = "different-scenario" if missing == "ground_truth" else SCENARIO_NAME
    _write_ground_truth(truth, valid_scenario)
    _write_run(run, chaos=missing != "chaos")
    _write_run(tmp_path / "results" / "run-2", scenario=valid_scenario)
    grades = grade_runs(
        GraderConfig(
            input_path=tmp_path / "results",
            output_path=tmp_path / "grades",
            ground_truth_path=truth,
            model="static-model",
        ),
        StaticJudge(),
    )
    by_run = {item["run"]: item for item in grades}
    assert by_run["run-1"]["status"] == "ungraded"
    assert by_run["run-2"]["status"] == "graded"
    assert (tmp_path / "grades" / "runs" / "run-1" / "judge-cache.json").is_file()


def test_resolved_scenario_extensions_preserve_historical_grading(tmp_path: Path):
    truth=tmp_path/'truth'
    penalties=tmp_path/'penalties'
    _write_ground_truth(truth)
    _write_penalties(penalties,SCENARIO_NAME,[])
    for name in ('historical','resolved'):
        run=tmp_path/'results'/name
        _write_run(run); _write_jobs(run); _write_metrics(run)
        if name=='resolved':
            path=run/'inputs/scenario.json'
            scenario=json.loads(path.read_text())
            scenario.update(schema_version=1,load={'type':'burst','parameters':{'peak_users':200}},
                            timing={'baseline_seconds':600,'grace_seconds':60},
                            integration='custom',prerun=['custom-reset'],postrun=['custom-export'],
                            deployments=[],agents_enabled=True)
            _write_json(path,scenario)
    grades=grade_runs(GraderConfig(input_path=tmp_path/'results',output_path=tmp_path/'grades',
                                  ground_truth_path=truth,penalties_path=penalties,model='static-model'),StaticJudge())
    assert len(grades)==2 and all(grade['status']=='graded' for grade in grades)
    for kind in ('rca_jobs','remediation_jobs'):
        assert grades[0][kind][0]['rubric']['overall_score']==grades[1][kind][0]['rubric']['overall_score']
        assert grades[0][kind][0]['alignment']==grades[1][kind][0]['alignment']
