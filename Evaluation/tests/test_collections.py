import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from testbed.applications import ApplicationCatalog
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
from testbed.domain.placement import APPLICATION_DEPLOYMENTS
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
    def test_primary_scenario_collections_and_chaos_catalog_are_valid(self):
        root = Path(__file__).resolve().parents[1]
        catalog = ChaosCatalog(root / "collections" / "chaos")
        boutique_placements = PlacementCatalog(
            root / "applications" / "online-boutique" / "kustomize" / "overlays"
        )
        teastore_placements = PlacementCatalog(
            root / "applications" / "teastore" / "kustomize" / "overlays"
        )
        boutique_scenarios = [
            ScenarioLoader(root, catalog, boutique_placements).load(path)
            for path in sorted(
                (root / "collections" / "online-boutique-scenario").glob("*.json")
            )
        ]
        teastore_scenarios = [
            ScenarioLoader(root, catalog, teastore_placements).load(path)
            for path in sorted(
                (root / "collections" / "teastore-scenario").glob("*.json")
            )
        ]
        scenarios = boutique_scenarios + teastore_scenarios
        self.assertEqual(len(catalog.schedules), 39)
        self.assertEqual(len(boutique_scenarios), 23)
        self.assertEqual(len(teastore_scenarios), 23)
        self.assertEqual(
            len({scenario.name for scenario in scenarios}),
            len(scenarios),
        )
        self.assertEqual(
            boutique_placements.references,
            ("canonical-six-node", "cpu-constrained-six-node"),
        )
        self.assertEqual(
            teastore_placements.references,
            ("canonical-six-node", "cpu-constrained-six-node"),
        )
        boutique_placement = PlacementRenderer(CommandRunner(), root).render(
            "canonical-six-node",
            boutique_placements.resolve("canonical-six-node"),
        )
        teastore_profile = ApplicationCatalog(
            root / "applications", root.parent
        ).resolve("teastore")
        teastore_placement = PlacementRenderer(
            CommandRunner(),
            root,
            application_profile=teastore_profile,
        ).render(
            "canonical-six-node",
            teastore_placements.resolve("canonical-six-node"),
        )
        boutique_pod_schedules = tuple(
            schedule
            for schedule in catalog.schedules
            if schedule.child_type != "PhysicalMachineChaos"
            and schedule.manifest["spec"][schedule.child_key]["selector"]["namespaces"]
            == ["online-boutique"]
        )
        teastore_pod_schedules = tuple(
            schedule
            for schedule in catalog.schedules
            if schedule.child_type != "PhysicalMachineChaos"
            and schedule.manifest["spec"][schedule.child_key]["selector"]["namespaces"]
            == ["teastore"]
        )
        validate_pod_chaos_selectors(boutique_placement, boutique_pod_schedules)
        validate_pod_chaos_selectors(teastore_placement, teastore_pod_schedules)
        referenced = {
            reference
            for scenario in boutique_scenarios
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
                "node-cpu-worker-2",
                "node-memory-worker-3",
                "single-cartservice-cpu",
                "single-checkoutservice-cpu",
                "single-recommendationservice-cpu",
                "single-productcatalogservice-cpu",
                "single-paymentservice-cpu",
                "single-adservice-memory",
                "single-checkoutservice-capacity-loss",
                "single-productcatalogservice-bandwidth",
                "single-redis-cart-memory",
                "single-currencyservice-memory",
                "single-shippingservice-bandwidth",
                "single-paymentservice-capacity-loss",
                "single-emailservice-cpu",
            },
        )
        teastore_referenced = {
            reference
            for scenario in teastore_scenarios
            for step in scenario.steps
            for reference in step.chaos
        }
        self.assertEqual(
            teastore_referenced,
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
                "node-cpu-worker-2",
                "node-memory-worker-3",
                "teastore-auth-cpu",
                "teastore-persistence-cpu",
                "teastore-recommender-cpu",
                "teastore-image-cpu",
                "teastore-registry-cpu",
                "teastore-image-memory",
                "teastore-persistence-capacity-loss",
                "teastore-image-bandwidth",
                "teastore-db-memory",
                "teastore-auth-memory",
                "teastore-recommender-bandwidth",
                "teastore-registry-capacity-loss",
                "teastore-webui-cpu",
            },
        )
        self.assertNotIn("node-delay-worker-4", catalog_refs)
        self.assertNotIn("node-delay-peers-to-worker-4", catalog_refs)
        for schedule in catalog.schedules:
            child = schedule.manifest["spec"][schedule.child_key]
            if "cpu" in schedule.reference:
                self.assertEqual(schedule.interval_seconds, 30)
                self.assertEqual(schedule.child_duration_seconds, 25)
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
                expected_mode = (
                    "one"
                    if schedule.reference
                    in {
                        "single-checkoutservice-capacity-loss",
                        "single-paymentservice-capacity-loss",
                        "teastore-persistence-capacity-loss",
                        "teastore-registry-capacity-loss",
                    }
                    else "all"
                )
                self.assertEqual(child["mode"], expected_mode)
                expected_namespace = (
                    "teastore"
                    if schedule.reference.startswith("teastore-")
                    else "online-boutique"
                )
                self.assertEqual(selector["namespaces"], [expected_namespace])
                self.assertNotIn("nodes", selector)
                expressions = selector["expressionSelectors"]
                self.assertEqual(expressions[0]["key"], "app")
                self.assertEqual(expressions[0]["operator"], "In")
                self.assertTrue(
                    schedule.reference.startswith("single-")
                    or schedule.reference.startswith("teastore-")
                )
                self.assertEqual(len(expressions[0]["values"]), 1)
                self.assertNotIn("frontend", expressions[0]["values"])
        schedules_by_reference = {
            schedule.reference: schedule for schedule in catalog.schedules
        }
        expected_new_faults = {
            "node-cpu-worker-2": ("PhysicalMachineChaos", "stress-cpu"),
            "node-memory-worker-3": ("PhysicalMachineChaos", "stress-mem"),
            "single-adservice-memory": ("StressChaos", None),
            "single-checkoutservice-capacity-loss": ("PodChaos", "pod-failure"),
            "single-productcatalogservice-bandwidth": (
                "NetworkChaos",
                "bandwidth",
            ),
            "single-redis-cart-memory": ("StressChaos", None),
            "single-currencyservice-memory": ("StressChaos", None),
            "single-shippingservice-bandwidth": ("NetworkChaos", "bandwidth"),
            "single-paymentservice-capacity-loss": ("PodChaos", "pod-failure"),
            "single-emailservice-cpu": ("StressChaos", None),
            "teastore-auth-memory": ("StressChaos", None),
            "teastore-db-memory": ("StressChaos", None),
            "teastore-image-memory": ("StressChaos", None),
            "teastore-persistence-capacity-loss": ("PodChaos", "pod-failure"),
            "teastore-registry-capacity-loss": ("PodChaos", "pod-failure"),
            "teastore-image-bandwidth": ("NetworkChaos", "bandwidth"),
            "teastore-recommender-bandwidth": ("NetworkChaos", "bandwidth"),
        }
        for reference, (child_type, action) in expected_new_faults.items():
            with self.subTest(reference=reference):
                schedule = schedules_by_reference[reference]
                self.assertEqual(schedule.child_type, child_type)
                self.assertEqual(schedule.action, action)
        node_memory = schedules_by_reference["node-memory-worker-3"].manifest[
            "spec"
        ]["physicalmachineChaos"]
        self.assertEqual(node_memory["stress-mem"], {"size": "75%"})
        checkout_capacity = schedules_by_reference[
            "single-checkoutservice-capacity-loss"
        ].manifest["spec"]["podChaos"]
        self.assertEqual(checkout_capacity["mode"], "one")
        catalog_bandwidth = schedules_by_reference[
            "single-productcatalogservice-bandwidth"
        ].manifest["spec"]["networkChaos"]
        self.assertEqual(
            catalog_bandwidth["bandwidth"],
            {"rate": "1mbps", "limit": 2097152, "buffer": 10000},
        )
        redis_memory = schedules_by_reference[
            "single-redis-cart-memory"
        ].manifest["spec"]["stressChaos"]
        self.assertEqual(
            redis_memory["stressors"]["memory"],
            {"workers": 1, "size": "400MB"},
        )
        payment_capacity = schedules_by_reference[
            "single-paymentservice-capacity-loss"
        ].manifest["spec"]["podChaos"]
        self.assertEqual(payment_capacity["mode"], "one")
        shipping_bandwidth = schedules_by_reference[
            "single-shippingservice-bandwidth"
        ].manifest["spec"]["networkChaos"]
        self.assertEqual(
            shipping_bandwidth["bandwidth"],
            {"rate": "1mbps", "limit": 2097152, "buffer": 10000},
        )
        for scenario in scenarios:
            constrained_scenarios = {
                "real-pod-emailservice-cpu-headroom-all-one-hour",
                "real-pod-checkoutservice-cpu-headroom-all-one-hour",
                "real-pod-productcatalogservice-cpu-headroom-all-one-hour",
                "teastore-pod-webui-cpu-headroom-all-one-hour",
                "teastore-pod-persistence-cpu-headroom-all-one-hour",
                "teastore-pod-image-cpu-headroom-all-one-hour",
            }
            expected_placement = (
                "cpu-constrained-six-node"
                if scenario.name in constrained_scenarios
                else "canonical-six-node"
            )
            self.assertEqual(scenario.placement, expected_placement)
            self.assertEqual(len(scenario.steps), 2)
            chaos_step, recovery_step = scenario.steps
            self.assertFalse(chaos_step.idle)
            self.assertEqual(chaos_step.duration, 3600)
            self.assertTrue(recovery_step.idle)
            self.assertEqual(recovery_step.duration, 600)
            self.assertTrue(recovery_step.name.endswith("recovery") or recovery_step.name == "02-recovery")
            if scenario.name.startswith("teastore-"):
                self.assertEqual(scenario.application, "teastore")
            else:
                self.assertEqual(scenario.application, "online-boutique")

    def test_long_scenario_collection_is_a_one_day_multi_fault(self):
        root = Path(__file__).resolve().parents[1]
        catalog = ChaosCatalog(root / "collections" / "chaos")
        placements = PlacementCatalog(
            root / "applications" / "online-boutique" / "kustomize" / "overlays"
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
            root / "applications" / "online-boutique" / "kustomize" / "overlays"
        )
        profile = PlacementRenderer(CommandRunner(), root).render(
            "canonical-six-node",
            catalog.resolve("canonical-six-node"),
        )
        self.assertEqual(
            profile.allowed_nodes,
            {
                deployment: tuple(f"worker-node-{index}" for index in range(1, 7))
                for deployment in APPLICATION_DEPLOYMENTS
            },
        )
        documents = list(yaml.safe_load_all(profile.rendered_manifest))
        deployments = {
            document["metadata"]["name"]: document
            for document in documents
            if document and document.get("kind") == "Deployment"
        }
        hpas = {
            document["metadata"]["name"]: document
            for document in documents
            if document and document.get("kind") == "HorizontalPodAutoscaler"
        }
        for name, deployment in deployments.items():
            expected_replicas = 6 if name == "frontend" else 2
            self.assertEqual(deployment["spec"]["replicas"], expected_replicas)
            pod_spec = deployment["spec"]["template"]["spec"]
            self.assertNotIn("affinity", pod_spec)
            self.assertEqual(
                pod_spec["topologySpreadConstraints"],
                [
                    {
                        "maxSkew": 1,
                        "topologyKey": "kubernetes.io/hostname",
                        "whenUnsatisfiable": "ScheduleAnyway",
                        "labelSelector": {"matchLabels": {"app": name}},
                    }
                ],
            )
            hpa = hpas[f"{name}-hpa"]
            self.assertEqual(hpa["spec"]["minReplicas"], expected_replicas)
            self.assertEqual(hpa["spec"]["maxReplicas"], 30)

    def test_cpu_constrained_placement_preserves_topology_and_removes_headroom(self):
        root = Path(__file__).resolve().parents[1]
        catalog = PlacementCatalog(
            root / "applications" / "online-boutique" / "kustomize" / "overlays"
        )
        profile = PlacementRenderer(CommandRunner(), root).render(
            "cpu-constrained-six-node",
            catalog.resolve("cpu-constrained-six-node"),
        )
        self.assertEqual(
            profile.allowed_nodes,
            {
                deployment: tuple(f"worker-node-{index}" for index in range(1, 7))
                for deployment in APPLICATION_DEPLOYMENTS
            },
        )
        documents = list(yaml.safe_load_all(profile.rendered_manifest))
        deployments = {
            document["metadata"]["name"]: document
            for document in documents
            if document and document.get("kind") == "Deployment"
        }
        hpas = {
            document["metadata"]["name"]: document
            for document in documents
            if document and document.get("kind") == "HorizontalPodAutoscaler"
        }
        self.assertEqual(set(deployments), set(APPLICATION_DEPLOYMENTS))
        for name, deployment in deployments.items():
            container = deployment["spec"]["template"]["spec"]["containers"][0]
            resources = container["resources"]
            self.assertEqual(
                resources["limits"]["cpu"],
                resources["requests"]["cpu"],
                name,
            )
            pod_spec = deployment["spec"]["template"]["spec"]
            self.assertEqual(pod_spec["nodeSelector"], {"role": "services"})
            self.assertEqual(
                pod_spec["topologySpreadConstraints"][0]["topologyKey"],
                "kubernetes.io/hostname",
            )
            hpa = hpas[f"{name}-hpa"]
            self.assertEqual(hpa["spec"]["maxReplicas"], 30)
            self.assertEqual(
                hpa["spec"]["metrics"][0]["resource"]["target"][
                    "averageUtilization"
                ],
                70,
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
                self.timeouts = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                self.timeouts.append(kwargs.get("timeout"))
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
            self.assertIn("--timeout=240s", command)
        self.assertEqual(set(runner.timeouts), {300})

    def test_delete_uses_background_cascading_and_get_checks_absence(self):
        class Runner:
            def __init__(self):
                self.commands = []
                self.timeouts = []

            def run(self, command, **kwargs):
                self.commands.append(command)
                self.timeouts.append(kwargs.get("timeout"))
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
            client.get_children(schedule)
        self.assertIn("--cascade=background", runner.commands[0])
        self.assertIn("--wait=true", runner.commands[0])
        self.assertEqual(runner.timeouts[0], 240)
        self.assertEqual(runner.commands[1][1:3], ["get", "schedule"])
        self.assertEqual(runner.timeouts[1], 30)
        self.assertEqual(runner.commands[2][1:3], ["get", schedule.child_type])
        self.assertIn("--selector=managed-by=a", runner.commands[2])
        self.assertEqual(runner.timeouts[2], 30)

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

            def get_children(self, schedule):
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

            def get_children(self, schedule):
                return CommandResult(("kubectl", "get"), 0)

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
        self.assertTrue(result["schedule_absent"])
        self.assertTrue(result["children_absent"])
        self.assertEqual(sleeps, [5])

    def test_cleaner_waits_for_managed_children_after_schedule_is_absent(self):
        class Client:
            def __init__(self):
                self.child_gets = 0

            def delete(self, schedule):
                return CommandResult(("kubectl", "delete"), 0)

            def get(self, schedule):
                return CommandResult(("kubectl", "get"), 0)

            def get_children(self, schedule):
                self.child_gets += 1
                return CommandResult(
                    ("kubectl", "get"),
                    0,
                    stdout="stresschaos/a-x" if self.child_gets == 1 else "",
                )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            schedule = ScheduleLoader().load(write_schedule(root, "a"))
            sleeps = []
            result = ScheduleCleaner(
                Client(),
                CommandLogger(),
                monotonic=lambda: 0,
                sleep=sleeps.append,
            ).clean(schedule, root / "logs", "cleanup")

        self.assertEqual(result["returncode"], 0)
        self.assertTrue(result["absent"])
        self.assertEqual(len(result["child_verification"]), 2)
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

            def get_children(self, schedule):
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
