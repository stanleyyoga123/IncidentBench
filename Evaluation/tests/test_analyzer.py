import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyzer.cli import parse_args
from analyzer.errors import collect_errors
from analyzer.ground_truth import DEFAULT_GROUND_TRUTH_DIR, load_ground_truth
from analyzer.impact import metric_impact
from analyzer.judge.classify import session_highlights
from analyzer.judge.client import DEFAULT_MAX_TOKENS, StaticJudge, VLLMJudge
from analyzer.judge.run import judge_run
from analyzer.judge.run import score_labeled_run
from analyzer.judge.scorer import (
    accuracy_metrics,
    apply_penalty,
    count_penalized_tools,
    end_score,
    efficiency_metrics,
    ground_truth_metrics,
    operational_health,
    rca_component_score,
    remediator_component_score,
    rubric_score,
    score_rca_job,
    score_remediation_job,
)
from analyzer.sessions import match_injected_fault, scenario_context
from analyzer.pipeline import analyze
from analyzer.plots import plot_run
from analyzer.reports import write_run_report
from analyzer.timebase import chaos_t0, elapsed_minutes
from testbed.reporting.prometheus_metric_reader import PrometheusMetricReader


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "analyzer-run"


class AnalyzerTests(unittest.TestCase):
    def test_markdown_ground_truth_has_result_scenarios(self):
        entries = load_ground_truth(DEFAULT_GROUND_TRUTH_DIR)
        self.assertIn("real-node-delay-worker-3-one-hour", entries)
        self.assertIn("worker-node-3", entries["real-node-delay-worker-3-one-hour"]["rca"])
        self.assertIn(
            "cordon and drain",
            entries["real-node-delay-worker-3-one-hour"]["remediation"].lower(),
        )

    def test_judge_timeout_is_configurable(self):
        self.assertEqual(DEFAULT_MAX_TOKENS, 8192)
        self.assertEqual(parse_args([]).judge_timeout_seconds, 600.0)
        self.assertEqual(
            parse_args(["--judge-timeout-seconds", "90"]).judge_timeout_seconds,
            90.0,
        )

    def test_vllm_timeout_does_not_repeat_same_request(self):
        judge = object.__new__(VLLMJudge)
        with mock.patch.object(
            judge, "_create", side_effect=TimeoutError("request timed out")
        ) as create:
            with self.assertRaises(TimeoutError):
                judge.complete("labels", {"type": "object"}, [])
        create.assert_called_once()

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

    def test_python_rubric_scoring_uses_fixed_denominator_without_tool_penalty(self):
        labels = {
            "localization": "correct",
            "evidence_quality": "partial",
            "necessity": "correct",
            "plan_quality": "incorrect",
            "grounding": "not_applicable",
        }
        raw = rubric_score(labels, tuple(labels))
        self.assertAlmostEqual(raw, (1 + 0.5 + 1 + 0 + 0) / 5)
        self.assertAlmostEqual(apply_penalty(raw, 1, "succeeded"), raw)
        self.assertEqual(apply_penalty(raw, 0, "failed"), 0.0)
        self.assertAlmostEqual(
            end_score(
                impact_observed=True,
                rca_score=0.5,
                remediator_score=0.0,
                operational=0.8,
            ),
            0.40 * 0.5 + 0.40 * 0.0 + 0.20 * 0.8,
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
                "attempt_class": "targeted",
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
                "evidence_refs": ["tool-001"],
                "confidence": "high",
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
            self.assertEqual(scores["components"]["evidence_coverage"], 1.0)
            self.assertEqual(scores["components"]["metric_confidence"], 1.0)
            report = (output / "runs" / "analyzer-run" / "report.md").read_text()
            self.assertIn("## RCA sessions", report)
            self.assertIn("## Remediation sessions", report)
            self.assertIn("Remediated the injected fault", report)
            self.assertIn("Degraded the system", report)
            self.assertIn("No impactful change", report)
            self.assertIn("Most impactful", report)
            cached = analyze(
                FIXTURE, output, judge=StaticJudge([]), skip_judge=False
            )
            self.assertAlmostEqual(
                cached[0]["scores"]["end_score"], scores["end_score"]
            )
            reused = analyze(FIXTURE, output, judge=None, reuse_judge=True)
            self.assertFalse(reused[0]["scores"]["skipped"])
            self.assertAlmostEqual(
                reused[0]["scores"]["end_score"], scores["end_score"]
            )

    def test_judge_failure_is_conservative_and_retryable(self):
        class FailingJudge:
            model = "failing-test-model"

            def __init__(self):
                self.calls = 0

            def complete(self, name, schema, messages):
                self.calls += 1
                raise TimeoutError("request timed out")

        metadata = json.loads((FIXTURE / "metadata.json").read_text())
        errors = collect_errors(FIXTURE, metadata)
        impact = metric_impact(FIXTURE, metadata, chaos_t0(metadata))
        judge = FailingJudge()
        with tempfile.TemporaryDirectory() as tmp:
            checkpoint = Path(tmp) / "judge.json"
            first = judge_run(
                FIXTURE, metadata, errors, impact, judge, checkpoint
            )
            self.assertEqual(first["components"]["judge_error_count"], 1)
            self.assertTrue(first["components"]["holistic_judge_error"])
            self.assertEqual(first["rca"][0]["score"], 0.0)
            self.assertEqual(first["components"]["metric_confidence"], 0.0)
            self.assertEqual(judge.calls, 2)

            judge_run(FIXTURE, metadata, errors, impact, judge, checkpoint)
            self.assertEqual(judge.calls, 4)

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
            "session_kind": "true_positive",
            "matched_injection": "yes",
            "localization": "correct",
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

    def test_ground_truth_match_does_not_override_conservative_judge(self):
        ground_truth = {
            "injected_faults": [
                {
                    "reference": "single-cartservice-cpu",
                    "child_type": "StressChaos",
                    "action": None,
                    "inferred_target": "cartservice",
                }
            ]
        }
        job = {
            "id": "rca-traffic",
            "status": "succeeded",
            "result": {
                "summary": "Cartservice CPU saturation is caused by traffic and HPA capacity.",
                "remediation_required": True,
            },
        }
        labels = {
            "session_id": "rca-traffic",
            "session_kind": "true_positive",
            "matched_injection": "yes",
            "localization": "correct",
            "evidence_quality": "partial",
            "necessity": "incorrect",
            "plan_quality": "incorrect",
            "grounding": "incorrect",
            "false_alarm_recognition": "incorrect",
            "harmlessness": "incorrect",
        }
        scored = score_rca_job(labels, job, 0, ground_truth)
        self.assertNotEqual(scored["matched_injection"], "yes")

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
                    "action": "network-delay",
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

    def test_all_sessions_contribute_to_run_scores(self):
        true_positive = {
            "session_kind": "true_positive",
            "raw": 1.0,
            "score": 0.8,
            "matched_injection": "yes",
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
        self.assertAlmostEqual(rca, 0.422)
        rem = remediator_component_score(
            [
                {
                    "addressed_injection": "yes",
                    "raw": 1.0,
                    "score": 1.0,
                    "impact_class": "helped",
                },
                *[
                    {
                        "addressed_injection": "no",
                        "raw": 0.0,
                        "score": 0.0,
                        "impact_class": "no_impact",
                    }
                    for _ in range(7)
                ],
            ],
            [true_positive, *false_alarms],
            True,
            False,
        )
        self.assertAlmostEqual(rem, 0.125)
        final = end_score(
            impact_observed=True,
            rca_score=rca,
            remediator_score=rem,
            operational=operational_health(2),
        )
        self.assertLess(final, 0.5)
        self.assertEqual(apply_penalty(1.0, 8, "succeeded"), 1.0)
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

    def test_side_effect_requires_grounded_evidence_and_ignores_tool_error(self):
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
        job = {
            "id": "rca-cpu",
            "status": "succeeded",
            "result": {
                "summary": (
                    "Frontend CPU utilization is sustained at 98% under legitimate "
                    "traffic and has little burst headroom."
                ),
                "remediation_required": True,
            },
            "tool_calls": [
                {
                    "tool_name": "prometheus.query",
                    "arguments": {"query": "frontend cpu utilization"},
                    "result": {"value": 98.0},
                    "ok": False,
                }
            ],
        }
        labels = {
            "session_id": "rca-cpu",
            "session_kind": "false_alarm",
            "attempt_class": "side_effect",
            "matched_injection": "no",
            "localization": "incorrect",
            "evidence_quality": "correct",
            "necessity": "partial",
            "plan_quality": "partial",
            "grounding": "correct",
            "false_alarm_recognition": "incorrect",
            "harmlessness": "correct",
            "impact_class": "no_impact",
            "evidence": "Prometheus reports sustained frontend CPU at 98%.",
            "evidence_refs": ["tool-001"],
            "confidence": "high",
        }
        side_effect = score_rca_job(labels, job, 1, ground_truth)
        self.assertEqual(side_effect["attempt_class"], "side_effect")
        self.assertEqual(side_effect["efficiency_credit"], 1.0)
        self.assertGreater(side_effect["score"], 0.0)

        unsupported = score_rca_job(
            {**labels, "evidence_refs": []}, job, 1, ground_truth
        )
        self.assertEqual(unsupported["attempt_class"], "false_alarm")
        self.assertEqual(unsupported["efficiency_credit"], 0.0)

    def test_network_path_degradation_matches_injected_delay(self):
        ground_truth = {
            "injected_faults": [
                {
                    "reference": "node-delay-worker-3",
                    "child_type": "NetworkChaos",
                    "action": "network-delay",
                    "inferred_target": "worker-node-3",
                }
            ]
        }
        job = {
            "result": {
                "summary": (
                    "Network-induced performance degradation on worker-node-3 "
                    "is producing sustained overlay network latency."
                )
            }
        }
        self.assertEqual(match_injected_fault(job, ground_truth), "yes")

    def test_rca_rollback_does_not_turn_correct_plan_into_harm(self):
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
        job = {
            "id": "rca-delay-with-rollback",
            "status": "succeeded",
            "result": {
                "summary": "Network path degradation is isolated to worker-node-3.",
                "remediation_required": True,
                "remediation_plan": {
                    "action": "Cordon and drain worker-node-3.",
                    "targets": ["worker-node-3"],
                    "rollback": "Uncordon worker-node-3 after the delay is removed.",
                },
            },
            "tool_calls": [
                {
                    "tool_name": "network.probe",
                    "arguments": {"node": "worker-node-3"},
                    "result": {"rtt_ms": 250},
                    "ok": True,
                }
            ],
        }
        labels = {
            "session_id": job["id"],
            "session_kind": "true_positive",
            "attempt_class": "targeted",
            "matched_injection": "yes",
            "localization": "correct",
            "evidence_quality": "correct",
            "necessity": "correct",
            "plan_quality": "correct",
            "grounding": "correct",
            "false_alarm_recognition": "not_applicable",
            "harmlessness": "correct",
            "impact_class": "helped",
            "evidence": "The probe confirms elevated RTT on worker-node-3.",
            "evidence_refs": ["tool-001"],
            "confidence": "high",
        }
        scored = score_rca_job(labels, job, 0, ground_truth)
        self.assertEqual(scored["matched_injection"], "yes")
        self.assertEqual(scored["attempt_class"], "targeted")
        self.assertEqual(scored["impact_class"], "helped")

    def test_linked_safe_remediation_can_be_side_effect(self):
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
        linked_rca = {
            "attempt_judged": True,
            "attempt_class": "side_effect",
        }
        job = {
            "id": "rem-cpu",
            "rca_job_id": "rca-cpu",
            "status": "failed",
            "result": {"summary": "Lower the frontend HPA target for CPU headroom."},
            "tool_calls": [
                {
                    "tool_name": "kubectl",
                    "arguments": {"args": ["patch", "hpa", "frontend"]},
                    "result": {"ok": False, "error": "bad first invocation"},
                    "ok": False,
                }
            ],
        }
        labels = {
            "session_id": "rem-cpu",
            "addressed_injection": "no",
            "attempt_class": "side_effect",
            "plan_alignment": "correct",
            "target_correctness": "incorrect",
            "execution_discipline": "partial",
            "verification": "not_applicable",
            "safety": "correct",
            "recovery_proven": "no",
            "recovery_evidence_refs": [],
            "impact_class": "no_impact",
            "evidence": "The attempted HPA patch targets the evidenced CPU risk.",
            "evidence_refs": ["tool-001"],
            "confidence": "high",
        }
        scored = score_remediation_job(
            labels, job, 1, ground_truth, linked_rca
        )
        self.assertEqual(scored["attempt_class"], "side_effect")
        self.assertEqual(scored["efficiency_credit"], 1.0)
        self.assertEqual(scored["fix_outcome"], "unsuccessful")

    def test_accuracy_requires_service_recovery_and_links_rca(self):
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
        rca_job = {
            "id": "rca-delay",
            "status": "succeeded",
            "result": {
                "summary": "Network delay on worker-node-3 is the root cause.",
                "remediation_required": True,
            },
            "tool_calls": [
                {
                    "tool_name": "network.probe",
                    "arguments": {"node": "worker-node-3"},
                    "result": {"latency_ms": 250},
                    "ok": True,
                }
            ],
        }
        remediation_job = {
            "id": "rem-delay",
            "rca_job_id": "rca-delay",
            "status": "succeeded",
            "result": {"summary": "Drain worker-node-3 and evacuate its workloads."},
            "tool_calls": [
                {
                    "tool_name": "kubectl.drain",
                    "arguments": {"node": "worker-node-3"},
                    "result": {"ok": True},
                    "ok": True,
                },
                {
                    "tool_name": "prometheus.query",
                    "arguments": {"query": "frontend response_time latency"},
                    "result": {"before": 1.2, "after": 0.08},
                    "ok": True,
                },
            ],
        }
        raw = {
            "rca": [
                {
                    "session_id": "rca-delay",
                    "session_kind": "true_positive",
                    "attempt_class": "targeted",
                    "matched_injection": "yes",
                    "localization": "correct",
                    "evidence_quality": "correct",
                    "necessity": "correct",
                    "plan_quality": "correct",
                    "grounding": "correct",
                    "false_alarm_recognition": "not_applicable",
                    "harmlessness": "correct",
                    "impact_class": "helped",
                    "evidence": "The node probe measured the injected delay.",
                    "evidence_refs": ["tool-001"],
                    "confidence": "high",
                }
            ],
            "remediation": [
                {
                    "session_id": "rem-delay",
                    "addressed_injection": "yes",
                    "attempt_class": "targeted",
                    "plan_alignment": "correct",
                    "target_correctness": "correct",
                    "execution_discipline": "correct",
                    "verification": "correct",
                    "safety": "correct",
                    "recovery_proven": "yes",
                    "recovery_evidence_refs": ["tool-002"],
                    "impact_class": "helped",
                    "evidence": "Latency recovered after draining the delayed node.",
                    "evidence_refs": ["tool-001", "tool-002"],
                    "confidence": "high",
                }
            ],
            "holistic": {},
        }
        sessions = {
            "rca": [rca_job],
            "remediation": [remediation_job],
            "workflow": [],
        }
        scores = score_labeled_run(
            Path("."),
            {},
            {"errors": []},
            {"observed": True},
            raw,
            sessions,
            {"ground_truth": ground_truth},
        )
        self.assertEqual(scores["components"]["accuracy"], 1.0)
        self.assertTrue(scores["components"]["accuracy_complete"])
        self.assertEqual(scores["components"]["efficiency"], 1.0)
        self.assertEqual(scores["remediation"][0]["fix_outcome"], "success")
        self.assertTrue(scores["rca"][0]["led_to_success"])

        mutation_only = score_remediation_job(
            {
                **raw["remediation"][0],
                "recovery_evidence_refs": ["tool-001"],
            },
            remediation_job,
            0,
            ground_truth,
            scores["rca"][0],
        )
        self.assertFalse(mutation_only["recovery_proven"])
        self.assertEqual(mutation_only["fix_outcome"], "unsuccessful")

        pre_action_only = score_remediation_job(
            {
                **raw["remediation"][0],
                "recovery_evidence_refs": ["tool-001"],
            },
            {
                **remediation_job,
                "tool_calls": list(reversed(remediation_job["tool_calls"])),
            },
            0,
            ground_truth,
            scores["rca"][0],
        )
        self.assertFalse(pre_action_only["recovery_proven"])
        self.assertEqual(pre_action_only["fix_outcome"], "unsuccessful")

    def test_efficiency_and_accuracy_exclude_unjudged_attempts(self):
        metrics = efficiency_metrics(
            [
                {
                    "attempt_judged": True,
                    "attempt_class": "targeted",
                    "efficiency_credit": 1.0,
                },
                {
                    "attempt_judged": True,
                    "attempt_class": "side_effect",
                    "efficiency_credit": 1.0,
                },
            ],
            [
                {
                    "attempt_judged": True,
                    "attempt_class": "false_alarm",
                    "efficiency_credit": 0.0,
                },
                {
                    "attempt_judged": False,
                    "attempt_class": None,
                    "efficiency_credit": None,
                },
            ],
        )
        self.assertAlmostEqual(metrics["efficiency"], 2 / 3)
        self.assertEqual(metrics["attempt_coverage"], 0.75)
        self.assertFalse(metrics["efficiency_complete"])
        self.assertEqual(metrics["side_effect_attempt_count"], 1)
        self.assertEqual(metrics["efficiency_false_alarm_count"], 1)

        unknown = accuracy_metrics(
            [{"attempt_judged": False, "fix_outcome": "unsuccessful"}]
        )
        self.assertIsNone(unknown["accuracy"])
        self.assertFalse(unknown["accuracy_complete"])
        failed_unjudged = accuracy_metrics(
            [
                {
                    "attempt_judged": False,
                    "fix_outcome": "unsuccessful",
                    "status": "failed",
                }
            ]
        )
        self.assertEqual(
            failed_unjudged,
            {"accuracy": 0.0, "accuracy_complete": True},
        )
        successful = accuracy_metrics(
            [
                {"attempt_judged": False, "fix_outcome": "unsuccessful"},
                {"attempt_judged": True, "fix_outcome": "success"},
            ]
        )
        self.assertEqual(successful["accuracy"], 1.0)
        self.assertTrue(successful["accuracy_complete"])
        self.assertEqual(
            accuracy_metrics(
                [{"attempt_judged": True, "fix_outcome": "unsuccessful"}]
            ),
            {"accuracy": 0.0, "accuracy_complete": True},
        )

    def test_two_layer_ground_truth_scoring(self):
        metrics = ground_truth_metrics(
            [
                {
                    "comparison_judged": True,
                    "ground_truth_match": True,
                    "system_harm": False,
                    "layer_score": 1.0,
                },
                {
                    "comparison_judged": True,
                    "ground_truth_match": False,
                    "system_harm": False,
                    "layer_score": 0.5,
                },
            ],
            [
                {
                    "comparison_judged": True,
                    "ground_truth_match": True,
                    "system_harm": False,
                    "layer_score": 1.0,
                },
                {
                    "comparison_judged": True,
                    "ground_truth_match": False,
                    "system_harm": True,
                    "layer_score": 0.0,
                },
            ],
        )
        self.assertEqual(metrics["accuracy"], 1.0)
        self.assertEqual(metrics["rca_accuracy"], 1.0)
        self.assertEqual(metrics["remediation_accuracy"], 1.0)
        self.assertEqual(metrics["ground_truth_score"], 0.625)
        self.assertEqual(metrics["safety_score"], 0.75)
        self.assertEqual(metrics["harmful_attempt_count"], 1)

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
            "evidence_refs": ["tool-001"],
            "confidence": "high",
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
            "evidence_refs": ["tool-001"],
            "confidence": "high",
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
            self.assertIn(
                "| session | ground-truth match | system harm | layer score |",
                report,
            )
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
