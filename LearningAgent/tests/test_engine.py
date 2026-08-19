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
