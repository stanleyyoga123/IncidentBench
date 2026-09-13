import unittest

from fastapi.testclient import TestClient

from adaptation import DetectorProfileRegistry
from api import create_app


class DetectorProfileAPITest(unittest.TestCase):
    def setUp(self):
        self.registry = DetectorProfileRegistry()
        self.client = TestClient(
            create_app(
                registry=self.registry,
                start_detector=False,
                profile_api_token="test-token",
            )
        )
        self.auth = {"X-Detector-Profile-Token": "test-token"}

    def test_lists_and_resolves_profiles_without_authentication(self):
        profiles = self.client.get("/api/v1/detector/profiles")
        resolved = self.client.get(
            "/api/v1/detector/profiles/resolve",
            params={
                "method": "threshold",
                "resource": "deployments",
                "name": "checkout",
                "metric": "http_5xx_rate",
            },
        )

        self.assertEqual(200, profiles.status_code)
        self.assertEqual("in_memory", profiles.json()["persistence"])
        self.assertGreater(profiles.json()["count"], 0)
        self.assertEqual(200, resolved.status_code)
        self.assertEqual(0.05, resolved.json()["parameters"]["threshold"])

    def test_create_update_history_and_reset_scoped_profile(self):
        created = self.client.post(
            "/api/v1/detector/profiles",
            headers=self.auth,
            json={
                "method": "threshold",
                "resource": "deployments",
                "name": "checkout",
                "metric": "http_5xx_rate",
                "parameters": {"threshold": 0.08},
                "reason": "evaluation marked recent alerts false positive",
            },
        )
        profile_id = created.json()["id"]
        updated = self.client.patch(
            f"/api/v1/detector/profiles/{profile_id}",
            headers=self.auth,
            json={
                "parameters": {"consecutive_anomalies_required": 4},
                "reason": "require longer persistence",
                "expected_version": 1,
            },
        )
        history = self.client.get(
            f"/api/v1/detector/profiles/{profile_id}/history"
        )
        reset = self.client.post(
            f"/api/v1/detector/profiles/{profile_id}/reset",
            headers=self.auth,
            json={"reason": "rollback experiment", "expected_version": 2},
        )

        self.assertEqual(201, created.status_code)
        self.assertEqual(200, updated.status_code)
        self.assertEqual(2, updated.json()["version"])
        self.assertEqual(200, history.status_code)
        self.assertEqual(2, len(history.json()["revisions"]))
        self.assertEqual(200, reset.status_code)
        self.assertFalse(reset.json()["active"])

    def test_mutations_require_token(self):
        response = self.client.post(
            "/api/v1/detector/profiles",
            json={
                "method": "threshold",
                "resource": "deployments",
                "name": "checkout",
                "metric": "http_5xx_rate",
                "parameters": {"threshold": 0.08},
                "reason": "unauthorized attempt",
            },
        )

        self.assertEqual(401, response.status_code)

    def test_mutations_are_disabled_without_configured_token(self):
        client = TestClient(
            create_app(
                registry=DetectorProfileRegistry(),
                start_detector=False,
                profile_api_token="",
            )
        )
        response = client.post(
            "/api/v1/detector/profiles",
            headers=self.auth,
            json={
                "method": "threshold",
                "resource": "deployments",
                "name": "checkout",
                "metric": "http_5xx_rate",
                "parameters": {"threshold": 0.08},
                "reason": "disabled mutation",
            },
        )

        self.assertEqual(503, response.status_code)

    def test_openapi_exposes_stable_agent_tool_names(self):
        operations = {
            operation["operationId"]
            for path in self.client.get("/openapi.json").json()["paths"].values()
            for operation in path.values()
        }

        self.assertEqual(
            {
                "get_anomaly_detector_health",
                "list_detector_profiles",
                "resolve_detector_profile",
                "get_detector_profile",
                "get_detector_profile_history",
                "create_detector_profile_override",
                "update_detector_profile",
                "reset_detector_profile",
            },
            operations,
        )


if __name__ == "__main__":
    unittest.main()
