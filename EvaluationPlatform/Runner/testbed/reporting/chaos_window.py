from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ChaosWindow:
    step_index: int
    step_name: str
    chaos: tuple[str, ...]
    schedule_types: tuple[str, ...]
    actions: tuple[str, ...]
    start: float
    end: float
    status: str


class ChaosWindowReader:
    def windows(self, metadata: dict) -> list[ChaosWindow]:
        definitions = {
            item["reference"]: item
            for item in metadata.get("chaos_definitions", [])
        }
        windows = []
        for step in metadata.get("chaos_steps", []):
            references = tuple(sorted(step.get("chaos", [])))
            if not references:
                continue
            start = step.get("active_started_at")
            end = step.get("cleanup_started_at")
            if not start or not end:
                continue
            selected = [definitions[reference] for reference in references]
            windows.append(
                ChaosWindow(
                    step_index=step["index"],
                    step_name=step["name"],
                    chaos=references,
                    schedule_types=tuple(
                        sorted({item["child_type"] for item in selected})
                    ),
                    actions=tuple(
                        sorted(
                            {
                                item["action"]
                                for item in selected
                                if item.get("action")
                            }
                        )
                    ),
                    start=pd.to_datetime(start, utc=True).timestamp(),
                    end=pd.to_datetime(end, utc=True).timestamp(),
                    status=step.get("status", "unknown"),
                )
            )
        return windows
