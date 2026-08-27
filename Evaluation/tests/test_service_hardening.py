import unittest
from pathlib import Path

import yaml

from testbed.domain.placement import APPLICATION_DEPLOYMENTS


def cpu_millicores(value: str) -> int:
    text = str(value)
    if text.endswith("m"):
        return int(text[:-1])
    return int(float(text) * 1000)


def memory_mebibytes(value: str) -> int:
    text = str(value)
    if text.endswith("Mi"):
        return int(text[:-2])
    if text.endswith("Gi"):
        return int(text[:-2]) * 1024
    raise AssertionError(f"Unsupported memory quantity in test: {value}")


class ServiceHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.kustomize_root = (
            cls.root.parent
            / "Infrastructure"
            / "kubernetes"
            / "online-boutique"
            / "kustomize"
        )
        base = cls.kustomize_root / "base"
        kustomization = yaml.safe_load((base / "kustomization.yaml").read_text())
        cls.deployments = {}
        for resource in kustomization["resources"]:
            for document in yaml.safe_load_all((base / resource).read_text()):
                if document and document.get("kind") == "Deployment":
                    cls.deployments[document["metadata"]["name"]] = document

    def test_all_application_deployments_have_resilient_health_probes(self):
        self.assertEqual(set(self.deployments), set(APPLICATION_DEPLOYMENTS))
        for name, deployment in self.deployments.items():
            with self.subTest(deployment=name):
                container = deployment["spec"]["template"]["spec"]["containers"][0]
                startup = container["startupProbe"]
                readiness = container["readinessProbe"]
                liveness = container["livenessProbe"]

                self.assertGreaterEqual(startup["timeoutSeconds"], 3)
                self.assertGreaterEqual(startup["failureThreshold"], 24)
                self.assertLessEqual(startup["periodSeconds"], 5)
                self.assertGreaterEqual(readiness["timeoutSeconds"], 3)
                self.assertGreaterEqual(readiness["failureThreshold"], 3)
                self.assertGreaterEqual(liveness["timeoutSeconds"], 5)
                self.assertGreaterEqual(liveness["failureThreshold"], 6)
                self.assertGreaterEqual(liveness["periodSeconds"], 10)

    def test_all_application_deployments_have_resource_headroom(self):
        for name, deployment in self.deployments.items():
            with self.subTest(deployment=name):
                container = deployment["spec"]["template"]["spec"]["containers"][0]
                resources = container["resources"]
                cpu_request = cpu_millicores(resources["requests"]["cpu"])
                cpu_limit = cpu_millicores(resources["limits"]["cpu"])
                memory_request = memory_mebibytes(
                    resources["requests"]["memory"]
                )
                memory_limit = memory_mebibytes(resources["limits"]["memory"])

                self.assertGreaterEqual(memory_limit, 512)
                self.assertGreaterEqual(memory_limit, memory_request)
                if name == "redis-cart":
                    self.assertGreaterEqual(cpu_limit, cpu_request * 2)
                else:
                    self.assertGreaterEqual(cpu_request, 250)
                    self.assertGreaterEqual(cpu_limit, 500)

    def test_recommendationservice_uses_canonical_two_replica_floor(self):
        deployment = self.deployments["recommendationservice"]
        container = deployment["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(deployment["spec"]["replicas"], 2)
        self.assertEqual(
            container["resources"],
            {
                "requests": {"cpu": "300m", "memory": "384Mi"},
                "limits": {"cpu": "500m", "memory": "768Mi"},
            },
        )

        hpa_path = self.kustomize_root / "overlays" / "canonical-six-node" / "hpa.yaml"
        hpas = {
            document["metadata"]["name"]: document
            for document in yaml.safe_load_all(hpa_path.read_text())
            if document
        }
        self.assertEqual(
            hpas["recommendationservice-hpa"]["spec"]["minReplicas"], 2
        )
        self.assertEqual(hpas["frontend-hpa"]["spec"]["minReplicas"], 6)


if __name__ == "__main__":
    unittest.main()
