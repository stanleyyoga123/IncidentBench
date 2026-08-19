from analyzer.judge.schemas import (
    HOLISTIC_INSTRUCTIONS,
    RCA_INSTRUCTIONS,
    REMEDIATION_INSTRUCTIONS,
)


def rca_messages(payload: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": RCA_INSTRUCTIONS},
        {"role": "user", "content": _json(payload)},
    ]


def remediation_messages(payload: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": REMEDIATION_INSTRUCTIONS},
        {"role": "user", "content": _json(payload)},
    ]


def holistic_messages(payload: dict) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": HOLISTIC_INSTRUCTIONS},
        {"role": "user", "content": _json(payload)},
    ]


def _json(payload: dict) -> str:
    import json

    return json.dumps(payload, default=str)
