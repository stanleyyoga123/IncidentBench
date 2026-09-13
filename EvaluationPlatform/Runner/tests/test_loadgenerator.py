import importlib
import os
import sys
import types
import unittest
from unittest.mock import patch


class LoadGeneratorSeedTests(unittest.TestCase):
    def import_shape_module(self, module_name, env):
        class LoadTestShape:
            def get_run_time(self):
                return 0

        locust_stub = types.SimpleNamespace(
            LoadTestShape=LoadTestShape,
            FastHttpUser=object,
            TaskSet=object,
            between=lambda *_args: None,
        )
        common_stub = types.SimpleNamespace(WebsiteUser=object)
        with patch.dict(os.environ, env, clear=True), patch.dict(
            sys.modules,
            {
                "locust": locust_stub,
                "testbed.loadgenerator.common": common_stub,
            },
        ):
            module = importlib.import_module(module_name)
            return importlib.reload(module)

    def test_burst_seed_controls_optional_bias(self):
        burst = self.import_shape_module(
            "testbed.loadgenerator.burst",
            {
                "BURST_BASELINE_USERS": "25",
                "BURST_PEAK_USERS": "200",
                "BURST_BASELINE_SECONDS": "120",
                "BURST_PEAK_SECONDS": "60",
                "BURST_BIAS_USERS": "5",
                "BURST_SEED": "7",
                "RUN_TIME_SECONDS": "0",
            },
        )

        burst.BurstLoadShape.baseline_users = 25
        burst.BurstLoadShape.bias_users = 5
        burst.BurstLoadShape.seed = 7
        first = burst.BurstLoadShape()
        second = burst.BurstLoadShape()

        with patch.object(first, "get_run_time", return_value=30):
            first_users, _ = first.tick()
        with patch.object(second, "get_run_time", return_value=30):
            second_users, _ = second.tick()

        self.assertEqual(first_users, second_users)
        self.assertGreaterEqual(first_users, 25)
        self.assertLessEqual(first_users, 30)

    def test_sinus_seed_controls_optional_bias(self):
        sinus = self.import_shape_module(
            "testbed.loadgenerator.sinus",
            {
                "SINUS_MIN_USERS": "20",
                "SINUS_MAX_USERS": "150",
                "SINUS_PERIOD_SECONDS": "300",
                "SINUS_BIAS_USERS": "5",
                "SINUS_SEED": "7",
                "RUN_TIME_SECONDS": "0",
            },
        )

        first = sinus.SinusLoadShape()
        second = sinus.SinusLoadShape()

        with patch.object(first, "get_run_time", return_value=0):
            first_users, _ = first.tick()
        with patch.object(second, "get_run_time", return_value=0):
            second_users, _ = second.tick()

        self.assertEqual(first_users, second_users)
        self.assertGreaterEqual(first_users, 85)
        self.assertLessEqual(first_users, 90)

    def test_default_burst_and_sinus_bias_preserves_current_shape(self):
        burst = self.import_shape_module("testbed.loadgenerator.burst", {})
        sinus = self.import_shape_module("testbed.loadgenerator.sinus", {})

        burst_shape = burst.BurstLoadShape()
        sinus_shape = sinus.SinusLoadShape()

        with patch.object(burst_shape, "get_run_time", return_value=30):
            burst_users, _ = burst_shape.tick()
        with patch.object(sinus_shape, "get_run_time", return_value=0):
            sinus_users, _ = sinus_shape.tick()

        # The repository's high-load burst profile starts at 300 users and
        # applies its deterministic (seed=1) default bias of 4 users.
        self.assertEqual(burst_users, 304)
        self.assertEqual(sinus_users, 85)

    def test_daily_shape_uses_percentage_stages(self):
        daily = self.import_shape_module(
            "testbed.loadgenerator.daily",
            {"DAILY_BASE_USERS": "600", "RUN_TIME_SECONDS": "0"},
        )
        shape = daily.DailyTrafficShape()
        samples = {
            0: (120, 2),
            7 * 3600: (240, 3),
            10.1 * 3600: (1200, 15),
            12 * 3600: (450, 10),
            13.1 * 3600: (1500, 20),
            23 * 3600: (150, 3),
        }
        for elapsed, expected in samples.items():
            with self.subTest(elapsed=elapsed), patch.object(
                shape, "get_run_time", return_value=elapsed
            ):
                self.assertEqual(shape.tick(), expected)

    def test_daily_configured_base_users_scales_percentages(self):
        daily = self.import_shape_module(
            "testbed.loadgenerator.daily",
            {"DAILY_BASE_USER": "200", "RUN_TIME_SECONDS": "0"},
        )
        daily.DailyTrafficShape.base_users = 200
        shape = daily.DailyTrafficShape()
        with patch.object(shape, "get_run_time", return_value=60):
            users, spawn_rate = shape.tick()
        self.assertEqual(users, 40)
        self.assertEqual(spawn_rate, 2)
        with patch.object(shape, "get_run_time", return_value=24 * 3600 + 60):
            wrapped_users, _ = shape.tick()
        self.assertEqual(wrapped_users, 40)


class ConnectionRecyclingTests(unittest.TestCase):
    def import_common(self, recycle_every):
        locust_stub = types.SimpleNamespace(
            FastHttpUser=object,
            TaskSet=object,
            between=lambda *_args: None,
        )
        faker_stub = types.SimpleNamespace(Faker=lambda: object())
        sys.modules.pop("testbed.loadgenerator.common", None)
        with patch.dict(
            os.environ,
            {"CONNECTION_RECYCLE_EVERY_REQUESTS": str(recycle_every)},
            clear=True,
        ), patch.dict(
            sys.modules,
            {"faker": faker_stub, "locust": locust_stub},
        ):
            return importlib.import_module("testbed.loadgenerator.common")

    def test_connection_pool_closes_after_every_configured_request_count(self):
        common = self.import_common(2)

        class Pool:
            def __init__(self):
                self.close_calls = 0

            def close(self):
                self.close_calls += 1

        class Client:
            def __init__(self):
                self.client = types.SimpleNamespace(clientpool=Pool())
                self.calls = []

            def get(self, path, *args, **kwargs):
                self.calls.append(("get", path, args, kwargs))
                return path

        user = types.SimpleNamespace(
            client=Client(),
            requests_since_connection_recycle=0,
        )

        common.request(user, "get", "/first")
        self.assertEqual(user.client.client.clientpool.close_calls, 0)
        self.assertEqual(user.requests_since_connection_recycle, 1)

        common.request(user, "get", "/second")
        self.assertEqual(user.client.client.clientpool.close_calls, 1)
        self.assertEqual(user.requests_since_connection_recycle, 0)

        common.request(user, "get", "/third")
        self.assertEqual(user.client.client.clientpool.close_calls, 1)
        self.assertEqual(user.requests_since_connection_recycle, 1)


if __name__ == "__main__":
    unittest.main()
