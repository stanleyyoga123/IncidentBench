from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml


class ArchivedInputError(ValueError):
    pass


def load_archived_scenario(run_folder: Path) -> dict[str, Any]:
    archived = run_folder / "inputs" / "scenario.json"
    if not archived.is_file():
        raise ArchivedInputError("archived scenario input is missing: inputs/scenario.json")
    payload = json.loads(archived.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not payload.get("name"):
        raise ArchivedInputError("archived scenario input is missing or invalid")
    return payload


def chaos_references(scenario: dict[str, Any]) -> list[str]:
    references: list[str] = []
    seen: set[str] = set()
    for step in scenario.get("steps") or []:
        if not isinstance(step, dict):
            continue
        for reference in step.get("chaos") or []:
            if isinstance(reference, str) and reference and reference not in seen:
                references.append(reference)
                seen.add(reference)
    return references


def load_archived_chaos(
    run_folder: Path, scenario: dict[str, Any]
) -> list[dict[str, Any]]:
    references = chaos_references(scenario)
    if not references:
        raise ArchivedInputError("scenario has no archived chaos references")
    loaded: list[dict[str, Any]] = []
    for reference in references:
        path = run_folder / "inputs" / "chaos" / f"{reference}.yaml"
        if not path.is_file():
            raise ArchivedInputError(
                f"archived chaos manifest is missing: inputs/chaos/{reference}.yaml"
            )
        documents = [
            item
            for item in yaml.safe_load_all(path.read_text(encoding="utf-8"))
            if item
        ]
        if len(documents) != 1 or not isinstance(documents[0], dict):
            raise ArchivedInputError(
                f"archived chaos manifest must contain one YAML object: {path.name}"
            )
        loaded.append(
            {
                "reference": reference,
                "source": str(path.relative_to(run_folder)),
                "manifest": documents[0],
            }
        )
    return loaded
