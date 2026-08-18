import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CURRENT_TABLES = (
    "anomaly_event",
    "agent_workflow",
    "rca_job",
    "remediation_job",
    "agent_tool_call",
    "remediation_artifact",
    "agent_execution_slot",
)
LEGACY_TABLES = ("detected_anomaly", "in_progress")


class PrerunTests(unittest.TestCase):
    def test_cleanup_sql_wipes_current_agent_tables(self):
        sql = (ROOT / "prerun" / "cleanup.sql").read_text()
        for table in CURRENT_TABLES:
            self.assertIn(table, sql)
        for table in LEGACY_TABLES:
            self.assertNotIn(table, sql)
        self.assertIn("TRUNCATE", sql)
        self.assertIn("UPDATE agent_execution_slot", sql)
        self.assertNotIn("TRUNCATE agent_execution_slot", sql)

    def test_prerun_recreates_online_boutique_from_central_kustomize(self):
        script = (ROOT / "prerun" / "run.sh").read_text()
        self.assertIn("kubectl delete ns", script)
        self.assertIn("kubectl apply -k", script)
        self.assertIn("cleanup.sh", script)
        self.assertNotIn("PLACEMENT_MANIFEST", script)
        self.assertNotIn("detected_anomaly", script)
        self.assertNotIn("in_progress", script)


class PostrunTests(unittest.TestCase):
    def test_queries_cover_anomaly_rca_and_remediation_sessions(self):
        queries = ROOT / "postrun" / "queries"
        expected = {
            "anomaly.sql": "anomaly_event",
            "rca_session.sql": "rca_job",
            "remediation_run.sql": "remediation_job",
            "remediation_session.sql": "remediator",
            "workflow.sql": "agent_workflow",
        }
        for filename, needle in expected.items():
            text = (queries / filename).read_text()
            self.assertIn(needle, text)
            self.assertNotIn("in_progress", text)
            self.assertNotIn("detected_anomaly", text)

    def test_postrun_writes_session_files_without_logging_dsn(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / "bin"
            bin_dir.mkdir()
            psql = bin_dir / "psql"
            psql.write_text(
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                "echo '[]'\n"
            )
            psql.chmod(psql.stat().st_mode | stat.S_IEXEC)
            output_dir = tmp_path / "run"
            output_dir.mkdir()
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            env["POSTGRES_DSN"] = "postgresql://secret-user:secret-pass@db/anomaly_detector"
            completed = subprocess.run(
                [str(ROOT / "postrun" / "run.sh"), "--output-dir", str(output_dir)],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            combined = completed.stdout + completed.stderr
            self.assertNotIn("secret-user", combined)
            self.assertNotIn("secret-pass", combined)
            sessions = output_dir / "sessions"
            for name in (
                "anomaly",
                "rca_session",
                "remediation_run",
                "remediation_session",
                "workflow",
            ):
                path = sessions / f"{name}.json"
                self.assertTrue(path.is_file(), name)
                self.assertEqual(path.read_text().strip(), "[]")

    def test_postrun_requires_postgres_dsn(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env.pop("POSTGRES_DSN", None)
            completed = subprocess.run(
                [str(ROOT / "postrun" / "run.sh"), "--output-dir", tmp],
                check=False,
                capture_output=True,
                text=True,
                env=env,
            )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("POSTGRES_DSN", completed.stderr)


class ScenarioOrchestratorTests(unittest.TestCase):
    def test_root_run_sh_invokes_prerun_testbed_and_postrun(self):
        script = (ROOT / "run.sh").read_text()
        self.assertIn("prerun/run.sh", script)
        self.assertIn("testbed/run.sh", script)
        self.assertIn("postrun/run.sh", script)
        self.assertIn("python -m testbed.main", (ROOT / "testbed" / "run.sh").read_text())
        self.assertNotIn("python -m src.main", script)
        self.assertNotIn("services/restart.sh", script)
