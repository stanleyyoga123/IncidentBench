from datetime import datetime, timezone
from unittest import TestCase

from schema.anomaly import AnomalyBatch, AnomalyRow


def _row(
    *,
    row_id: int,
    name: str = "frontend",
    resource: str = "deployment",
    metric: str = "response_time_p95_seconds",
    detail: str | None = None,
) -> AnomalyRow:
    return AnomalyRow(
        id=row_id,
        timestamp=datetime(2026, 6, 26, 1, 2, 3, tzinfo=timezone.utc),
        resource=resource,
        name=name,
        metrics=metric,
        method="ZScoreLogic",
        detail=detail
        or "\n".join(
            [
                "anomaly_type = z_score_point_anomaly",
                f"resource = {resource}",
                f"name = {name}",
                f"metric = {metric}",
                "timestamp = 1717400030.0",
                "current_value = 1.82",
                "baseline_mean = 0.31",
                "baseline_std = 0.09",
                "z_score = 16.78",
                "severity = critical",
                "observed_direction = increase",
                "metric_semantics = request latency in seconds",
                "interpretation = latency is above_baseline",
                "rca_hints = check dependency latency and error rate",
                "remediation_hints = consider scaling if impact is confirmed",
            ]
        ),
    )


class AnomalyPromptTest(TestCase):
    def test_manager_prompt_surfaces_detector_fields(self):
        prompt = AnomalyBatch(anomalies=[_row(row_id=42)]).to_manager_prompt()

        self.assertIn("# Detector Anomaly Investigation", prompt)
        self.assertIn("Row ID: 42", prompt)
        self.assertIn("Metric: response_time_p95_seconds", prompt)
        self.assertIn("timestamp: 1717400030.0", prompt)
        self.assertIn("current_value: 1.82", prompt)
        self.assertIn("baseline_mean: 0.31", prompt)
        self.assertIn("z_score: 16.78", prompt)
        self.assertIn("severity: critical", prompt)
        self.assertIn("observed_direction: increase", prompt)
        self.assertIn("rca_hints: check dependency latency and error rate", prompt)
        self.assertIn(
            "remediation_hints: consider scaling if impact is confirmed", prompt
        )
        self.assertIn("Remediation Required", prompt)
        self.assertIn("Failed Investigation", prompt)
        self.assertIn("detector-named service as the observation point", prompt)
        self.assertIn("Impact Scope", prompt)
        self.assertIn("Missing Or Uncertain", prompt)

    def test_manager_prompt_groups_by_name_and_resource(self):
        batch = AnomalyBatch(
            anomalies=[
                _row(row_id=1, name="frontend"),
                _row(row_id=2, name="frontend", metric="traffic_rps"),
                _row(
                    row_id=4,
                    name="frontend",
                    resource="node",
                    metric="node_memory_utilization_percent",
                ),
                _row(
                    row_id=3,
                    name="worker-node-1",
                    resource="node",
                    metric="node_cpu_utilization_percent",
                ),
            ]
        )

        prompt = batch.to_manager_prompt()

        self.assertIn("## Group: deployment:frontend", prompt)
        self.assertIn("## Group: node:frontend", prompt)
        self.assertIn("## Group: node:worker-node-1", prompt)
        self.assertIn("Row IDs: [1, 2, 4, 3]", prompt)
        self.assertIn("traffic_rps", prompt)
        self.assertIn("node_memory_utilization_percent", prompt)
        self.assertIn("node_cpu_utilization_percent", prompt)
