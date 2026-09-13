import hashlib
import json
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
