from pathlib import Path
import unittest

import yaml

from collector.metrics.query import QueryBuilder


ROOT = Path(__file__).resolve().parents[1]
PROMETHEUS_VALUES = ROOT.parent / "Infrastructure" / "values" / "prometheus"


class RecordingRulesTest(unittest.TestCase):
    def test_plain_and_helm_rules_match_required_metric_contract(self):
        plain = yaml.safe_load(
            (PROMETHEUS_VALUES / "recording-rules.yml").read_text()
        )
        helm = yaml.safe_load(
            (PROMETHEUS_VALUES / "recording-rules.values.yaml").read_text()
        )["serverFiles"]["recording_rules.yml"]

        self.assertEqual(plain, helm)
        names = {
            rule["record"]
            for group in plain["groups"]
            for rule in group["rules"]
        }
        self.assertTrue(QueryBuilder.required_record_names() <= names)
        self.assertIn("anomaly_detector:http_5xx_rps", names)
        self.assertEqual("30s", plain["groups"][0]["interval"])

    def test_5xx_rule_is_a_guarded_ratio(self):
        rules = yaml.safe_load(
            (PROMETHEUS_VALUES / "recording-rules.yml").read_text()
        )["groups"][0]["rules"]
        expression = next(
            rule["expr"]
            for rule in rules
            if rule["record"] == "anomaly_detector:http_5xx_rate"
        )

        self.assertIn("100 / 120", expression)
        self.assertIn("5 / 120", expression)
        self.assertIn("clamp_min", expression)
        self.assertIn("anomaly_detector:http_5xx_rps", expression)


if __name__ == "__main__":
    unittest.main()
