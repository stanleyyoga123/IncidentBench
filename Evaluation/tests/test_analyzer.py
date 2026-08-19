import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyzer.cli import parse_args
from analyzer.errors import collect_errors
from analyzer.impact import metric_impact
from analyzer.judge.classify import session_highlights
from analyzer.judge.client import StaticJudge
from analyzer.judge.scorer import (
    apply_penalty,
    count_penalized_tools,
    end_score,
    operational_health,
    rca_component_score,
    remediator_component_score,
    rubric_score,
    score_rca_job,
    score_remediation_job,
)
from analyzer.sessions import scenario_context
from analyzer.pipeline import analyze
from analyzer.plots import plot_run
from analyzer.reports import write_run_report
from analyzer.timebase import chaos_t0, elapsed_minutes
from testbed.reporting.prometheus_metric_reader import PrometheusMetricReader


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "analyzer-run"


class AnalyzerTests(unittest.TestCase):
    def test_elapsed_minutes_zero_at_first_chaos(self):
        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        origin = chaos_t0(metadata)
        self.assertEqual(origin, 1700000000.0)
        self.assertAlmostEqual(elapsed_minutes(1699999400, origin), -10.0)
        self.assertAlmostEqual(elapsed_minutes(1700000000, origin), 0.0)

    def test_prometheus_read_all_keeps_baseline_points(self):
        frame = PrometheusMetricReader().read_all(FIXTURE, "deployment_cpu_usage")
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame["timestamp"].min(), 1699999400.0)

    def test_operational_errors_include_failed_tools_not_benign_locust(self):
        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        report = collect_errors(FIXTURE, metadata)
        kinds = {item["kind"] for item in report["errors"]}
        self.assertIn("tool_failure", kinds)
        self.assertIn("snapshot_command", kinds)
        self.assertIn("load_generator_stop", kinds)
        self.assertTrue(report["locust"]["benign_stop"])
        self.assertGreaterEqual(report["failed_tool_count"], 1)
        self.assertEqual(
            report["agent_error_count"],
            len([item for item in report["errors"] if item["kind"] != "load_generator_stop"]),
        )

    def test_metric_impact_detects_cpu_increase(self):
        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        impact = metric_impact(FIXTURE, metadata, chaos_t0(metadata))
        self.assertTrue(impact["observed"])
        self.assertTrue(impact["signals"]["deployment_cpu_usage"]["diverged"])

    def test_python_rubric_scoring_and_penalties(self):
        labels = {
            "localization": "correct",
            "evidence_quality": "partial",
            "necessity": "correct",
            "plan_quality": "incorrect",
            "grounding": "not_applicable",
        }
        raw = rubric_score(labels, tuple(labels))
        self.assertAlmostEqual(raw, (1 + 0.5 + 1 + 0) / 4)
        self.assertAlmostEqual(apply_penalty(raw, 1, "succeeded"), raw - 0.1)
        self.assertEqual(apply_penalty(raw, 0, "failed"), 0.0)
        self.assertAlmostEqual(
            end_score(
                impact_observed=True,
                rca_score=0.5,
                remediator_score=0.0,
                operational=0.8,
            ),
            0.20 * 1 + 0.30 * 0.5 + 0.30 * 0.0 + 0.20 * 0.8,
        )

    def test_plots_use_chaos_origin(self):
        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        with tempfile.TemporaryDirectory() as tmp:
            written = plot_run(FIXTURE, chaos_t0(metadata), Path(tmp))
            names = {path.name for path in written}
            self.assertIn("deployment_cpu_usage.png", names)
            self.assertIn("locust_aggregated.png", names)

    def test_pipeline_skip_judge_and_static_judge(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analysis"
            records = analyze(FIXTURE, output, judge=None, skip_judge=True)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]["scores"]["skipped"])
            self.assertTrue((output / "summary.csv").is_file())
            self.assertTrue((output / "runs" / "analyzer-run" / "errors.json").is_file())

        canned = [
            {
                "session_id": "rca-1",
                "session_kind": "true_positive",
                "matched_injection": "yes",
                "localization": "correct",
                "evidence_quality": "partial",
                "necessity": "correct",
                "plan_quality": "correct",
                "grounding": "correct",
                "false_alarm_recognition": "not_applicable",
                "harmlessness": "not_applicable",
                "impact_class": "helped",
                "evidence": "worker-node-1",
            },
            {
                "impact_observed": "yes",
                "rca_matched_injection": "yes",
                "remediation_attempted": "no",
                "successfully_remediated": "not_attempted",
                "impact_narrative": "CPU rose on the injected node; remediator did not run.",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "analysis"
            records = analyze(
                FIXTURE, output, judge=StaticJudge(list(canned)), skip_judge=False
            )
            scores = records[0]["scores"]
            self.assertFalse(scores["skipped"])
            self.assertGreater(scores["end_score"], 0)
            self.assertEqual(
                scores["holistic"]["successfully_remediated"], "not_attempted"
            )
            self.assertEqual(scores["components"]["remediator_invoked"], False)
            self.assertEqual(scores["rca"][0]["session_kind"], "true_positive")
            self.assertEqual(scores["rca"][0]["matched_injection"], "yes")
            self.assertEqual(scores["holistic"]["rca_matched_injection"], "yes")
            report = (output / "runs" / "analyzer-run" / "report.md").read_text()
            self.assertIn("## RCA sessions", report)
            self.assertIn("## Remediation sessions", report)
            self.assertIn("Remediated the injected fault", report)
            self.assertIn("Degraded the system", report)
            self.assertIn("No impactful change", report)
            self.assertIn("Most impactful", report)
            reused = analyze(FIXTURE, output, judge=None, reuse_judge=True)
            self.assertFalse(reused[0]["scores"]["skipped"])
            self.assertAlmostEqual(
                reused[0]["scores"]["end_score"], scores["end_score"]
            )

    def test_ground_truth_marks_matching_rca_true_positive(self):
        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        ground_truth = scenario_context(metadata)["ground_truth"]
        self.assertEqual(
            ground_truth["injected_faults"][0]["inferred_target"], "worker-node-1"
        )
        job = {
            "id": "rca-1",
            "status": "succeeded",
            "result": {
                "summary": "CPU stress on worker-node-1 affects checkoutservice.",
                "remediation_required": True,
            },
        }
        labels = {
            "session_id": "rca-1",
            "session_kind": "false_alarm",
            "matched_injection": "no",
            "localization": "incorrect",
            "evidence_quality": "partial",
            "necessity": "correct",
            "plan_quality": "correct",
            "grounding": "correct",
            "false_alarm_recognition": "not_applicable",
            "harmlessness": "not_applicable",
        }
        scored = score_rca_job(labels, job, 0, ground_truth)
        self.assertEqual(scored["session_kind"], "true_positive")
        self.assertEqual(scored["matched_injection"], "yes")
        self.assertEqual(scored["labels"]["localization"], "correct")

    def test_not_applicable_false_alarm_is_still_scored(self):
        job = {
            "id": "rca-2",
            "status": "succeeded",
            "result": {
                "summary": "Frontend replica count blip recovered.",
                "remediation_required": False,
                "incident_state": "unconfirmed",
            },
        }
        labels = {
            "session_id": "rca-2",
            "session_kind": "false_alarm",
            "matched_injection": "no",
            "localization": "not_applicable",
            "evidence_quality": "not_applicable",
            "necessity": "not_applicable",
            "plan_quality": "not_applicable",
            "grounding": "not_applicable",
            "false_alarm_recognition": "not_applicable",
            "harmlessness": "not_applicable",
        }
        ground_truth = {
            "injected_faults": [
                {
                    "reference": "node-delay-worker-3",
                    "child_type": "NetworkChaos",
                    "action": "delay",
                    "inferred_target": "worker-node-3",
                }
            ]
        }
        scored = score_rca_job(labels, job, 0, ground_truth)
        self.assertEqual(scored["session_kind"], "false_alarm")
        self.assertEqual(scored["matched_injection"], "no")
        self.assertEqual(scored["labels"]["false_alarm_recognition"], "correct")
        self.assertEqual(scored["labels"]["necessity"], "correct")
        self.assertGreater(scored["score"], 0)

    def test_cli_defaults_to_vllm_endpoint(self):
        with mock.patch.dict(os.environ):
            for key in ("JUDGE_URL", "JUDGE_MODEL", "JUDGE_TOKEN"):
                os.environ.pop(key, None)
            args = parse_args(["--skip-judge"])
        self.assertEqual(args.base_url, "http://localhost:8000/v1")
        self.assertEqual(args.model, "Qwen/Qwen3.6-35B-A3B")
        self.assertEqual(args.token, "EMPTY")
        self.assertTrue(args.skip_judge)

    def test_json_object_fallback_keeps_system_message_first(self):
        from analyzer.judge.client import JSON_OBJECT_HINT, with_json_object_hint

        messages = [
            {"role": "system", "content": "Classify the session."},
            {"role": "user", "content": "{}"},
        ]
        hinted = with_json_object_hint(messages)
        self.assertEqual(hinted[0]["role"], "system")
        self.assertIn(JSON_OBJECT_HINT, hinted[0]["content"])
        self.assertEqual(hinted[1]["role"], "user")
        self.assertEqual(messages[0]["content"], "Classify the session.")

    def test_successful_injection_match_is_not_diluted_by_false_alarms(self):
        true_positive = {
            "session_kind": "true_positive",
            "raw": 1.0,
            "score": 0.8,
            "impact_class": "helped",
        }
        false_alarms = [
            {
                "session_kind": "false_alarm",
                "raw": 0.3,
                "score": 0.1,
                "impact_class": "no_impact",
            }
        ] * 9
        rca = rca_component_score([true_positive, *false_alarms])
        self.assertGreater(rca, 0.85)
        rem = remediator_component_score(
            [
                {
                    "addressed_injection": "yes",
                    "raw": 1.0,
                    "impact_class": "helped",
                },
                *[
                    {
                        "addressed_injection": "no",
                        "raw": 0.0,
                        "impact_class": "no_impact",
                    }
                    for _ in range(7)
                ],
            ],
            [true_positive, *false_alarms],
            True,
            False,
        )
        self.assertGreater(rem, 0.75)
        final = end_score(
            impact_observed=True,
            rca_score=rca,
            remediator_score=rem,
            operational=operational_health(2),
        )
        self.assertGreater(final, 0.80)
        self.assertEqual(apply_penalty(1.0, 8, "succeeded"), 0.8)
        job = {
            "tool_calls": [
                {
                    "tool_name": "prometheus.query",
                    "ok": False,
                    "result": {"ok": False, "error": "http status error"},
                }
            ]
        }
        self.assertEqual(count_penalized_tools(job), 0)

    def test_drain_and_uncordon_are_best_and_worst_sessions(self):
        ground_truth = {
            "injected_faults": [
                {
                    "reference": "node-delay-worker-3",
                    "child_type": "NetworkChaos",
                    "action": "delay",
                    "inferred_target": "worker-node-3",
                }
            ]
        }
        drain_job = {
            "id": "rem-drain",
            "status": "succeeded",
            "result": {
                "summary": "Draining worker-node-3 to evacuate delayed services.",
                "remediation_plan": {
                    "action": "drain worker-node-3",
                    "targets": ["worker-node-3"],
                },
            },
            "tool_calls": [{"tool_name": "kubectl.drain", "ok": True}],
        }
        uncordon_job = {
            "id": "rem-uncordon",
            "status": "succeeded",
            "result": {
                "summary": "Uncordon worker-node-3 after a false recovery.",
                "remediation_plan": {
                    "action": "uncordon worker-node-3",
                    "targets": ["worker-node-3"],
                },
            },
            "tool_calls": [{"tool_name": "kubectl.uncordon", "ok": True}],
        }
        drain_labels = {
            "session_id": "rem-drain",
            "addressed_injection": "yes",
            "plan_alignment": "correct",
            "target_correctness": "correct",
            "execution_discipline": "correct",
            "verification": "correct",
            "safety": "correct",
            "evidence": "drain worker-node-3",
        }
        uncordon_labels = {
            "session_id": "rem-uncordon",
            "addressed_injection": "no",
            "plan_alignment": "incorrect",
            "target_correctness": "incorrect",
            "execution_discipline": "partial",
            "verification": "partial",
            "safety": "incorrect",
            "impact_class": "helped",
            "evidence": "uncordon worker-node-3",
        }
        drain = score_remediation_job(drain_labels, drain_job, 0, ground_truth)
        uncordon = score_remediation_job(uncordon_labels, uncordon_job, 0, ground_truth)
        self.assertEqual(drain["impact_class"], "helped")
        self.assertEqual(uncordon["impact_class"], "harmed")
        highlights = session_highlights([], [drain, uncordon])
        self.assertEqual(highlights["best"]["session_id"], "rem-drain")
        self.assertEqual(highlights["worst"]["session_id"], "rem-uncordon")
        self.assertIn("uncordon", highlights["worst"]["reason"].lower())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            write_run_report(
                path,
                {
                    "run_id": "demo",
                    "scenario": "node-delay-worker-3",
                    "mode": "agent",
                    "t0": 1,
                    "plots": [],
                    "errors": {"agent_error_count": 0, "errors": []},
                    "impact": {"observed": True},
                    "scores": {
                        "end_score": 0.9,
                        "weights": {"impact": 0.2},
                        "holistic": {
                            "successfully_remediated": "yes",
                            "rca_matched_injection": "yes",
                            "impact_narrative": "Drained the delayed node.",
                        },
                        "components": {
                            "impact_observed": True,
                            "rca": 0.9,
                            "remediation": 0.8,
                            "operational": 1.0,
                        },
                        "highlights": highlights,
                        "categories": {
                            "helped": [highlights["best"]],
                            "harmed": [highlights["worst"]],
                            "no_impact": [],
                        },
                        "rca": [],
                        "remediation": [drain, uncordon],
                    },
                },
            )
            report = path.read_text()
            self.assertIn("| session | addressed | impact | score |", report)
            self.assertIn("rem-drain", report)
            self.assertIn("rem-uncordon", report)
            self.assertIn("Most impactful", report)
            self.assertIn("Worst", report)

    def test_cli_reuse_judge_flag(self):
        args = parse_args(["--reuse-judge"])
        self.assertTrue(args.reuse_judge)
        self.assertFalse(args.skip_judge)


if __name__ == "__main__":
    unittest.main()
