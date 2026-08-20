import json

import pytest
from pydantic import ValidationError

from engine import LearningEngine


def test_parse_structured_atomic_lessons_and_fences():
    raw = '''```json
{"summary":"Reusable findings","lessons":[{"category":"investigation","title":"Check cordon cause","guidance":"When pods stop scheduling, inspect node schedulability and scheduling events before changing placement.","applies_when":["pods are Pending"],"avoid":["blindly uncordoning a node"],"evidence_refs":["tool-call:12"],"resource":"nodes","name":null,"metric":"app_instance_count","tags":["scheduling"],"confidence":0.9}]}
```'''
    result = LearningEngine.parse(raw)
    assert result.lessons[0].category == "investigation"
    assert result.lessons[0].confidence == 0.9


def test_parse_invalid_output_fails_attempt():
    with pytest.raises((ValueError, ValidationError)):
        LearningEngine.parse("not json")


def test_parse_coerces_prose_lists_and_confidence_labels():
    raw = json.dumps(
        {
            "summary": "Reusable findings from a CPU-throttling investigation.",
            "lessons": [
                {
                    "category": "Investigation",
                    "title": "Confirm CPU request headroom",
                    "guidance": "When CPU request utilization is high, inspect throttling and request headroom before scaling.",
                    "applies_when": "CPU request utilization is elevated and throttling remains stable.",
                    "avoid": "Immediately triggering node evacuation without checking HPA status or rollout history.",
                    "evidence_refs": "tool-call:12",
                    "resource": "deployments",
                    "name": "checkoutservice",
                    "metric": "deployment_cpu_request_utilization_percent",
                    "tags": "cpu,hpa",
                    "confidence": "high",
                },
                {
                    "category": "remediation",
                    "title": "Preserve HPA during rolling updates",
                    "guidance": "When HPA is active, keep stabilization windows intact during rollouts.",
                    "applies_when": "HPA-driven deployments change replica count during rolling updates.",
                    "avoid": "Setting stabilization windows to zero or disabling HPA entirely.",
                    "evidence_refs": [],
                    "resource": "",
                    "name": "",
                    "metric": "",
                    "tags": [],
                    "confidence": "medium-high",
                },
                {
                    "category": "verification",
                    "title": "Re-check HPA after the change",
                    "guidance": "After changing HPA settings, verify replica movement in a short window.",
                    "applies_when": "HPA parameters have been changed and a deployment is scheduled.",
                    "avoid": "Assuming the fix is permanent when the observation window is too long.",
                    "confidence": "medium",
                },
            ],
        }
    )
    result = LearningEngine.parse(raw)
    first, second, third = result.lessons
    assert first.category == "investigation"
    assert first.applies_when == [
        "CPU request utilization is elevated and throttling remains stable."
    ]
    assert first.avoid == [
        "Immediately triggering node evacuation without checking HPA status or rollout history."
    ]
    assert first.evidence_refs == ["tool-call:12"]
    assert first.tags == ["cpu,hpa"]
    assert first.confidence == 0.8
    assert second.confidence == 0.7
    assert second.resource is None
    assert second.name is None
    assert second.metric is None
    assert third.confidence == 0.5


def test_parse_rejects_unknown_confidence_label():
    raw = json.dumps(
        {
            "summary": "Reusable findings",
            "lessons": [
                {
                    "category": "investigation",
                    "title": "Check scheduling state",
                    "guidance": "Inspect node schedulability before changing placement.",
                    "applies_when": ["pods are Pending"],
                    "avoid": ["blind uncordon"],
                    "confidence": "likely",
                }
            ],
        }
    )
    with pytest.raises(ValidationError):
        LearningEngine.parse(raw)
