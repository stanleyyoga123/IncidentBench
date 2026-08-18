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


def test_parse_accepts_markdown_emphasis_around_headings():
    raw = """
**Remediation Required:** yes
**Incident State:** active
**Summary:**
checkout pods cannot schedule
**Evidence:**
- pending pods
**Impact Scope:**
- checkoutservice
**Missing Or Uncertain:**
- how the affinity was introduced
**Remediation Plan:**
remove the invalid nodeAffinity
**Remediation Targets:**
- deployment online-boutique/checkoutservice
**Expected Benefit:**
pods become Running
**Verification:**
- kubectl get pods
"""

    result = RCAEngine._parse(raw)

    assert result.remediation_required is True
    assert result.incident_state == "active"
    assert result.summary == "checkout pods cannot schedule"
    assert result.evidence == ["pending pods"]
    assert result.remediation_plan.action == "remove the invalid nodeAffinity"
    assert result.remediation_plan.targets == [
        "deployment online-boutique/checkoutservice"
    ]


def test_parse_malformed_remediation_decision_fails_safe():
    result = RCAEngine._parse(
        "Remediation Required: unknown\n"
        "Incident State: unknown\n"
        "Summary: model output was incomplete"
    )

    assert result.remediation_required is False
    assert result.incident_state == "unconfirmed"


def test_parse_markdown_headings_and_omitted_remediation_required():
    raw = """
Based on the baseline profiling and the investigation into the `checkoutservice` deployment:

### Incident State: **Active**

### Summary
checkoutservice cannot schedule new pods because nodeAffinity names a missing node.

### Evidence
- Pending pods show FailedScheduling
- Node inventory confirms nonexistent-sre-fault-node is absent

### Impact Scope
- checkoutservice

### Missing Or Uncertain
- traffic volume on the remaining replica

### Remediation Plan
**Corrective Action:** Remove the invalid nodeAffinity constraint from the checkoutservice Deployment.

**Remediation Targets:**
- `deployment.apps/checkoutservice` (namespace: `online-boutique`)

**Expected Benefit:**
pods become Running on real worker nodes
"""

    result = RCAEngine._parse(raw)

    assert result.incident_state == "active"
    assert result.remediation_required is True
    assert "cannot schedule" in result.summary
    assert result.evidence[0].startswith("Pending pods")
    assert result.remediation_plan.action.startswith("Remove the invalid nodeAffinity")
    assert result.remediation_plan.targets == [
        "deployment.apps/checkoutservice` (namespace: `online-boutique`)"
    ]
