from pathlib import Path

import numpy as np
import pandas as pd


class LocustMetricReader:
    def read_window(self, run_folder: Path, start: float, end: float) -> dict:
        paths = sorted((Path(run_folder) / "loadgenerator").glob("*_stats_history.csv"))
        if not paths:
            return {}
        history = pd.read_csv(paths[0], low_memory=False)
        history = history[history["Name"].astype(str) == "Aggregated"].copy()
        history["Timestamp"] = pd.to_numeric(history["Timestamp"], errors="coerce")
        history = history.dropna(subset=["Timestamp"]).sort_values("Timestamp")
        before = history[history["Timestamp"] < start].tail(1)
        finish = history[history["Timestamp"] <= end].tail(1)
        window = history[(history["Timestamp"] >= start) & (history["Timestamp"] <= end)]
        if finish.empty:
            return {}
        first = before.iloc[0] if not before.empty else history.iloc[0]
        last = finish.iloc[0]
        start_count = self._number(first, "Total Request Count")
        end_count = self._number(last, "Total Request Count")
        requests = max(0.0, end_count - start_count)
        failures = max(
            0.0,
            self._number(last, "Total Failure Count")
            - self._number(first, "Total Failure Count"),
        )
        response_sum = (
            end_count * self._number(last, "Total Average Response Time")
            - start_count * self._number(first, "Total Average Response Time")
        )
        requests_per_second = (
            pd.to_numeric(window["Requests/s"], errors="coerce").mean()
            if not window.empty and "Requests/s" in window
            else np.nan
        )
        return {
            "request_count": requests,
            "failure_count": failures,
            "failure_pct": 100 * failures / requests if requests else np.nan,
            "avg_response_ms": response_sum / requests if requests else np.nan,
            "locust_avg_rps": requests_per_second,
        }

    @staticmethod
    def _number(row, key: str) -> float:
        value = row.get(key, np.nan)
        return float(value) if pd.notna(value) else np.nan
