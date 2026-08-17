from adaptation import DetectorProfileRegistry, attach_profile
from detector.logic.z_score import ZScoreLogic
from detector.monitor._base import _BaseMonitor
from schema.storage import MetricSeries
from schema.detection import Detection


class ZScoreMonitor(_BaseMonitor):
    def __init__(
        self,
        cooldown_duration: float,
        profile_registry: DetectorProfileRegistry | None = None,
    ):
        super().__init__(cooldown_duration)
        self._profile_registry = profile_registry or DetectorProfileRegistry()

    def detect(self, data: list[MetricSeries]) -> list[Detection]:
        detections = []
        for series in data:
            self._check_cooldown()
            if series.metadata.key in self._cooldowns:
                continue
            profile = self._profile_registry.resolve(
                "z_score",
                series.metadata.resource,
                series.metadata.name,
                series.metadata.metric,
            )
            if profile is None:
                continue

            detection = ZScoreLogic(**profile.parameters).predict(series)
            detection = attach_profile(detection, profile)
            detections.append(detection)
        return detections
