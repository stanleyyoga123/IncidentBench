import unittest

from detector.logic.z_score import ZScoreLogic
from schema.storage import Metadata, MetricSeries


def series(values: list[float], metric: str = "test_metric") -> MetricSeries:
    return MetricSeries(
        metadata=Metadata(name="test-service", resource="deployments", metric=metric),
        timestamps=[float(index) for index in range(len(values))],
        values=values,
    )


class ZScoreLogicTest(unittest.TestCase):
    def test_default_logic_keeps_constant_history_suppression(self):
        detection = ZScoreLogic(threshold=3, min_history=30).predict(
            series([10.0] * 30 + [100.0])
        )

        self.assertFalse(detection.is_anomaly)

    def test_constant_history_tiny_movement_is_not_anomaly(self):
        detection = ZScoreLogic(
            threshold=3,
            lookback=120,
            min_history=30,
            n_tail=3,
            min_absolute_delta=1.0,
            consecutive_anomalies_required=3,
        ).predict(series([10.0] * 30 + [10.01, 10.02, 10.03]))

        self.assertFalse(detection.is_anomaly)

    def test_large_sustained_movement_is_anomaly(self):
        detection = ZScoreLogic(
            threshold=3,
            lookback=120,
            min_history=30,
            n_tail=3,
            min_absolute_delta=1.0,
            consecutive_anomalies_required=3,
        ).predict(series([10.0] * 30 + [100.0, 200.0, 300.0]))

        self.assertTrue(detection.is_anomaly)
        self.assertIn("anomaly_type = z_score_point_anomaly", detection.detail)
        self.assertIn("resource = deployments", detection.detail)
        self.assertIn("z_score_threshold = 3", detection.detail)
        self.assertNotIn("rca_hints =", detection.detail)
        self.assertNotIn("remediation_hints =", detection.detail)

    def test_one_point_spike_is_not_anomaly_when_persistence_required(self):
        detection = ZScoreLogic(
            threshold=3,
            lookback=120,
            min_history=30,
            n_tail=3,
            min_absolute_delta=1.0,
            consecutive_anomalies_required=3,
        ).predict(series([10.0] * 30 + [100.0, 10.0, 10.0]))

        self.assertFalse(detection.is_anomaly)

    def test_high_only_metric_ignores_low_drop(self):
        detection = ZScoreLogic(
            threshold=3,
            lookback=120,
            min_history=30,
            n_tail=3,
            min_absolute_delta=0.10,
            consecutive_anomalies_required=1,
            direction="high",
        ).predict(series([1.0] * 30 + [0.1, 0.1, 0.1], "response_time_p95_seconds"))

        self.assertFalse(detection.is_anomaly)

    def test_small_cpu_percent_delta_is_ignored_despite_large_z_score(self):
        history = [50.0 + (index * 0.001) for index in range(30)]
        detection = ZScoreLogic(
            threshold=3,
            lookback=120,
            min_history=30,
            n_tail=3,
            min_absolute_delta=5.0,
            consecutive_anomalies_required=1,
            direction="high",
        ).predict(series(history + [50.5, 50.6, 50.7]))

        self.assertFalse(detection.is_anomaly)


if __name__ == "__main__":
    unittest.main()
