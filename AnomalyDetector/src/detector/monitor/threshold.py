from adaptation import DetectorProfileRegistry, attach_profile
from detector.logic.threshold import ThresholdLogic
from detector.monitor._base import _BaseMonitor
from schema.detection import Detection
from schema.storage import MetricSeries


class ThresholdMonitor(_BaseMonitor):
    def __init__(
        self,
        cooldown_duration: float,
        metric_thresholds: dict[str, dict] | None = None,
        profile_registry: DetectorProfileRegistry | None = None,
    ):
        super().__init__(cooldown_duration)
        self._profile_registry = profile_registry or DetectorProfileRegistry()
        self._metric_thresholds = metric_thresholds or {}

    def detect(self, data: list[MetricSeries]) -> list[Detection]:
        detections = []
        for series in data:
            self._check_cooldown()
            if series.metadata.key in self._cooldowns:
                continue

            profile = self._profile_registry.resolve(
                "threshold",
                series.metadata.resource,
                series.metadata.name,
                series.metadata.metric,
            )
            if profile is None:
                continue

            parameters = profile.parameters | self._metric_thresholds.get(
                series.metadata.metric,
                {},
            )
            effective_profile = profile.model_copy(
                update={"parameters": parameters},
                deep=True,
            )
            detection = ThresholdLogic(**parameters).predict(series)
            detection = attach_profile(detection, effective_profile)
            detections.append(detection)
        return detections
