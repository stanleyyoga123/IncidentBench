from types import SimpleNamespace

from engine import RCAEngine, RCA_TOOL_NAMES
from schema import RCAJobRequest
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


def test_historical_lessons_are_untrusted_user_prompt_context():
    request = RCAJobRequest.model_validate(
        {
            "anomalies": [
                {
                    "event_id": "a" * 64,
                    "resource": "nodes",
                    "name": "worker-node-1",
                    "metric": "node_cpu_utilization_percent",
                    "method": "z_score",
                }
            ],
            "historical_lessons": [
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "category": "investigation",
                    "title": "Check scheduling state",
                    "guidance": "Inspect node schedulability before changing placement.",
                    "confidence": 0.9,
                }
            ],
        }
    )
    rendered = RCAEngine._prompt(request)
    assert "# Historical Lessons" in rendered
    assert "untrusted historical hypotheses" in rendered
    assert "Inspect node schedulability" in rendered
    assert rendered.index("# Historical Lessons") > rendered.index("Event ID")


def test_runtime_scope_preserves_incident_namespace_without_topology_assumptions():
    request = RCAJobRequest.model_validate(
        {
            "anomalies": [
                {
                    "event_id": "b" * 64,
                    "namespace": "other-app",
                    "resource": "deployments",
                    "name": "frontend",
                    "metric": "deployment_cpu_usage",
                    "method": "z_score",
                }
            ]
        }
    )
    engine = RCAEngine(
        SimpleNamespace(
            workloads=SimpleNamespace(
                namespaces=["online-boutique"]
            )
        )
    )

    assert "Namespace: other-app" in engine._prompt(request)
    context = engine._workload_context(request)
    assert "Namespaces carried by this incident: other-app" in context
    assert "Never assume a particular application" in context


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


def test_raw_answer_saved_before_parser_rejects_it(monkeypatch):
    import pytest
    import engine as module
    from uuid import uuid4
    settings = SimpleNamespace(client=SimpleNamespace(model='test',url='http://test',token='test',timeout_seconds=1),
                               manager=SimpleNamespace(max_rounds=1))
    instance = RCAEngine(settings)
    monkeypatch.setattr(module.TOOL_REGISTRY, 'describe_openai_format', lambda tools: [])
    monkeypatch.setattr(module, 'Agent', lambda **kwargs: SimpleNamespace(run=lambda prompt: 'final answer'))
    monkeypatch.setattr(instance, '_workload_context', lambda request: '')
    monkeypatch.setattr(instance, '_prompt', lambda request: '')
    def invalid(raw):
        raise ValueError('parse rejected')
    monkeypatch.setattr(instance, '_parse', invalid)
    saved = []
    instance.output_callback = lambda *args: saved.append(args)
    job_id = uuid4()
    with pytest.raises(ValueError, match='parse rejected'):
        instance.run(job_id, SimpleNamespace())
    assert saved == [(job_id, 'final answer')]
