import threading
import unittest

from collector.metrics.prometheus import PrometheusConfigurationError
from manager.detector import DetectorManager
from schema.detection import Detection
from schema.storage import Metadata, MetricSeries


class FakeProvider:
    def __init__(self, series=None, error=None, stop_event=None):
        self.series = series or []
        self.error = error
        self.stop_event = stop_event
        self.closed = False

    async def fetch_recent(self):
        if self.stop_event is not None:
            self.stop_event.set()
        if self.error is not None:
            raise self.error
        return self.series

    async def close(self):
        self.closed = True


class FakeSink:
    def __init__(self, error=None):
        self.inserted = []
        self.error = error
        self.closed = False

    async def ingest(self, detections):
        if self.error:
            raise self.error
        self.inserted.extend(detections)
        return {"accepted": len(detections), "duplicates": 0}

    async def close(self):
        self.closed = True


class FakeMonitor:
    def __init__(self, detections):
        self.detections = detections
        self.received = None
        self.acknowledged = set()

    def detect(self, series):
        self.received = series
        return self.detections

    def acknowledge(self, keys):
        self.acknowledged.update(keys)


def metric_series():
    return MetricSeries(
        metadata=Metadata(
            name="checkout",
            resource="deployments",
            metric="traffic_rps",
        ),
        timestamps=[0.0, 30.0],
        values=[10.0, 20.0],
    )


def detection(is_anomaly):
    return Detection(
        metadata=metric_series().metadata,
        method="test",
        detail="",
        is_anomaly=is_anomaly,
    )


class DetectorManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_one_snapshot_is_shared_and_only_anomalies_are_written(self):
        series = [metric_series()]
        provider = FakeProvider(series=series)
        sink = FakeSink()
        first = FakeMonitor([detection(False)])
        second = FakeMonitor([detection(True)])
        manager = DetectorManager(
            series_provider=provider,
            sink=sink,
            monitors=[first, second],
        )

        result = await manager.detect()
        await manager.close()

        self.assertIs(first.received, series)
        self.assertIs(second.received, series)
        self.assertEqual(1, len(sink.inserted))
        self.assertEqual({metric_series().metadata.key}, second.acknowledged)
        self.assertEqual({"series": 1, "samples": 2, "anomalies": 1}, result)
        self.assertTrue(provider.closed)
        self.assertTrue(sink.closed)

    async def test_prometheus_data_error_skips_cycle_without_writes(self):
        stop_event = threading.Event()
        provider = FakeProvider(error=ValueError("bad payload"), stop_event=stop_event)
        sink = FakeSink()
        manager = DetectorManager(
            series_provider=provider,
            sink=sink,
            monitors=[FakeMonitor([detection(True)])],
        )

        await manager.detect_forever(stop_event)

        self.assertEqual([], sink.inserted)
        self.assertTrue(provider.closed)

    async def test_missing_rules_are_fatal(self):
        stop_event = threading.Event()
        provider = FakeProvider(
            error=PrometheusConfigurationError("missing rules"),
            stop_event=stop_event,
        )
        manager = DetectorManager(
            series_provider=provider,
            sink=FakeSink(),
            monitors=[],
        )

        with self.assertRaises(PrometheusConfigurationError):
            await manager.detect_forever(stop_event)
        self.assertTrue(provider.closed)

    async def test_delivery_failure_does_not_start_cooldown(self):
        monitor = FakeMonitor([detection(True)])
        manager = DetectorManager(
            series_provider=FakeProvider(series=[metric_series()]),
            sink=FakeSink(error=RuntimeError("orchestrator unavailable")),
            monitors=[monitor],
        )

        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            await manager.detect()

        self.assertEqual(set(), monitor.acknowledged)


if __name__ == "__main__":
    unittest.main()
