from engine import RCAEngine, RCA_TOOL_NAMES
import prompt
from prompt import AGENT_ORCHESTRATOR_PROMPT
from registry.tool_context import TOOL_USAGE_CONTEXT


def test_rca_prompt_and_tool_surface_exclude_remediation_execution():
    assert "Do not execute remediation" in AGENT_ORCHESTRATOR_PROMPT
    assert not hasattr(prompt, "REMEDIATOR_PROMPT")
    assert "remediator" not in RCA_TOOL_NAMES
    assert "remediator.write_file" not in TOOL_USAGE_CONTEXT
    assert "remediator.run_ansible" not in TOOL_USAGE_CONTEXT


def test_parse_populates_structured_remediation_plan():
    raw = """Remediation Required: yes
Incident State: active
Summary: checkout is degraded
Failed Investigation:
- traces unavailable
Evidence:
- elevated latency
Impact Scope:
- checkoutservice
Missing Or Uncertain:
- exact trigger
Remediation Plan: relocate the affected deployment after validation
Remediation Targets:
- deployment online-boutique/checkoutservice
Expected Benefit: restore healthy latency
Verification:
- verify rollout and request latency
Rollback:
- restore the previous pod template
Guardrails:
- stop if no eligible destination exists
"""

    result = RCAEngine._parse(raw)

    assert result.remediation_required is True
    assert result.incident_state == "active"
    assert result.remediation_plan.action.startswith("relocate")
    assert result.remediation_plan.targets == [
        "deployment online-boutique/checkoutservice"
    ]
    assert result.remediation_plan.expected_benefit == "restore healthy latency"
    assert result.remediation_plan.verification == [
        "verify rollout and request latency"
    ]
    assert result.remediation_plan.rollback == [
        "restore the previous pod template"
    ]
    assert result.remediation_plan.guardrails == [
        "stop if no eligible destination exists"
    ]


def test_parse_malformed_remediation_decision_fails_safe():
    result = RCAEngine._parse(
        "Remediation Required: unknown\n"
        "Incident State: unknown\n"
        "Summary: model output was incomplete"
    )

    assert result.remediation_required is False
    assert result.incident_state == "unconfirmed"
