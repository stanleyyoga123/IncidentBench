import unittest
from pathlib import Path

from testbed.cli import parse_args


class CliTests(unittest.TestCase):
    def test_collection_scenario_path_is_accepted(self):
        args = parse_args(
            [
                "--loadgenerator",
                "constant",
                "--scenario",
                "collections/online-boutique-scenario/01-node-delay-worker-3.json",
            ]
        )
        self.assertEqual(
            args.scenario,
            Path("collections/online-boutique-scenario/01-node-delay-worker-3.json"),
        )

    def test_negative_grace_period_is_rejected(self):
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--loadgenerator",
                    "constant",
                    "--scenario",
                    "scenario.json",
                    "--grace-period",
                    "-1",
                ]
            )

    def test_skip_reset_is_no_longer_supported(self):
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--loadgenerator",
                    "constant",
                    "--scenario",
                    "scenario.json",
                    "--skip-reset",
                ]
            )

    def test_postgres_dsn_is_not_a_testbed_flag(self):
        with self.assertRaises(SystemExit):
            parse_args(
                [
                    "--loadgenerator",
                    "constant",
                    "--scenario",
                    "scenario.json",
                    "--postgres-dsn",
                    "postgresql://example",
                ]
            )
