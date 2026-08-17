from typing import Literal
from datetime import datetime, timezone

from schema.detection import Detection
from schema.storage import MetricSeries

Direction = Literal["both", "high", "low"]


class ThresholdLogic:
    def __init__(
        self,
        threshold: float,
        n_tail: int | None = None,
        consecutive_anomalies_required: int = 1,
        direction: Direction = "high",
    ):
        self._threshold = threshold
        self._consecutive_anomalies_required = max(1, consecutive_anomalies_required)
        self._n_tail = max(1, n_tail or self._consecutive_anomalies_required)
        self._direction = direction

        self._method = "ThresholdLogic"

    def predict(self, series: MetricSeries) -> Detection:
        tail_count = max(self._n_tail, self._consecutive_anomalies_required)
        start = max(0, len(series.values) - tail_count)
        consecutive_anomalies = 0
        latest_anomaly: Detection | None = None

        for index in range(start, len(series.values)):
            value = series.values[index]
            timestamp = series.timestamps[index]

            if self._is_threshold_violation(value):
                consecutive_anomalies += 1
                latest_anomaly = Detection(
                    metadata=series.metadata,
                    method=self._method,
                    detail=self._anomaly_detail(
                        series=series,
                        timestamp=timestamp,
                        value=value,
                        consecutive_anomalies=consecutive_anomalies,
                    ),
                    is_anomaly=True,
                    detected_at=datetime.fromtimestamp(timestamp, timezone.utc),
                )
                if consecutive_anomalies >= self._consecutive_anomalies_required:
                    return latest_anomaly
            else:
                consecutive_anomalies = 0
                latest_anomaly = None

        return Detection(
            metadata=series.metadata, method=self._method, detail="", is_anomaly=False
        )

    def _is_threshold_violation(self, value: float) -> bool:
        if self._direction == "high":
            return value > self._threshold
        if self._direction == "low":
            return value < self._threshold
        return abs(value) > self._threshold

    def _anomaly_detail(
        self,
        series: MetricSeries,
        timestamp: float,
        value: float,
        consecutive_anomalies: int,
    ) -> str:
        threshold_margin = self._threshold_margin(value)
        latest_values = series.values[-self._n_tail :]
        observed_direction = self._observed_direction(value)
        severity = self._severity_label(value)

        return "\n".join(
            [
                "anomaly_type = threshold_point_anomaly",
                f"resource = {series.metadata.resource}",
                f"name = {series.metadata.name}",
                f"metric = {series.metadata.metric}",
                f"timestamp = {timestamp}",
                f"current_value = {value}",
                f"threshold = {self._threshold}",
                f"threshold_margin = {threshold_margin}",
                f"direction = {self._direction}",
                f"observed_direction = {observed_direction}",
                f"severity = {severity}",
                f"tail_points_evaluated = {self._n_tail}",
                f"consecutive_anomalies = {consecutive_anomalies}",
                (
                    "consecutive_anomalies_required = "
                    f"{self._consecutive_anomalies_required}"
                ),
                (
                    "latest_tail_values = "
                    f"{', '.join(str(value) for value in latest_values)}"
                ),
            ]
        )

    def _threshold_margin(self, value: float) -> float:
        if self._direction == "low":
            return self._threshold - value
        if self._direction == "both":
            return abs(value) - self._threshold
        return value - self._threshold

    def _observed_direction(self, value: float) -> str:
        if self._direction == "both":
            return "increase" if value > self._threshold else "decrease"
        if self._direction == "low":
            return "decrease"
        return "increase"

    def _severity_label(self, value: float) -> str:
        margin = self._threshold_margin(value)
        scale = max(abs(self._threshold), 1e-8)
        relative_margin = margin / scale
        if relative_margin >= 0.50:
            return "critical"
        if relative_margin >= 0.20:
            return "high"
        return "warning"
