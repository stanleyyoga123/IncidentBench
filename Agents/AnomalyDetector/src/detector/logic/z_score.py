from collections import Counter
from math import sqrt
from typing import Literal
from datetime import datetime, timezone

from schema.detection import Detection
from schema.storage import Metadata, MetricSeries

Direction = Literal["both", "high", "low"]


class ZScoreLogic:
    def __init__(
        self,
        threshold: float = 3.0,
        lookback: int = 30,
        min_history: int = 5,
        n_tail: int = 1,
        epsilon: float = 1e-8,
        min_normalized_std_threshold: float = 0.05,  # about 5% difference
        min_constant_fraction: float = 0.9,  # 90% of the data being dominated by one value
        min_absolute_delta: float | None = None,
        min_relative_delta: float | None = None,
        consecutive_anomalies_required: int = 1,
        direction: Direction = "both",
    ):
        self._threshold = threshold
        self._lookback = lookback
        self._min_history = min_history
        self._n_tail = n_tail
        self._epsilon = epsilon
        self._min_normalized_std_threshold = min_normalized_std_threshold
        self._min_constant_fraction = min_constant_fraction
        self._min_absolute_delta = min_absolute_delta
        self._min_relative_delta = min_relative_delta
        self._consecutive_anomalies_required = max(1, consecutive_anomalies_required)
        self._direction = direction

        self._method = "ZScoreLogic"

    def predict(self, series: MetricSeries):
        start = max(0, len(series.values) - self._n_tail)
        consecutive_anomalies = 0
        latest_anomaly: Detection | None = None

        for index in range(start, len(series.values)):
            history_start = max(0, index - self._lookback)
            history = series.values[history_start:index]
            if len(history) < self._min_history:
                consecutive_anomalies = 0
                continue

            avg, std = self._mean_and_pstdev(history)
            value = series.values[index]
            timestamp = series.timestamps[index]
            delta = value - avg

            is_constant = self._is_almost_constant(
                history=history,
                metadata=series.metadata,
                std=std,
                value=value,
                avg=avg,
            )
            if is_constant:
                consecutive_anomalies = 0
                continue

            score = delta / max(std, self._epsilon)
            if self._is_qualifying_anomaly(score=score, delta=delta, avg=avg):
                consecutive_anomalies += 1
                latest_anomaly = Detection(
                    metadata=series.metadata,
                    method=self._method,
                    detail=self._anomaly_detail(
                        series=series,
                        timestamp=timestamp,
                        value=value,
                        avg=avg,
                        std=std,
                        delta=delta,
                        score=score,
                        history=history,
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

    def _is_almost_constant(
        self,
        history: list[float],
        metadata: Metadata,
        std: float,
        value: float,
        avg: float,
    ) -> Detection | None:
        delta = value - avg
        if std <= self._epsilon:
            if self._has_magnitude_guards() and self._passes_magnitude_guards(
                delta=delta, avg=avg
            ):
                return None
            return Detection(
                metadata=metadata,
                method=self._method,
                detail="constant historical data",
                is_anomaly=False,
            )

        if self._has_dominant_baseline(history):
            if self._has_magnitude_guards() and self._passes_magnitude_guards(
                delta=delta, avg=avg
            ):
                return None
            return Detection(
                metadata=metadata,
                method=self._method,
                detail="historical data is dominated by one baseline value",
                is_anomaly=False,
            )

        # Use max history instead of mean, because CV explodes when the
        # mean is close to zero even if absolute movement is tiny.
        scale = max(max(abs(value) for value in history), self._epsilon)
        normalized_std = std / scale
        if normalized_std < self._min_normalized_std_threshold:
            if self._has_magnitude_guards() and self._passes_magnitude_guards(
                delta=delta, avg=avg
            ):
                return None
            return Detection(
                metadata=metadata,
                method=self._method,
                detail="almost constant historical data",
                is_anomaly=False,
            )

    def _is_qualifying_anomaly(self, score: float, delta: float, avg: float) -> bool:
        if not self._passes_direction(score):
            return False
        if abs(score) <= self._threshold:
            return False
        return self._passes_magnitude_guards(delta=delta, avg=avg)

    def _passes_direction(self, score: float) -> bool:
        if self._direction == "high":
            return score > 0
        if self._direction == "low":
            return score < 0
        return True

    def _passes_magnitude_guards(self, delta: float, avg: float) -> bool:
        if (
            self._min_absolute_delta is not None
            and abs(delta) < self._min_absolute_delta
        ):
            return False

        if self._min_relative_delta is not None:
            scale = max(abs(avg), self._epsilon)
            if abs(delta) / scale < self._min_relative_delta:
                return False

        return True

    def _has_magnitude_guards(self) -> bool:
        return (
            self._min_absolute_delta is not None or self._min_relative_delta is not None
        )

    def _anomaly_detail(
        self,
        series: MetricSeries,
        timestamp: float,
        value: float,
        avg: float,
        std: float,
        delta: float,
        score: float,
        history: list[float],
        consecutive_anomalies: int,
    ) -> str:
        relative_delta = abs(delta) / max(abs(avg), self._epsilon)
        latest_values = series.values[-self._n_tail :]
        direction_text = self._direction_text(score)
        severity = self._severity_label(score)

        return "\n".join(
            [
                "anomaly_type = z_score_point_anomaly",
                f"resource = {series.metadata.resource}",
                f"name = {series.metadata.name}",
                f"metric = {series.metadata.metric}",
                f"timestamp = {timestamp}",
                f"current_value = {value}",
                f"baseline_mean = {avg}",
                f"baseline_std = {std}",
                f"delta_from_baseline = {delta}",
                f"relative_delta_from_baseline = {relative_delta:.4f}",
                f"z_score = {score:.2f}",
                f"z_score_threshold = {self._threshold}",
                f"direction = {self._direction}",
                f"observed_direction = {direction_text}",
                f"severity = {severity}",
                f"lookback_points = {len(history)}",
                f"lookback_limit = {self._lookback}",
                f"min_history_required = {self._min_history}",
                f"tail_points_evaluated = {self._n_tail}",
                f"consecutive_anomalies = {consecutive_anomalies}",
                (
                    "consecutive_anomalies_required = "
                    f"{self._consecutive_anomalies_required}"
                ),
                f"min_absolute_delta = {self._min_absolute_delta}",
                f"min_relative_delta = {self._min_relative_delta}",
                (
                    "latest_tail_values = "
                    f"{', '.join(str(value) for value in latest_values)}"
                ),
            ]
        )

    def _direction_text(self, score: float) -> str:
        return "increase" if score > 0 else "decrease"

    def _severity_label(self, score: float) -> str:
        magnitude = abs(score)
        if magnitude >= self._threshold * 2:
            return "critical"
        if magnitude >= self._threshold * 1.5:
            return "high"
        return "warning"

    def _mean_and_pstdev(self, values: list[float]) -> tuple[float, float]:
        avg = sum(values) / len(values)
        variance = sum((value - avg) ** 2 for value in values) / len(values)
        return avg, sqrt(variance)

    def _has_dominant_baseline(self, history: list[float]) -> bool:
        rounded_counts = Counter(
            0.0 if abs(value) <= self._epsilon else round(value, 8) for value in history
        )
        dominant_count = max(rounded_counts.values())
        return dominant_count / len(history) >= self._min_constant_fraction
