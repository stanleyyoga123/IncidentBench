import unittest

from adaptation import DetectorProfileRegistry
from detector.logic.threshold import ThresholdLogic
from detector.monitor.threshold import ThresholdMonitor
from schema.storage import Metadata, MetricSeries


def series(values: list[float], metric: str = "test_metric") -> MetricSeries:
    return MetricSeries(
        metadata=Metadata(name="test-service", resource="deployments", metric=metric),
        timestamps=[float(index) for index in range(len(values))],
        values=values,
    )


class ThresholdLogicTest(unittest.TestCase):
    def test_high_threshold_crossing_is_anomaly(self):
        detection = ThresholdLogic(
            threshold=80.0,
        ).predict(series([50.0] * 5 + [90.0], "deployment_cpu_request_utilization_percent"))

        self.assertTrue(detection.is_anomaly)
        self.assertIn("anomaly_type = threshold_point_anomaly", detection.detail)
        self.assertIn("threshold = 80.0", detection.detail)
        self.assertIn("observed_direction = increase", detection.detail)

    def test_detects_without_historical_warmup(self):
        detection = ThresholdLogic(
            threshold=80.0,
        ).predict(series([90.0]))

        self.assertTrue(detection.is_anomaly)

    def test_requires_consecutive_tail_violations_when_configured(self):
        logic = ThresholdLogic(
            threshold=80.0,
            consecutive_anomalies_required=3,
        )

        one_point_spike = logic.predict(series([50.0] * 5 + [90.0, 50.0, 50.0]))
        sustained_spike = logic.predict(series([50.0] * 5 + [90.0, 91.0, 92.0]))

        self.assertFalse(one_point_spike.is_anomaly)
        self.assertTrue(sustained_spike.is_anomaly)
        self.assertIn("consecutive_anomalies = 3", sustained_spike.detail)

    def test_low_threshold_crossing_is_anomaly(self):
        detection = ThresholdLogic(
            threshold=1.0,
            direction="low",
        ).predict(series([5.0] * 5 + [0.5], "app_instance_count"))

        self.assertTrue(detection.is_anomaly)
        self.assertIn("observed_direction = decrease", detection.detail)

    def test_monitor_uses_metric_threshold_config(self):
        monitor = ThresholdMonitor(
            cooldown_duration=300,
            metric_thresholds={
                "http_5xx_rate": {
                    "threshold": 0.01,
                    "direction": "high",
                }
            },
        )

        detections = monitor.detect(
            [series([0.0] * 5 + [0.02, 0.02, 0.02], "http_5xx_rate")]
        )

        self.assertEqual(1, len(detections))
        self.assertTrue(detections[0].is_anomaly)

    def test_monitor_has_default_metric_thresholds(self):
        monitor = ThresholdMonitor(cooldown_duration=300)

        detections = monitor.detect(
            [
                series(
                    [50.0] * 30 + [95.0, 96.0, 97.0],
                    "deployment_cpu_request_utilization_percent",
                )
            ]
        )

        self.assertEqual(1, len(detections))
        self.assertTrue(detections[0].is_anomaly)
        self.assertIn("threshold = 90.0", detections[0].detail)

    def test_5xx_threshold_requires_sustained_ratio_strictly_above_five_percent(self):
        monitor = ThresholdMonitor(cooldown_duration=300)

        exactly_five_percent = monitor.detect(
            [series([0.0] * 30 + [0.05, 0.05, 0.05], "http_5xx_rate")]
        )
        above_five_percent = monitor.detect(
            [series([0.0] * 30 + [0.051, 0.051, 0.051], "http_5xx_rate")]
        )

        self.assertFalse(exactly_five_percent[0].is_anomaly)
        self.assertTrue(above_five_percent[0].is_anomaly)

    def test_monitor_uses_updated_profile_and_records_provenance(self):
        registry = DetectorProfileRegistry()
        profile = registry.resolve(
            "threshold",
            "deployments",
            "test-service",
            "deployment_cpu_request_utilization_percent",
        )
        registry.update(
            profile.id,
            changes={"threshold": 95.0},
            reason="reduce observed false positives",
        )
        monitor = ThresholdMonitor(
            cooldown_duration=300,
            profile_registry=registry,
        )

        below_adapted_limit = monitor.detect(
            [
                series(
                    [50.0] * 30 + [92.0, 92.0, 92.0],
                    "deployment_cpu_request_utilization_percent",
                )
            ]
        )[0]
        active = registry.update(
            profile.id,
            changes={"threshold": 90.0},
            reason="restore sensitive limit",
        )
        above_adapted_limit = monitor.detect(
            [
                series(
                    [50.0] * 30 + [92.0, 92.0, 92.0],
                    "deployment_cpu_request_utilization_percent",
                )
            ]
        )[0]

        self.assertFalse(below_adapted_limit.is_anomaly)
        self.assertTrue(above_adapted_limit.is_anomaly)
        self.assertEqual(active.id, above_adapted_limit.profile_id)
        self.assertEqual(active.version, above_adapted_limit.profile_version)
        self.assertIn("detector_parameter_threshold = 90.0", above_adapted_limit.detail)


if __name__ == "__main__":
    unittest.main()
