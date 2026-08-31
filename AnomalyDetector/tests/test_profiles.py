import unittest

from adaptation import (
    DetectorProfileRegistry,
    ProfileConflictError,
    ProfileValidationError,
)


class DetectorProfileRegistryTest(unittest.TestCase):
    def setUp(self):
        self.registry = DetectorProfileRegistry()

    def test_scoped_override_wins_and_reset_falls_back_to_default(self):
        default = self.registry.resolve(
            "threshold",
            "deployments",
            "checkout",
            "http_5xx_rate",
        )
        override = self.registry.create_override(
            method="threshold",
            resource="deployments",
            name="checkout",
            metric="http_5xx_rate",
            changes={"threshold": 0.08},
            reason="reduce false positives for checkout",
        )

        self.assertEqual(
            override.id,
            self.registry.resolve(
                "threshold",
                "deployments",
                "checkout",
                "http_5xx_rate",
            ).id,
        )

        reset = self.registry.reset(
            override.id,
            reason="return to inherited profile",
            expected_version=1,
        )

        self.assertFalse(reset.active)
        self.assertEqual(
            default.id,
            self.registry.resolve(
                "threshold",
                "deployments",
                "checkout",
                "http_5xx_rate",
            ).id,
        )

    def test_update_is_versioned_and_requires_expected_version_when_supplied(self):
        profile = self.registry.resolve(
            "z_score",
            "deployments",
            "checkout",
            "response_time_p95_seconds",
        )
        updated = self.registry.update(
            profile.id,
            changes={"threshold": 3.5},
            reason="validated evaluation result",
            expected_version=1,
        )

        self.assertEqual(2, updated.version)
        self.assertEqual(3.5, updated.parameters["threshold"])
        self.assertEqual(2, len(self.registry.history(profile.id)))
        with self.assertRaises(ProfileConflictError):
            self.registry.update(
                profile.id,
                changes={"threshold": 4.0},
                reason="stale update",
                expected_version=1,
            )

    def test_namespace_scoped_override_does_not_cross_applications(self):
        default = self.registry.resolve(
            "threshold", "deployments", "frontend", "http_5xx_rate",
            "other-app",
        )
        override = self.registry.create_override(
            method="threshold",
            namespace="online-boutique",
            resource="deployments",
            name="frontend",
            metric="http_5xx_rate",
            changes={"threshold": 0.08},
            reason="workload-specific calibration",
        )

        self.assertEqual(
            override.id,
            self.registry.resolve(
                "threshold", "deployments", "frontend", "http_5xx_rate",
                "online-boutique",
            ).id,
        )
        self.assertEqual(
            default.id,
            self.registry.resolve(
                "threshold", "deployments", "frontend", "http_5xx_rate",
                "other-app",
            ).id,
        )

    def test_rejects_unsafe_or_immutable_changes(self):
        cpu_profile = self.registry.resolve(
            "threshold",
            "nodes",
            "worker-1",
            "node_cpu_utilization_percent",
        )
        with self.assertRaises(ProfileValidationError):
            self.registry.update(
                cpu_profile.id,
                changes={"threshold": 40.0},
                reason="unsafe threshold",
            )

        instance_profile = self.registry.resolve(
            "threshold",
            "deployments",
            "checkout",
            "app_instance_count",
        )
        with self.assertRaises(ProfileValidationError):
            self.registry.update(
                instance_profile.id,
                changes={"threshold": 0.0},
                reason="could suppress outages",
            )


if __name__ == "__main__":
    unittest.main()
