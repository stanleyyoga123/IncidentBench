import json
from pathlib import Path

import pandas as pd


class PrometheusMetricReader:
    def read(self, run_folder: Path, metric_name: str, start: float, end: float) -> pd.DataFrame:
        path = Path(run_folder) / "metrics" / f"{metric_name}.json"
        if not path.is_file():
            return pd.DataFrame(columns=["name", "timestamp", "value"])
        payload = json.loads(path.read_text())
        rows = []
        for series in payload.get("data", {}).get("result", []):
            labels = series.get("metric", {})
            name = (
                labels.get("deployment")
                or labels.get("destination_workload")
                or labels.get("node")
                or "cluster"
            )
            for timestamp, value in series.get("values", []):
                try:
                    rows.append(
                        {
                            "name": name,
                            "timestamp": float(timestamp),
                            "value": float(value),
                        }
                    )
                except (TypeError, ValueError):
                    continue
        frame = pd.DataFrame(rows)
        if frame.empty:
            return frame
        return frame[
            (frame["timestamp"] >= start) & (frame["timestamp"] <= end)
        ]
