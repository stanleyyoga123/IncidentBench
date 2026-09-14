import asyncio
import unittest

from collector.metrics.prometheus import (
    PrometheusCollector,
    PrometheusConfigurationError,
)
from collector.metrics.provider import PrometheusSeriesProvider
from collector.metrics.query import QueryBuilder


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TrackingClient:
    def __init__(self, payload=None):
        self.payload = payload or {"status": "success", "data": {"result": []}}
        self.active = 0
        self.max_active = 0
        self.requests = []

    async def get(self, url, params):
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.requests.append((url, params))
        await asyncio.sleep(0.001)
        self.active -= 1
        return FakeResponse(self.payload)


class FakeCollector:
    def __init__(self, payload):
        self.payload = payload
        self.verify_calls = 0
        self.collect_calls = []
        self.closed = False

    async def verify_recording_rules(self, required_names):
        self.verify_calls += 1
        self.required_names = required_names

    async def collect_range(self, **kwargs):
        self.collect_calls.append(kwargs)
        return self.payload

    async def close(self):
        self.closed = True


def range_payload():
    payload = {
        name: {
            "query": QueryBuilder.record_name(name),
            "response": {"status": "success", "data": {"result": []}},
        }
        for name in QueryBuilder.names()
    }
    payload["traffic_rps"]["response"]["data"]["result"] = [
        {
            "metric": {"namespace": "default", "deployment": "checkout"},
            "values": [
                [60, "1.0"],
                [30, "NaN"],
                [60, "2.0"],
                [0, "+Inf"],
                [30, "3.0"],
            ],
        }
    ]
    return payload


class PrometheusCollectorTest(unittest.IsolatedAsyncioTestCase):
    def test_query_builder_escapes_regex_for_promql_string_literals(self):
        query = QueryBuilder.build(
            "traffic_rps",
            namespace_regex=r"team\-a|team\.b",
        )

        self.assertIn(r'namespace=~"team\\-a|team\\.b"', query)

    async def test_collect_range_limits_concurrency_and_shares_window(self):
        client = TrackingClient()
        collector = PrometheusCollector(
            "http://prometheus",
            max_concurrency=2,
            client=client,
        )

        result = await collector.collect_range(
            start=100,
            end=200,
            step=30,
            namespace_regex="default",
            excluded_node_regex="tools\\-node",
        )

        self.assertEqual(set(QueryBuilder.names()), set(result))
        self.assertLessEqual(client.max_active, 2)
        self.assertEqual(len(QueryBuilder.names()), len(client.requests))
        for _, params in client.requests:
            self.assertEqual(100, params["start"])
            self.assertEqual(200, params["end"])
            self.assertEqual(30, params["step"])

    async def test_verify_rules_rejects_missing_recordings(self):
        client = TrackingClient(
            {"status": "success", "data": {"groups": [{"rules": []}]}}
        )
        collector = PrometheusCollector("http://prometheus", client=client)

        with self.assertRaises(PrometheusConfigurationError):
            await collector.verify_recording_rules(
                {"anomaly_detector:traffic_rps"}
            )

    async def test_malformed_range_payload_is_rejected(self):
        client = TrackingClient({"status": "success", "data": {}})
        collector = PrometheusCollector("http://prometheus", client=client)

        with self.assertRaises(ValueError):
            await collector.query_range("up", 0, 30, 30)


class PrometheusSeriesProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_recent_aligns_window_and_cleans_samples(self):
        collector = FakeCollector(range_payload())
        provider = PrometheusSeriesProvider(
            collector,
            namespaces=["team.b", "team-a"],
            excluded_nodes=["tools-node"],
            history_minutes=30,
            query_step_seconds=30,
            clock=lambda: 1_234.9,
        )

        first = await provider.fetch_recent()
        await provider.fetch_recent()

        self.assertEqual(1, collector.verify_calls)
        self.assertEqual(QueryBuilder.required_record_names(), collector.required_names)
        self.assertEqual(1_230, collector.collect_calls[0]["end"])
        self.assertEqual(-570, collector.collect_calls[0]["start"])
        self.assertEqual(30, collector.collect_calls[0]["step"])
        self.assertEqual("team\\-a|team\\.b", collector.collect_calls[0]["namespace_regex"])
        self.assertEqual("tools\\-node", collector.collect_calls[0]["excluded_node_regex"])
        self.assertEqual(1, len(first))
        self.assertEqual("default", first[0].metadata.namespace)
        self.assertEqual("checkout", first[0].metadata.name)
        self.assertEqual([30.0, 60.0], first[0].timestamps)
        self.assertEqual([3.0, 2.0], first[0].values)


if __name__ == "__main__":
    unittest.main()
