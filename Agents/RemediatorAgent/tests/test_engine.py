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


@pytest.mark.parametrize("raw", [
    "Status\n- Automation: executed\n- Recovery: not-recovered\nVerification\n- Rollout pending.",
    "Status\n- Automation: not executed\n- Recovery: unverified\nVerification\n- No valid post-action metrics.",
    "Ansible failed; changes may have been partially applied.",
    "**Status**\nSkipped: approved plan is no longer necessary.",
])
def test_nonempty_output_completes_and_is_checkpointed(monkeypatch, raw):
    from types import SimpleNamespace
    import engine as module
    monkeypatch.setattr(module.TOOL_REGISTRY, "describe_openai_format", lambda tools: [])
    monkeypatch.setattr(module, "Agent", lambda **kwargs: SimpleNamespace(run=lambda prompt: raw))
    settings = SimpleNamespace(client=SimpleNamespace(model="test", url="http://test", token="test", timeout_seconds=1),
                               manager=SimpleNamespace(max_rounds=1))
    engine = RemediationEngine(settings)
    saved = []
    engine.output_callback = lambda *args: saved.append(args)
    job_id = uuid4()
    result, returned = engine.run(job_id, request())
    assert returned == raw
    assert result.summary
    assert saved == [(job_id, raw), (job_id, raw, result.model_dump(mode="json"))]


@pytest.mark.parametrize("raw", [None, "", " \n\t"])
def test_empty_output_fails(monkeypatch, raw):
    from types import SimpleNamespace
    import engine as module
    monkeypatch.setattr(module.TOOL_REGISTRY, "describe_openai_format", lambda tools: [])
    monkeypatch.setattr(module, "Agent", lambda **kwargs: SimpleNamespace(run=lambda prompt: raw))
    settings = SimpleNamespace(client=SimpleNamespace(model="test", url="http://test", token="test", timeout_seconds=1),
                               manager=SimpleNamespace(max_rounds=1))
    engine = RemediationEngine(settings)
    with pytest.raises(RuntimeError, match="no final output"):
        engine.run(uuid4(), request())
