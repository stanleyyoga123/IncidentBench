import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml

from testbed.artifacts import ArtifactLayout, InputArtifactArchiver
from testbed.artifacts.metadata_factory import MetadataFactory
from testbed.command import CommandLogger
from testbed.domain import CommandResult
from testbed.domain.placement import APPLICATION_DEPLOYMENTS, PlacementProfile
from testbed.domain.scenario import Scenario
from testbed.kubernetes.application_deployments import ApplicationDeploymentController
from testbed.orchestration.application_reset_phase import ApplicationResetPhase
from testbed.placement import PlacementRenderer


def deployment(name: str) -> dict:
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name},
        "spec": {
            "template": {
                "spec": {
                    "nodeSelector": {"role": "services"},
                    "topologySpreadConstraints": [
                        {
                            "maxSkew": 1,
                            "topologyKey": "kubernetes.io/hostname",
                            "whenUnsatisfiable": "ScheduleAnyway",
                            "labelSelector": {"matchLabels": {"app": name}},
                        }
                    ],
                }
            }
        },
    }


def pod(name: str, node="worker-node-1", ready=True) -> dict:
    return {
        "metadata": {"name": f"{name}-pod", "labels": {"app": name}},
        "spec": {"nodeName": node},
        "status": {
            "phase": "Running" if ready else "Pending",
            "containerStatuses": [{"ready": ready}],
        },
    }


def node(
    name="worker-node-1",
    *,
    ready=True,
    unschedulable=False,
    role="services",
    hostname=None,
    taints=None,
) -> dict:
    return {
        "metadata": {
            "name": name,
            "labels": {
                "role": role,
                "kubernetes.io/hostname": hostname or name,
            },
        },
        "spec": {
            "unschedulable": unschedulable,
            "taints": taints or [],
        },
        "status": {
            "conditions": [
                {"type": "Ready", "status": "True" if ready else "False"}
            ]
        },
    }


def profile(
    source: Path,
    nodes: tuple[str, ...] = ("worker-node-1",),
) -> PlacementProfile:
    rendered = "rendered\n"
    return PlacementProfile(
        reference="test-placement",
        source_dir=source,
        rendered_manifest=rendered,
        rendered_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
        allowed_nodes={name: nodes for name in APPLICATION_DEPLOYMENTS},
        tolerations={name: () for name in APPLICATION_DEPLOYMENTS},
    )


class FakeRunner:
    def __init__(self):
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append((command, kwargs))
        return CommandResult(tuple(command), 0)


class FakeKubectl:
    def __init__(self, responses):
        self.responses = iter(responses)

    def run(self, command):
        value = next(self.responses)
        return CommandResult(("kubectl", *command), *value)

    def rollout_status(self, deployment, namespace):
        return CommandResult(("kubectl", "rollout", "status", deployment), 0)


class PlacementControllerTests(unittest.TestCase):
    def controller(self, root: Path, responses):
        return ApplicationDeploymentController(
            FakeRunner(),
            FakeKubectl(responses),
            ArtifactLayout(root / "artifacts"),
            CommandLogger(),
            root,
        )

    def test_rollout_wait_respects_long_progress_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self.controller(Path(tmp), [(0, json.dumps({"items": [
                {"metadata": {"name": "front-end"}, "spec": {}},
                {"metadata": {"name": "orders"}, "spec": {"progressDeadlineSeconds": 1200}},
            ]}), "")])
            calls = []
            def rollout(deployment, namespace, timeout):
                calls.append((deployment, namespace, timeout))
                return CommandResult(("kubectl", "rollout", "status", deployment), 0)
            controller.kubectl.rollout_status = rollout
            result = controller.wait_for_rollouts("sock-shop")
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(calls, [
                ("deployment.apps/front-end", "sock-shop", "600s"),
                ("deployment.apps/orders", "sock-shop", "1260s"),
            ])

    def test_rollout_wait_rejects_invalid_deployment_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            controller = self.controller(Path(tmp), [(0, "not-json", "")])
            result = controller.wait_for_rollouts("sock-shop")
            self.assertEqual(result["returncode"], 2)

    def test_node_preflight_accepts_healthy_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            controller = self.controller(
                root,
                [(0, json.dumps({"items": [node()]}), "")],
            )
            result = controller.preflight(profile(source))
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["errors"], [])

    def test_node_normalization_uncordons_only_referenced_nodes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            controller = self.controller(root, [(0, "node/worker-node-1", "")])
            result = controller.normalize_nodes(profile(source))
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(set(result["nodes"]), {"worker-node-1"})
        self.assertEqual(
            result["nodes"]["worker-node-1"]["command"],
            ["kubectl", "uncordon", "worker-node-1"],
        )

    def test_node_preflight_rejects_unusable_node_states(self):
        cases = [
            ([], "does not exist"),
            ([node(ready=False)], "not Ready"),
            ([node(unschedulable=True)], "unschedulable"),
            ([node(role="other")], "role=services"),
            ([node(hostname="other")], "kubernetes.io/hostname"),
            (
                [node(taints=[{"key": "blocked", "effect": "NoSchedule"}])],
                "untolerated blocking taints",
            ),
        ]
        for items, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source"
                source.mkdir()
                controller = self.controller(
                    root,
                    [(0, json.dumps({"items": items}), "")],
                )
                result = controller.preflight(profile(source))
                self.assertNotEqual(result["returncode"], 0)
                self.assertIn(message, " ".join(result["errors"]))


class PlacementManifestValidationTests(unittest.TestCase):
    class Runner:
        def __init__(self, documents):
            self.rendered = yaml.safe_dump_all(documents)

        def run(self, command, **kwargs):
            return CommandResult(tuple(command), 0, stdout=self.rendered)

    def render(self, documents):
        return PlacementRenderer(self.Runner(documents), Path("/repo")).render(
            "profile",
            Path("/repo/services/kustomize/overlays/profile"),
        )

    def test_renderer_requires_the_exact_application_deployment_set(self):
        documents = [deployment(name) for name in APPLICATION_DEPLOYMENTS[:-1]]
        with self.assertRaisesRegex(ValueError, "exactly the application Deployments"):
            self.render(documents)

    def test_renderer_rejects_missing_invalid_and_conflicting_constraints(self):
        def missing_spread(value):
            del value["spec"]["template"]["spec"]["topologySpreadConstraints"]

        def hard_affinity(value):
            value["spec"]["template"]["spec"]["affinity"] = {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": []
                    }
                }
            }

        def conflicting_selector(value):
            value["spec"]["template"]["spec"]["nodeSelector"]["zone"] = "other"

        def hard_spread(value):
            value["spec"]["template"]["spec"]["topologySpreadConstraints"][0][
                "whenUnsatisfiable"
            ] = "DoNotSchedule"

        for mutate, message in (
            (missing_spread, "topology spread constraint"),
            (hard_affinity, "must not contain required node affinity"),
            (conflicting_selector, "conflicting node selectors"),
            (hard_spread, "softly spread"),
        ):
            with self.subTest(message=message):
                documents = [deployment(name) for name in APPLICATION_DEPLOYMENTS]
                mutate(documents[0])
                with self.assertRaisesRegex(ValueError, message):
                    self.render(documents)


class PlacementRuntimeVerificationTests(unittest.TestCase):
    def controller(self, root: Path, responses):
        return ApplicationDeploymentController(
            FakeRunner(),
            FakeKubectl(responses),
            ArtifactLayout(root / "artifacts"),
            CommandLogger(),
            root,
        )

    def test_controller_does_not_own_namespace_restart(self):
        self.assertFalse(hasattr(ApplicationDeploymentController, "restart"))

    def test_live_verification_records_a_stable_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            deployments = [deployment(name) for name in APPLICATION_DEPLOYMENTS]
            pods = [pod(name) for name in APPLICATION_DEPLOYMENTS]
            controller = self.controller(
                root,
                [
                    (0, json.dumps({"items": deployments}), ""),
                    (0, json.dumps({"items": pods}), ""),
                ],
            )
            result = controller.verify_placement(
                profile(source, tuple(f"worker-node-{index}" for index in range(1, 7))),
                "online-boutique",
            )
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["errors"], [])
        self.assertEqual(len(result["observed_placement_fingerprint"]), 64)
        self.assertEqual(
            result["observed_placement"]["frontend"],
            {"worker-node-1": 1},
        )

    def test_live_verification_rejects_pod_and_template_drift(self):
        cases = [
            (
                [deployment(name) for name in APPLICATION_DEPLOYMENTS],
                [
                    pod(name, node="worker-node-7" if name == "frontend" else "worker-node-1")
                    for name in APPLICATION_DEPLOYMENTS
                ],
                "disallowed node",
            ),
            (
                [deployment(name) for name in APPLICATION_DEPLOYMENTS],
                [pod(name, ready=name != "frontend") for name in APPLICATION_DEPLOYMENTS],
                "not Ready",
            ),
            (
                [deployment(name) for name in APPLICATION_DEPLOYMENTS],
                [pod(name) for name in APPLICATION_DEPLOYMENTS if name != "frontend"],
                "no application pods",
            ),
            (
                [
                    {
                        **deployment(name),
                        "spec": {
                            **deployment(name)["spec"],
                            "template": {
                                "spec": {
                                    **deployment(name)["spec"]["template"]["spec"],
                                    "topologySpreadConstraints": [],
                                }
                            },
                        },
                    }
                    if name == "frontend" else deployment(name)
                    for name in APPLICATION_DEPLOYMENTS
                ],
                [pod(name) for name in APPLICATION_DEPLOYMENTS],
                "topology spread constraint",
            ),
        ]
        for deployments, pods, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                source = root / "source"
                source.mkdir()
                controller = self.controller(
                    root,
                    [
                        (0, json.dumps({"items": deployments}), ""),
                        (0, json.dumps({"items": pods}), ""),
                    ],
                )
                result = controller.verify_placement(
                    profile(
                        source,
                        tuple(f"worker-node-{index}" for index in range(1, 7)),
                    ),
                    "online-boutique",
                )
                self.assertNotEqual(result["returncode"], 0)
                self.assertIn(message, " ".join(result["errors"]))


class PlacementOrchestrationTests(unittest.TestCase):
    def test_preflight_failure_prevents_namespace_reset(self):
        class Controller:
            def __init__(self):
                self.calls = []

            def normalize_nodes(self, value):
                self.calls.append("normalize")
                return {"returncode": 0, "nodes": {}}

            def preflight(self, value):
                self.calls.append("preflight")
                return {"returncode": 2, "errors": ["bad node"]}

        class Metadata:
            def write(self, value):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            controller = Controller()
            context = SimpleNamespace(
                config=SimpleNamespace(
                    namespace="online-boutique",
                ),
                metadata={"placement": {}, "commands": {}, "phases": []},
                phase_results=[],
            )
            result = ApplicationResetPhase(
                controller,
                profile(source),
                Metadata(),
                lambda _: None,
            ).execute(context)
        self.assertTrue(result.failed)
        self.assertEqual(controller.calls, ["normalize", "preflight"])

    def test_normalization_failure_prevents_preflight_and_reset(self):
        class Controller:
            def __init__(self):
                self.calls = []

            def normalize_nodes(self, value):
                self.calls.append("normalize")
                return {"returncode": 1, "nodes": {}}

            def preflight(self, value):
                self.calls.append("preflight")
                return {"returncode": 0}

        class Metadata:
            def write(self, value):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            controller = Controller()
            context = SimpleNamespace(
                config=SimpleNamespace(
                    namespace="online-boutique",
                ),
                metadata={"placement": {}, "commands": {}, "phases": []},
                phase_results=[],
            )
            result = ApplicationResetPhase(
                controller,
                profile(source),
                Metadata(),
                lambda _: None,
            ).execute(context)
        self.assertTrue(result.failed)
        self.assertEqual(controller.calls, ["normalize"])

    def test_application_reset_does_not_restart_namespace(self):
        class Controller:
            def __init__(self):
                self.calls = []

            def normalize_nodes(self, value):
                self.calls.append("normalize")
                return {"returncode": 0, "nodes": {}}

            def preflight(self, value):
                self.calls.append("preflight")
                return {"returncode": 0, "errors": []}

            def wait_for_rollouts(self, namespace):
                self.calls.append(("rollout", namespace))
                return {"returncode": 0}

            def verify_placement(self, placement, namespace):
                self.calls.append(("verify", namespace))
                return {
                    "returncode": 0,
                    "observed_placement": {},
                    "observed_placement_fingerprint": "abc",
                    "commands": {},
                }

        class Metadata:
            def write(self, value):
                pass

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            controller = Controller()
            context = SimpleNamespace(
                config=SimpleNamespace(namespace="online-boutique"),
                metadata={"placement": {}, "commands": {}, "phases": []},
                phase_results=[],
            )
            result = ApplicationResetPhase(
                controller,
                profile(source),
                Metadata(),
                lambda _: None,
            ).execute(context)
        self.assertFalse(result.failed)
        self.assertEqual(
            controller.calls,
            [
                "normalize",
                "preflight",
                ("rollout", "online-boutique"),
                ("verify", "online-boutique"),
            ],
        )
        self.assertNotIn("restart", context.metadata["commands"])

    def test_archiver_preserves_profile_source_and_exact_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            (source / "kustomization.yaml").write_text("kind: Kustomization\n")
            placement = profile(source)
            scenario_path = root / "scenario.json"
            scenario_path.write_text("{}")
            layout = ArtifactLayout(root / "output")
            InputArtifactArchiver(layout).archive(
                Scenario("scenario", "test-placement", (), str(scenario_path)),
                (),
                placement,
            )
            self.assertEqual(
                layout.archived_placement_render.read_text(),
                placement.rendered_manifest,
            )
            self.assertTrue(
                (layout.archived_placement_source / "kustomization.yaml").is_file()
            )

    def test_metadata_records_profile_hash_and_artifact_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            placement = profile(source)
            scenario_path = root / "scenario.json"
            scenario_path.write_text("{}")
            scenario = Scenario(
                "scenario",
                placement.reference,
                (),
                str(scenario_path),
            )
            config = SimpleNamespace(
                baseline_seconds=60,
                grace_period=0,
                repo_root=root,
                namespace="online-boutique",
                agent_namespace="agents",
                host="http://frontend",
                agents_enabled=False,
                loadgenerator="constant",
            )
            args = SimpleNamespace(
                scenario=scenario_path,
                postgres_dsn="secret",
            )
            metadata = MetadataFactory.create(
                config,
                scenario,
                args,
                (),
                {},
                placement,
                root / "inputs" / "placement" / "source",
                root / "inputs" / "placement" / "rendered.yaml",
            )
        self.assertEqual(metadata["schema_version"], 2)
        self.assertEqual(metadata["placement"]["reference"], placement.reference)
        self.assertEqual(
            metadata["placement"]["rendered_sha256"],
            placement.rendered_sha256,
        )
        self.assertEqual(metadata["args"]["postgres_dsn"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
