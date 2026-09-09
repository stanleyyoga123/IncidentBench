import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from testbed.artifacts import ArtifactLayout, MetadataRepository
from testbed.chaos.execution.cluster_chaos_state_cleaner import ClusterChaosStateCleaner
from testbed.command.command_logger import CommandLogger
from testbed.command.command_runner import CommandRunner
from testbed.evaluator.prometheus import PrometheusClient
from testbed.orchestration.baseline_phase import BaselinePhase
from testbed.orchestration import ExperimentRunner
from testbed.reporting import AgentComparator
from testbed.reporting.chaos_window import ChaosWindowReader
from testbed.reporting.metadata_reader import MetadataReader


class ArchitectureTests(unittest.TestCase):
    def test_baseline_waits_for_application_warmup_before_starting_load(self):
        events = []

        class Metadata:
            def write(self, _metadata):
                events.append("metadata")

        class Evaluator:
            def collect_snapshot(self, _name):
                events.append("snapshot")
                return {}

        process = SimpleNamespace(command=["locust"], process=SimpleNamespace(poll=lambda: None))
        context = SimpleNamespace(
            config=SimpleNamespace(
                startup_delay_seconds=180,
                application="teastore",
                repo_root=Path("/app"),
                output_dir=Path("/results"),
                loadgenerator="constant",
                loadgenerator_module="applications.teastore",
                host="http://teastore",
                baseline_seconds=0,
                agents_enabled=False,
            ),
            metadata={"snapshots": [], "loadgenerator": {}, "phases": []},
            evaluator=Evaluator(),
            load_process=None,
            run_started_wall=None,
            phase_results=[],
            total_load_duration=60,
        )
        phase = BaselinePhase(
            lambda **_kwargs: events.append("load") or process,
            lambda *_args: None,
            Metadata(),
            lambda _message: None,
            sleep=lambda seconds: events.append(f"sleep:{seconds}"),
        )

        phase.execute(context)

        self.assertEqual(events[:3], ["sleep:180", "snapshot", "load"])

    def test_main_is_a_small_entrypoint(self):
        testbed = Path(__file__).resolve().parents[1] / "testbed"
        main_path = testbed / "main.py"
        self.assertLess(len(main_path.read_text().splitlines()), 220)
        self.assertFalse((testbed / "evaluation_runner").exists())
        self.assertTrue((testbed / "orchestration").is_dir())
        self.assertTrue((testbed / "reporting").is_dir())

    def test_artifact_layout_owns_step_paths(self):
        layout = ArtifactLayout(Path("/tmp/run"))
        self.assertEqual(
            layout.chaos_step(2, "network"),
            Path("/tmp/run/injector/02-network"),
        )

    def test_metadata_repository_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            repository = MetadataRepository(Path(tmp) / "metadata.json")
            repository.write({"status": "running"})
            self.assertEqual(repository.read(), {"status": "running"})

    def test_reporting_rejects_historical_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "metadata.json"
            path.write_text('{"status": "completed"}')
            with self.assertRaisesRegex(ValueError, "expected version 2"):
                MetadataReader().read(Path(tmp))

    def test_reporting_reads_v2_multi_schedule_window(self):
        metadata = {
            "schema_version": 2,
            "chaos_definitions": [
                {"reference": "a", "child_type": "NetworkChaos", "action": "delay"},
                {"reference": "b", "child_type": "StressChaos", "action": None},
            ],
            "chaos_steps": [
                {
                    "index": 1,
                    "name": "multi",
                    "chaos": ["b", "a"],
                    "active_started_at": "2026-01-01T00:00:00+00:00",
                    "cleanup_started_at": "2026-01-01T00:01:00+00:00",
                    "status": "completed",
                },
                {"index": 2, "name": "idle", "chaos": [], "status": "completed"},
            ],
        }
        windows = ChaosWindowReader().windows(metadata)
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].chaos, ("a", "b"))
        self.assertEqual(windows[0].schedule_types, ("NetworkChaos", "StressChaos"))

    def test_agent_comparator_groups_each_chaos_step(self):
        summary = pd.DataFrame(
            [
                {
                    "scenario": "scenario-a",
                    "step_index": 1,
                    "step_name": "network",
                    "chaos": "checkout-delay",
                    "mode": "agent",
                    "avg_cpu_cores": 1.0,
                    "avg_response_ms": 50.0,
                    "avg_p95_ms": 100.0,
                    "peak_p95_ms": 200.0,
                    "avg_rps": 100.0,
                    "avg_5xx_rps": 0.0,
                    "failure_pct": 0.0,
                    "avg_instances": 2.0,
                },
                {
                    "scenario": "scenario-a",
                    "step_index": 1,
                    "step_name": "network",
                    "chaos": "checkout-delay",
                    "mode": "non-agent",
                    "avg_cpu_cores": 1.2,
                    "avg_response_ms": 100.0,
                    "avg_p95_ms": 200.0,
                    "peak_p95_ms": 400.0,
                    "avg_rps": 80.0,
                    "avg_5xx_rps": 1.0,
                    "failure_pct": 2.0,
                    "avg_instances": 2.0,
                },
            ]
        )
        comparison = AgentComparator().compare(summary)
        self.assertEqual(len(comparison), 1)
        self.assertEqual(comparison.iloc[0]["avg_response_ms_improvement_pct"], 50)
        self.assertEqual(comparison.iloc[0]["avg_rps_improvement_pct"], 25)

    def test_agent_comparator_accepts_different_soft_spread_outcomes(self):
        rows = []
        for mode, fingerprint in (("agent", "placement-a"), ("non-agent", "placement-b")):
            row = {
                "scenario": "scenario-a",
                "placement": "canonical-six-node",
                "placement_fingerprint": fingerprint,
                "placement_definition_fingerprint": "same-definition",
                "step_index": 1,
                "step_name": "network",
                "chaos": "node-loss",
                "mode": mode,
            }
            row.update({metric: 1.0 for metric in AgentComparator.METRICS})
            rows.append(row)
        comparison = AgentComparator().compare(pd.DataFrame(rows))
        self.assertEqual(len(comparison), 1)

    def test_agent_comparator_rejects_different_placement_definitions(self):
        rows = []
        for mode, fingerprint in (("agent", "definition-a"), ("non-agent", "definition-b")):
            row = {
                "scenario": "scenario-a",
                "placement": "canonical-six-node",
                "placement_definition_fingerprint": fingerprint,
                "step_index": 1,
                "step_name": "network",
                "chaos": "node-loss",
                "mode": mode,
            }
            row.update({metric: 1.0 for metric in AgentComparator.METRICS})
            rows.append(row)
        comparison = AgentComparator().compare(pd.DataFrame(rows))
        self.assertTrue(comparison.empty)

    def test_prometheus_range_normalizes_an_empty_window(self):
        client = PrometheusClient("http://prometheus.test")
        client._get = lambda url, timeout: "{}"
        timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        url, _ = client.query_range("up", timestamp, timestamp, 15)
        self.assertIn("2026-01-01T00%3A00%3A15%2B00%3A00", url)

    def test_cluster_cleanup_uses_authoritative_script_and_logs_result(self):
        calls = []

        def run(command, **kwargs):
            calls.append((command, kwargs))
            return SimpleNamespace(returncode=0, stdout="clean\n", stderr="")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "commands"
            cleaner = ClusterChaosStateCleaner(
                CommandRunner(run),
                root,
                CommandLogger(),
            )
            result = cleaner.clean(output)

            self.assertEqual(
                calls[0][0],
                ["bash", str(root / "cleanup_chaos_state.sh"), "--yes"],
            )
            self.assertEqual(calls[0][1]["cwd"], root)
            self.assertEqual(calls[0][1]["timeout"], 900)
            self.assertEqual(result["returncode"], 0)
            self.assertEqual((output / "cleanup.stdout").read_text(), "clean\n")

    def test_finalizer_error_is_recorded_instead_of_escaping(self):
        class Finalizer:
            def execute(self, context):
                raise RuntimeError("stop failed")

        class Metadata:
            path = Path("metadata.json")

            def write(self, metadata):
                self.value = metadata.copy()

        metadata = Metadata()
        context = SimpleNamespace(metadata={"status": "running"})
        returncode = ExperimentRunner([], Finalizer(), metadata, lambda _: None).run(
            context
        )
        self.assertEqual(returncode, 1)
        self.assertEqual(context.metadata["status"], "failed")
        self.assertIn("stop failed", context.metadata["finalization_error"])


if __name__ == "__main__":
    unittest.main()
