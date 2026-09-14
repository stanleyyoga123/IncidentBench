import hashlib
import json
import pytest
from uuid import uuid4

import prompt
from engine import RemediationEngine, TOOLS
from prompt import REMEDIATOR_PROMPT
from schema import RemediationJobRequest


def request():
    rca_result = {
        "remediation_required": True,
        "summary": "checkout is degraded",
        "remediation_plan": {
            "action": "relocate checkoutservice",
            "targets": ["deployment online-boutique/checkoutservice"],
        },
    }
    canonical = json.dumps(rca_result, sort_keys=True, separators=(",", ":"))
    return RemediationJobRequest(
        workflow_id=uuid4(),
        rca_job_id=uuid4(),
        rca_result=rca_result,
        rca_result_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
        approval={
            "actor": "operator",
            "reason": "evidence reviewed",
            "workflow_version": 2,
        },
    )


def test_remediator_prompt_and_tools_exclude_rca_orchestration():
    assert "Do not redo root-cause analysis" in REMEDIATOR_PROMPT
    assert not hasattr(prompt, "AGENT_ORCHESTRATOR_PROMPT")
    assert "agent_spawner" not in TOOLS
    assert "cluster.profile_baseline" not in TOOLS
    assert "The playbook must contain only the approved mutation" in REMEDIATOR_PROMPT
    assert "Adding `NotIn` is not enough" in REMEDIATOR_PROMPT
    assert "basename only" in REMEDIATOR_PROMPT


def test_prompt_serializes_approved_context_as_json():
    job_id = uuid4()
    value = RemediationEngine._prompt(job_id, request())

    assert f"Active MCP remediation session ID: {job_id}" in value
    assert '"approval": {' in value
    assert '"remediation_plan": {' in value
    assert "Approved RCA workflow" not in value
    assert "{'remediation_required':" not in value


def test_parse_matches_requested_plain_heading_output():
    result = RemediationEngine._parse(
        """Status
- Artifact: Ansible
- Automation: executed

Changes
- deployment online-boutique/checkoutservice: node-a -> node-b

Verification
- direct kubectl confirmed rollout complete

Blocked Or Skipped
- None

Next Steps
- Continue monitoring
"""
    )

    assert "Artifact: Ansible" in result.summary
    assert result.changes == [
        "deployment online-boutique/checkoutservice: node-a -> node-b"
    ]
    assert result.verification == ["direct kubectl confirmed rollout complete"]
    assert result.artifacts == []


def test_require_live_ansible_rejects_check_only_and_failed_runs():
    engine = RemediationEngine(settings=None)

    engine.note_tool_result(
        "remediator.run_ansible",
        {"ok": True, "check": True, "executed": True},
    )
    try:
        engine.require_live_ansible()
        raise AssertionError("check-only ansible must not count as live execution")
    except RuntimeError as exc:
        assert "live Ansible" in str(exc)

    engine.note_tool_result(
        "remediator.run_ansible",
        {"ok": False, "check": False, "executed": False},
    )
    try:
        engine.require_live_ansible()
        raise AssertionError("failed live ansible must not count as success")
    except RuntimeError:
        pass

    engine.note_tool_result(
        "remediator.run_ansible",
        {"ok": True, "check": False, "executed": True},
    )
    engine.require_live_ansible()


VERIFIED_OUTPUT = """Status
- Automation: executed
- Recovery: verified

Changes
- deployment example/service: old -> new

Verification
- rollout complete; latency and errors recovered over the approved window
"""


def live_success(engine):
    engine.note_tool_result("remediator.run_ansible", {"ok": True, "check": False})


def observed_recovery(engine):
    engine.note_tool_result("kubectl", {"ok": True, "stdout": "rollout complete"})
    engine.note_tool_result("prometheus", {
        "ok": True,
        "data": {"status": "success", "data": {"result": [
            {"metric": {}, "value": [123, "0.1"]},
        ]}},
    })


def test_success_requires_observations_after_execution():
    engine = RemediationEngine(None)
    observed_recovery(engine)
    live_success(engine)
    with pytest.raises(RuntimeError, match="post-action"):
        engine.require_verified_recovery(VERIFIED_OUTPUT)
    observed_recovery(engine)
    engine.require_verified_recovery(VERIFIED_OUTPUT)
    live_success(engine)
    with pytest.raises(RuntimeError, match="post-action"):
        engine.require_verified_recovery(VERIFIED_OUTPUT)


@pytest.mark.parametrize("status", ["unknown", "not-recovered", "verified\n- Recovery: unknown"])
def test_execution_cannot_override_unverified_or_conflicting_recovery(status):
    engine = RemediationEngine(None)
    live_success(engine)
    observed_recovery(engine)
    with pytest.raises(RuntimeError, match="not explicitly verified"):
        engine.require_verified_recovery(VERIFIED_OUTPUT.replace("Recovery: verified", f"Recovery: {status}"))


@pytest.mark.parametrize("result", [
    {"ok": False},
    {"ok": True, "data": {"status": "error"}},
    {"ok": True, "data": {"status": "success", "data": {"result": []}}},
])
def test_empty_or_failed_metric_response_is_not_recovery_evidence(result):
    engine = RemediationEngine(None)
    live_success(engine)
    engine.note_tool_result("kubectl", {"ok": True, "stdout": "ready"})
    engine.note_tool_result("prometheus", result)
    with pytest.raises(RuntimeError, match="post-action"):
        engine.require_verified_recovery(VERIFIED_OUTPUT)


def test_later_success_does_not_erase_failed_live_attempt():
    engine = RemediationEngine(None)
    engine.note_tool_result("remediator.run_ansible", {"ok": False, "check": False})
    live_success(engine)
    observed_recovery(engine)
    with pytest.raises(RuntimeError, match="failure requires review"):
        engine.require_verified_recovery(VERIFIED_OUTPUT)


def test_validation_only_does_not_count_as_successful_remediation():
    engine = RemediationEngine(None)
    observed_recovery(engine)
    with pytest.raises(RuntimeError, match="live Ansible"):
        engine.require_verified_recovery("Status\n- Automation: validation-only\n- Recovery: verified")
