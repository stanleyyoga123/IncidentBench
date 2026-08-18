import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from testbed.evaluator.collector import Evaluator, PROMETHEUS_QUERIES


class EvaluatorTests(unittest.TestCase):
    @patch("testbed.evaluator.collector.subprocess.run")
    def test_collect_snapshot_records_failed_kubectl_top_without_failing(self, run_mock):
        def fake_run(command, text, capture_output, check):
            class Result:
                returncode = 1 if command[:2] == ["kubectl", "top"] else 0
                stdout = ""
                stderr = "metrics API unavailable" if returncode else ""

            return Result()

        run_mock.side_effect = fake_run

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = Evaluator(Path(tmp), namespace="online-boutique")
            metadata = evaluator.collect_snapshot("test")

            self.assertEqual(metadata["label"], "test")
            self.assertEqual(metadata["prometheus"]["enabled"], False)
            self.assertTrue((Path(tmp) / "snapshots" / "test" / "snapshot.json").exists())
            self.assertTrue(
                any(
                    item["name"] == "top-pods" and item["returncode"] == 1
                    for item in metadata["commands"]
                )
            )

    @patch("testbed.evaluator.collector.urllib.request.urlopen")
    def test_collect_metrics_writes_expected_metric_files(self, urlopen_mock):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def read(self):
                return b'{"status": "success", "data": {"result": []}}'

        urlopen_mock.return_value = Response()

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = Evaluator(
                Path(tmp),
                namespace="online-boutique",
                prometheus_url="http://prometheus.example",
            )
            metadata = evaluator.collect_metrics(
                start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
            )

            metrics_dir = Path(tmp) / "metrics"
            self.assertEqual(
                sorted(item["name"] for item in metadata["prometheus"]["queries"]),
                sorted(PROMETHEUS_QUERIES),
            )
            for metric_name in PROMETHEUS_QUERIES:
                self.assertTrue((metrics_dir / f"{metric_name}.json").exists())

    @patch("testbed.evaluator.collector.urllib.request.urlopen")
    def test_collect_metrics_uses_query_range_15s_step_and_1m_window(self, urlopen_mock):
        captured_urls = []

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return None

            def read(self):
                return b'{"status": "success", "data": {"result": []}}'

        def fake_urlopen(url, timeout):
            captured_urls.append(url)
            return Response()

        urlopen_mock.side_effect = fake_urlopen

        with tempfile.TemporaryDirectory() as tmp:
            evaluator = Evaluator(
                Path(tmp),
                namespace="online-boutique",
                prometheus_url="http://prometheus.example",
            )
            evaluator.collect_metrics(
                start=datetime(2026, 1, 1, tzinfo=timezone.utc),
                end=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
            )

        first_url = captured_urls[0]
        parsed = urlparse(first_url)
        query_params = parse_qs(parsed.query)

        self.assertEqual(parsed.path, "/api/v1/query_range")
        self.assertEqual(query_params["step"], ["15s"])
        self.assertIn("[1m]", query_params["query"][0])


if __name__ == "__main__":
    unittest.main()
