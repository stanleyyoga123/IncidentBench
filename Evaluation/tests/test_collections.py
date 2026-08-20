import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from testbed.artifacts import ArtifactLayout
from testbed.chaos.catalog import ChaosCatalog, ScheduleLoader
from testbed.chaos.execution.execution_context import ChaosExecutionContext
from testbed.chaos.execution.physical_machine_state_cleaner import (
    PhysicalMachineStateCleaner,
)
from testbed.chaos.execution.schedule_cleaner import ScheduleCleaner
from testbed.chaos.execution.scheduled_step_executor import ScheduledStepExecutor
from testbed.command import CommandLogger
from testbed.command.command_runner import CommandRunner
from testbed.domain import CommandResult, ScenarioStep
from testbed.kubernetes import ChaosScheduleClient
from testbed.orchestration.chaos_phase import ChaosPhase
from testbed.placement import (
    PlacementCatalog,
    PlacementRenderer,
    validate_pod_chaos_selectors,
)
from testbed.scenarios import ScenarioLoader


def schedule_manifest(name="network-delay", child_type="NetworkChaos"):
    keys = {
        "NetworkChaos": "networkChaos",
        "StressChaos": "stressChaos",
        "PhysicalMachineChaos": "physicalmachineChaos",
    }
    return {
        "apiVersion": "chaos-mesh.org/v1alpha1",
        "kind": "Schedule",
        "metadata": {"name": name, "namespace": "chaos-mesh"},
        "spec": {
            "schedule": "@every 30s",
            "historyLimit": 1,
            "concurrencyPolicy": "Forbid",
            "type": child_type,
            keys[child_type]: {"action": "delay", "duration": "25s"},
        },
    }


def write_schedule(folder: Path, reference: str, manifest=None):
    path = folder / f"{reference}.yaml"
    path.write_text(yaml.safe_dump(manifest or schedule_manifest(reference)))
    return path


def write_placement_collection(root: Path, reference="placement") -> PlacementCatalog:
    profile = root / "placement" / reference
    profile.mkdir(parents=True)
    (profile / "kustomization.yaml").write_text(
        "apiVersion: kustomize.config.k8s.io/v1beta1\n"
        "kind: Kustomization\n"
    )
    return PlacementCatalog(root / "placement")


class CollectionValidationTests(unittest.TestCase):
    def test_real_scenario_collection_and_chaos_catalog_are_valid(self):
        root = Path(__file__).resolve().parents[1]
        catalog = ChaosCatalog(root / "collections" / "chaos")
        placements = PlacementCatalog(
            root.parent / "Infrastructure" / "kubernetes" / "online-boutique" / "kustomize" / "overlays"
        )
        scenarios = [
            ScenarioLoader(root, catalog, placements).load(path)
            for path in sorted((root / "collections" / "real-scenario").glob("*.json"))
        ]
        self.assertEqual(len(catalog.schedules), 22)
        self.assertEqual(len(scenarios), 16)
        self.assertEqual(placements.references, ("canonical-six-node",))
        placement = PlacementRenderer(CommandRunner(), root).render(
            "canonical-six-node",
            placements.resolve("canonical-six-node"),
        )
        validate_pod_chaos_selectors(placement, catalog.schedules)
        referenced = {
            reference
            for scenario in scenarios
            for step in scenario.steps
            for reference in step.chaos
        }
        catalog_refs = {schedule.reference for schedule in catalog.schedules}
        self.assertTrue(referenced <= catalog_refs)
        self.assertEqual(
            referenced,
            {
                "node-delay-worker-2",
                "node-delay-peers-to-worker-2",
                "node-delay-worker-3",
                "node-delay-peers-to-worker-3",
                "node-delay-worker-5",
                "node-delay-peers-to-worker-5",
                "node-loss-worker-1",
                "node-loss-worker-2",
                "node-loss-worker-3",
                "single-cartservice-cpu",
                "single-cartservice-cpu-worker-1",
                "single-checkoutservice-cpu",
                "single-checkoutservice-cpu-worker-2",
                "single-recommendationservice-cpu",
                "single-recommendationservice-cpu-worker-1",
                "single-productcatalogservice-cpu",
                "single-productcatalogservice-cpu-worker-3",
                "single-paymentservice-cpu",
                "single-paymentservice-cpu-worker-5",
            },
        )
        self.assertNotIn("node-delay-worker-4", catalog_refs)
        self.assertNotIn("node-delay-peers-to-worker-4", catalog_refs)
        for schedule in catalog.schedules:
            child = schedule.manifest["spec"][schedule.child_key]
            selector = child["selector"]
            if schedule.reference.startswith("node-"):
                nodes = selector["physicalMachines"]["chaos-mesh"]
                if schedule.reference.startswith("node-delay-peers-to-worker-"):
                    remote_index = schedule.reference.rsplit("-", 1)[1]
                    expected_peers = {
                        f"worker-node-{index}"
                        for index in range(1, 7)
                        if str(index) != remote_index
                    }
                    self.assertEqual(set(nodes), expected_peers)
                    self.assertEqual(child["mode"], "all")
                else:
                    self.assertEqual(len(nodes), 1)
            else:
                self.assertEqual(selector["namespaces"], ["online-boutique"])
                expressions = selector["expressionSelectors"]
                self.assertEqual(expressions[0]["key"], "app")
                self.assertEqual(expressions[0]["operator"], "In")
                self.assertTrue(schedule.reference.startswith("single-"))
                self.assertEqual(len(expressions[0]["values"]), 1)
                self.assertNotIn("frontend", expressions[0]["values"])
                if "nodes" in selector:
                    known_nodes = {
                        node
                        for nodes in placement.allowed_nodes.values()
                        for node in nodes
                    }
                    self.assertTrue(set(selector["nodes"]) <= known_nodes)
        for scenario in scenarios:
            self.assertEqual(scenario.placement, "canonical-six-node")
            self.assertEqual(len(scenario.steps), 2)
            chaos_step, recovery_step = scenario.steps
            self.assertFalse(chaos_step.idle)
            self.assertEqual(chaos_step.duration, 3600)
            self.assertTrue(recovery_step.idle)
            self.assertEqual(recovery_step.duration, 600)
            self.assertTrue(recovery_step.name.endswith("recovery") or recovery_step.name == "02-recovery")

    def test_long_scenario_collection_is_a_one_day_multi_fault(self):
        root = Path(__file__).resolve().parents[1]
        catalog = ChaosCatalog(root / "collections" / "chaos")
        placements = PlacementCatalog(
            root.parent / "Infrastructure" / "kubernetes" / "online-boutique" / "kustomize" / "overlays"
        )
        paths = sorted((root / "collections" / "long-scenario").glob("*.json"))
        self.assertEqual([path.name for path in paths], ["01-multi-fault-one-day.json"])
        scenario = ScenarioLoader(root, catalog, placements).load(paths[0])
        self.assertEqual(scenario.name, "long-multi-fault-one-day")
        self.assertEqual(scenario.placement, "canonical-six-node")
        self.assertEqual(sum(step.duration for step in scenario.steps), 82800)
        chaos_steps = [step for step in scenario.steps if not step.idle]
        recovery_steps = [step for step in scenario.steps if step.idle]
        self.assertEqual(len(chaos_steps), 4)
        self.assertEqual(len(recovery_steps), 5)
        self.assertTrue(scenario.steps[0].idle)
        self.assertEqual(scenario.steps[0].duration, 3600)
        self.assertTrue(scenario.steps[-1].idle)
        self.assertEqual(
            [(step.duration, step.chaos) for step in scenario.steps],
            [
                (3600, ()),
                (7200, ("node-delay-worker-3", "node-delay-peers-to-worker-3")),
                (10800, ()),
                (1800, ("node-loss-worker-3",)),
                (23400, ()),
                (3600, ("single-productcatalogservice-cpu",)),
                (18000, ()),
                (7200, ("node-delay-worker-5", "node-delay-peers-to-worker-5")),
                (7200, ()),
            ],
        )

    def test_scenario_supports_multiple_schedules_and_idle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chaos = root / "chaos"
            chaos.mkdir()
            write_schedule(chaos, "a")
            write_schedule(chaos, "b", schedule_manifest("b", "StressChaos"))
            placements = write_placement_collection(root)
            path = root / "scenario.json"
            path.write_text(
                json.dumps(
                    {
                        "name": "scenario",
                        "placement": "placement",
                        "steps": [
                            {"name": "chaos", "chaos": ["a", "b"], "duration": 30},
                            {"name": "idle", "chaos": [], "duration": 10},
                        ],
                    }
                )
            )
            scenario = ScenarioLoader(
                root,
                ChaosCatalog(chaos),
                placements,
            ).load(path)
        self.assertEqual(scenario.steps[0].chaos, ("a", "b"))
        self.assertTrue(scenario.steps[1].idle)

    def test_scenario_rejects_unknown_duplicate_and_slow_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chaos = root / "chaos"
            chaos.mkdir()
            write_schedule(chaos, "a")
            catalog = ChaosCatalog(chaos)
            placements = write_placement_collection(root)
            loader = ScenarioLoader(root, catalog, placements)
            cases = [
                ({"name": "x", "chaos": ["missing"], "duration": 30}, "unknown"),
                ({"name": "x", "chaos": ["a", "a"], "duration": 30}, "unique"),
                ({"name": "x", "chaos": ["a"], "duration": 29}, "shorter"),
                ({"name": "x", "chaos": [], "duration": 1, "extra": 1}, "unknown fields"),
            ]
            for index, (step, message) in enumerate(cases):
                path = root / f"{index}.json"
                path.write_text(
                    json.dumps(
                        {
                            "name": "scenario",
                            "placement": "placement",
                            "steps": [step],
                        }
                    )
                )
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    loader.load(path)

    def test_scenario_requires_a_known_safe_placement_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chaos = root / "chaos"
            chaos.mkdir()
            placements = write_placement_collection(root)
            loader = ScenarioLoader(root, ChaosCatalog(chaos), placements)
            cases = [
                ({"name": "scenario", "steps": []}, "placement reference"),
                (
                    {"name": "scenario", "placement": "missing", "steps": []},
                    "unknown placement",
                ),
                (
                    {"name": "scenario", "placement": "../bad", "steps": []},
                    "safe",
                ),
            ]
            for index, (value, message) in enumerate(cases):
                path = root / f"placement-{index}.json"
                path.write_text(json.dumps(value))
                with self.subTest(message=message), self.assertRaisesRegex(
                    ValueError, message
                ):
                    loader.load(path)

    def test_canonical_placement_renders_the_expected_service_map(self):
        root = Path(__file__).resolve().parents[1]
        catalog = PlacementCatalog(
            root.parent / "Infrastructure" / "kubernetes" / "online-boutique" / "kustomize" / "overlays"
        )
        profile = PlacementRenderer(CommandRunner(), root).render(
            "canonical-six-node",
            catalog.resolve("canonical-six-node"),
        )
        self.assertEqual(
            profile.allowed_nodes,
            {
                "adservice": ("worker-node-1",),
                "cartservice": ("worker-node-1",),
                "checkoutservice": ("worker-node-2", "worker-node-4"),
                "currencyservice": ("worker-node-3", "worker-node-5"),
                "emailservice": ("worker-node-2", "worker-node-4"),
                "frontend": ("worker-node-1", "worker-node-2", "worker-node-6"),
                "paymentservice": ("worker-node-3", "worker-node-5"),
                "productcatalogservice": ("worker-node-3", "worker-node-5"),
                "recommendationservice": ("worker-node-1",),
                "redis-cart": ("worker-node-4", "worker-node-6"),
                "shippingservice": ("worker-node-4", "worker-node-6"),
            },
        )

    def test_schedule_validation_rejects_contract_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = schedule_manifest()
            mutations = [
                (lambda value: value.update(kind="NetworkChaos"), "kind"),
                (lambda value: value["metadata"].update(namespace="default"), "namespace"),
                (lambda value: value["spec"].update(historyLimit=2), "historyLimit"),
                (lambda value: value["spec"].update(concurrencyPolicy="Allow"), "concurrencyPolicy"),
                (lambda value: value["spec"].update(schedule="* * * * *"), "@every"),
                (lambda value: value["spec"]["networkChaos"].update(duration="30s"), "less than"),
            ]
            for index, (mutate, message) in enumerate(mutations):
                value = json.loads(json.dumps(base))
                mutate(value)
                path = root / f"bad-{index}.yaml"
                path.write_text(yaml.safe_dump(value))
                with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                    ScheduleLoader().load(path)

    def test_catalog_rejects_duplicate_kubernetes_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_schedule(root, "a", schedule_manifest("same"))
            write_schedule(root, "b", schedule_manifest("same"))
            with self.assertRaisesRegex(ValueError, "duplicate Schedule identity"):
                ChaosCatalog(root)

class FakeClient:
    def __init__(self, failing=None):
        self.failing = failing
        self.applied = []

    def apply(self, schedule):
        self.applied.append(schedule.reference)
        return CommandResult(
            command=("kubectl", "apply"),
            returncode=1 if schedule.reference == self.failing else 0,
            stderr="failed" if schedule.reference == self.failing else "",
        )


class FakeCleaner:
    def __init__(self, failing_prefix=None):
        self.calls = []
        self.failing_prefix = failing_prefix

    def clean(self, schedule, output, prefix):
        self.calls.append((prefix, schedule.reference))
        failed = self.failing_prefix == (prefix, schedule.reference)
        return {"returncode": 1 if failed else 0, "absent": not failed}


class ScheduledExecutionTests(unittest.TestCase):
    def make_executor(self, root, failing_apply=None, failing_cleanup=None):
        chaos = root / "chaos"
        chaos.mkdir()
        write_schedule(chaos, "a")
        write_schedule(chaos, "b", schedule_manifest("b", "StressChaos"))
        catalog = ChaosCatalog(chaos)
        client = FakeClient(failing_apply)
        cleaner = FakeCleaner(failing_cleanup)
        clock = iter([10.0, 15.0])
        executor = ScheduledStepExecutor(
            catalog,
            client,
            cleaner,
            CommandLogger(),
            monotonic=lambda: next(clock),
        )
        return executor, client, cleaner

    def test_multiple_schedules_apply_then_cleanup_in_reverse(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor, client, cleaner = self.make_executor(root)
            waits = []
            context = ChaosExecutionContext(
                ArtifactLayout(root / "output"),
                lambda duration, started: waits.append((duration, started)),
                lambda message: None,
                lambda result: None,
            )
            result = executor.execute(
                ScenarioStep(1, "multi", ("a", "b"), 30), context
            )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(client.applied, ["a", "b"])
        self.assertEqual(waits, [(30, 10.0)])
        self.assertEqual(
            cleaner.calls,
            [("prepare", "a"), ("prepare", "b"), ("cleanup", "b"), ("cleanup", "a")],
        )
        self.assertEqual(result["actual_active_duration_seconds"], 5.0)

    def test_apply_failure_rolls_back_and_cleanup_failure_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor, client, cleaner = self.make_executor(
                root, failing_apply="b", failing_cleanup=("cleanup", "a")
            )
            context = ChaosExecutionContext(
                ArtifactLayout(root / "output"),
                lambda *_: None,
                lambda _: None,
                lambda result: None,
            )
            result = executor.execute(
                ScenarioStep(1, "multi", ("a", "b"), 30), context
            )
        self.assertEqual(client.applied, ["a", "b"])
        self.assertEqual(result["status"], "cleanup_failed")
        self.assertEqual(cleaner.calls[-2:], [("cleanup", "b"), ("cleanup", "a")])

    def test_chaos_phase_maps_cleanup_and_interrupt_exit_codes(self):
        class Executor:
            def __init__(self, status):
                self.status = status

            def execute(self, steps, context):
                return [{"status": self.status}]

        class Metadata:
            def write(self, value):
                pass

        for status, returncode in (("cleanup_failed", 3), ("interrupted", 130)):
            context = SimpleNamespace(
                scenario=SimpleNamespace(steps=[object()]),
                metadata={"snapshots": [], "phases": []},
                evaluator=SimpleNamespace(collect_snapshot=lambda label: {}),
                phase_results=[],
            )
            result = ChaosPhase(
                Executor(status), None, Metadata(), lambda _: None
            ).execute(context)
            self.assertEqual(result.returncode, returncode)

    def test_interrupt_cleans_before_returning(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            executor, _, cleaner = self.make_executor(root)
            context = ChaosExecutionContext(
                ArtifactLayout(root / "output"),
                lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()),
                lambda _: None,
                lambda result: None,
            )
            result = executor.execute(
                ScenarioStep(1, "multi", ("a", "b"), 30), context
            )
        self.assertEqual(result["status"], "interrupted")
        self.assertEqual(cleaner.calls[-2:], [("cleanup", "b"), ("cleanup", "a")])


class ScheduleClientTests(unittest.TestCase):
    def test_delete_all_experiments_covers_schedules_and_children(self):
        class Runner:
            def __init__(self):
                self.commands = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                return CommandResult(tuple(command), 0)

        runner = Runner()
        results = ChaosScheduleClient(runner, Path(".")).delete_all_experiments()

        self.assertEqual(
            set(results),
            set(ChaosScheduleClient.EXPERIMENT_RESOURCES),
        )
        self.assertIn("schedules.chaos-mesh.org", results)
        self.assertIn("physicalmachinechaos.chaos-mesh.org", results)
        self.assertNotIn("physicalmachines.chaos-mesh.org", results)
        for command in runner.commands:
            self.assertIn("--all", command)
            self.assertIn("--all-namespaces", command)
            self.assertIn("--wait=true", command)

    def test_delete_uses_foreground_cascading_and_get_checks_absence(self):
        class Runner:
            def __init__(self):
                self.commands = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                return CommandResult(tuple(command), 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chaos = root / "chaos"
            chaos.mkdir()
            path = write_schedule(chaos, "a")
            schedule = ScheduleLoader().load(path)
            runner = Runner()
            client = ChaosScheduleClient(runner, root)
            client.delete(schedule)
            client.get(schedule)
        self.assertIn("--cascade=foreground", runner.commands[0])
        self.assertIn("--wait=true", runner.commands[0])
        self.assertEqual(runner.commands[1][1:3], ["get", "schedule"])

    def test_recovery_releases_only_confirmed_destroyed_records_finalizer(self):
        class Runner:
            def __init__(self):
                self.commands = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                if command[1] == "get":
                    return CommandResult(
                        tuple(command),
                        0,
                        stdout=json.dumps(
                            {
                                "items": [
                                    {
                                        "kind": "PhysicalMachineChaos",
                                        "metadata": {
                                            "name": "stale-child",
                                            "namespace": "chaos-mesh",
                                            "deletionTimestamp": "2026-08-07T00:00:00Z",
                                            "finalizers": ["chaos-mesh/records"],
                                        },
                                        "status": {
                                            "experiment": {
                                                "message": "can not recover destroyed experiment"
                                            }
                                        },
                                    },
                                    {
                                        "kind": "PhysicalMachineChaos",
                                        "metadata": {
                                            "name": "active-child",
                                            "namespace": "chaos-mesh",
                                            "finalizers": ["chaos-mesh/records"],
                                        },
                                        "status": {
                                            "experiment": {
                                                "message": "can not recover destroyed experiment"
                                            }
                                        },
                                    },
                                    {
                                        "kind": "PhysicalMachineChaos",
                                        "metadata": {
                                            "name": "other-finalizer",
                                            "namespace": "chaos-mesh",
                                            "deletionTimestamp": "2026-08-07T00:00:00Z",
                                            "finalizers": [
                                                "chaos-mesh/records",
                                                "example.com/protect",
                                            ],
                                        },
                                        "status": {
                                            "experiment": {
                                                "message": "can not recover destroyed experiment"
                                            }
                                        },
                                    },
                                ]
                            }
                        ),
                    )
                return CommandResult(tuple(command), 0)

        runner = Runner()
        results = ChaosScheduleClient(
            runner,
            Path("."),
        ).recover_destroyed_experiment_finalizers()

        patches = [command for command in runner.commands if command[1] == "patch"]
        self.assertEqual(len(patches), 1)
        self.assertIn("stale-child", patches[0])
        self.assertNotIn("active-child", patches[0])
        self.assertIn("chaos-mesh/PhysicalMachineChaos/stale-child", results)

    def test_cleaner_recovers_destroyed_child_then_retries_schedule_delete(self):
        class Client:
            def __init__(self):
                self.deletes = 0

            def delete(self, schedule):
                self.deletes += 1
                return CommandResult(
                    ("kubectl", "delete"),
                    1 if self.deletes == 1 else 0,
                )

            def recover_destroyed_experiment_finalizers(self):
                return {
                    "scan": CommandResult(("kubectl", "get"), 0),
                    "chaos-mesh/PhysicalMachineChaos/stale": CommandResult(
                        ("kubectl", "patch"),
                        0,
                    ),
                }

            def get(self, schedule):
                return CommandResult(("kubectl", "get"), 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            client = Client()
            schedule = ScheduleLoader().load(write_schedule(root, "a"))
            result = ScheduleCleaner(
                client,
                CommandLogger(),
            ).clean(schedule, root / "logs", "cleanup")

        self.assertEqual(client.deletes, 2)
        self.assertEqual(result["returncode"], 0)
        self.assertIsNotNone(result["delete_retry"])
        self.assertIn(
            "chaos-mesh/PhysicalMachineChaos/stale",
            result["finalizer_recovery"],
        )

    def test_apply_uses_archived_manifest_when_supplied(self):
        class Runner:
            def __init__(self):
                self.command = None

            def run(self, command, **kwargs):
                self.command = command
                return CommandResult(tuple(command), 0)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = write_schedule(root, "a")
            archived = root / "archived.yaml"
            archived.write_text(source.read_text())
            schedule = ScheduleLoader().load(source)
            runner = Runner()
            ChaosScheduleClient(
                runner,
                root,
                manifest_paths={"a": archived},
            ).apply(schedule)
        self.assertEqual(runner.command[-1], str(archived))

    def test_cleaner_polls_until_schedule_is_absent(self):
        class Client:
            def __init__(self):
                self.gets = 0

            def delete(self, schedule):
                return CommandResult(("kubectl", "delete"), 0)

            def get(self, schedule):
                self.gets += 1
                return CommandResult(
                    ("kubectl", "get"),
                    0,
                    stdout="schedule/a" if self.gets == 1 else "",
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schedule = ScheduleLoader().load(write_schedule(root, "a"))
            sleeps = []
            cleaner = ScheduleCleaner(
                Client(),
                CommandLogger(),
                monotonic=lambda: 0,
                sleep=sleeps.append,
            )
            result = cleaner.clean(schedule, root / "logs", "cleanup")
        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["absent"])
        self.assertEqual(sleeps, [5])

    def test_physical_machine_cleaner_targets_inventory_hosts(self):
        class Runner:
            def __init__(self):
                self.commands = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                return CommandResult(tuple(command), 0, stdout="clean")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "inventory.ini"
            inventory.write_text(
                "[service_nodes]\n"
                "worker-node-1 ansible_host=192.0.2.1\n"
                "worker-node-2 ansible_host=192.0.2.2\n"
            )
            runner = Runner()
            cleaner = PhysicalMachineStateCleaner(
                runner,
                root,
                CommandLogger(),
                inventory_path=inventory,
                ssh_identity_file=Path("/run/ssh/id_ed25519"),
                ssh_known_hosts_file=Path("/run/ssh/known_hosts"),
            )
            result = cleaner.clean_all(root / "logs")

        self.assertEqual(result["returncode"], 0)
        self.assertEqual(set(result["nodes"]), {"worker-node-1", "worker-node-2"})
        self.assertEqual(len(runner.commands), 2)
        self.assertIn("chaos-cleaner@192.0.2.1", runner.commands[0])
        self.assertIn("StrictHostKeyChecking=yes", runner.commands[0])
        self.assertIn("/run/ssh/id_ed25519", runner.commands[0])
        self.assertIn(
            "UserKnownHostsFile=/run/ssh/known_hosts",
            runner.commands[0],
        )
        self.assertIn("sudo -n", runner.commands[0][-1])
        self.assertIn(
            "/usr/local/sbin/evaluation-clean-host-chaos",
            runner.commands[0][-1],
        )

    def test_schedule_cleaner_fails_when_host_state_is_not_clean(self):
        class Client:
            def delete(self, schedule):
                return CommandResult(("kubectl", "delete"), 0)

            def get(self, schedule):
                return CommandResult(("kubectl", "get"), 0)

        class HostCleaner:
            def clean_schedule(self, schedule, output_dir, prefix):
                return {"required": True, "returncode": 1, "nodes": {}}

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schedule = ScheduleLoader().load(write_schedule(root, "a"))
            result = ScheduleCleaner(
                Client(),
                CommandLogger(),
                HostCleaner(),
            ).clean(schedule, root / "logs", "cleanup")

        self.assertTrue(result["absent"])
        self.assertEqual(result["returncode"], 1)
        self.assertEqual(result["physical_machine"]["returncode"], 1)

if __name__ == "__main__":
    unittest.main()
