from __future__ import annotations

import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = (
    "detected_anomaly",
    "in_progress",
    "completed",
    "remediation",
    "remediation_ansible_run",
)
AGENT_TABLES = (
    "anomaly_event",
    "agent_workflow",
    "rca_job",
    "remediation_job",
    "agent_execution_slot",
    "agent_tool_call",
    "remediation_artifact",
)
EXPECTED_COLUMNS = {
    "detected_anomaly": {
        "id", "timestamp", "resource", "name", "metrics", "method", "detail"
    },
    "in_progress": {
        "id", "timestamp", "resource", "name", "metrics", "method", "detail"
    },
    "completed": {
        "id", "timestamp", "resource", "name", "metrics", "method", "detail"
    },
    "remediation": {
        "id",
        "session_id",
        "anomaly_ids",
        "anomalies",
        "grouped_anomalies",
        "remediation_output",
        "changes",
        "created_at",
    },
    "remediation_ansible_run": {
        "id",
        "session_id",
        "stdout",
        "ansible_file_content",
        "check_mode",
        "extra_vars",
        "created_at",
    },
}


def _load_initial_migration():
    path = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "20260817_0001_initial_schema.py"
    )
    spec = spec_from_file_location("initial_schema_migration", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load migration: {path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_agent_migration():
    path = PROJECT_ROOT / "migrations" / "versions" / "20260817_0002_agent_services.py"
    spec = spec_from_file_location("agent_services_migration", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeOperations:
    def __init__(self):
        self.context = Mock(as_sql=False)
        self.bind = object()
        self.created_tables: list[str] = []

    def get_context(self):
        return self.context

    def get_bind(self):
        return self.bind

    def create_table(self, table_name, *_columns):
        self.created_tables.append(table_name)


class MigrationContractTest(TestCase):
    def _alembic(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", "alembic.ini", *arguments],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_history_has_one_head(self) -> None:
        result = self._alembic("heads")

        self.assertIn("20260817_0002 (head)", result.stdout)

    def test_offline_upgrade_creates_the_complete_schema(self) -> None:
        result = self._alembic("upgrade", "head", "--sql")
        sql = result.stdout.lower()

        for table_name in EXPECTED_TABLES:
            self.assertIn(f"create table {table_name}", sql)
            self.assertIn(f"drop table {table_name}", sql)
        for table_name in AGENT_TABLES:
            self.assertIn(f"create table {table_name}", sql)
        self.assertIn("create table alembic_version", sql)
        self.assertIn("insert into alembic_version", sql)

    def test_existing_legacy_schema_is_adopted_without_recreation(self) -> None:
        migration = _load_initial_migration()
        operations = FakeOperations()
        inspector = Mock()
        inspector.get_table_names.return_value = list(EXPECTED_TABLES)
        inspector.get_columns.side_effect = lambda table: [
            {"name": column} for column in EXPECTED_COLUMNS[table]
        ]

        with (
            patch.object(migration, "op", operations),
            patch.object(migration.sa, "inspect", return_value=inspector),
        ):
            migration.upgrade()

        self.assertEqual([], operations.created_tables)

    def test_incompatible_legacy_schema_fails_adoption(self) -> None:
        migration = _load_initial_migration()
        operations = FakeOperations()
        inspector = Mock()
        inspector.get_table_names.return_value = ["detected_anomaly"]
        inspector.get_columns.return_value = [
            {"name": column}
            for column in EXPECTED_COLUMNS["detected_anomaly"] - {"detail"}
        ]

        with (
            patch.object(migration, "op", operations),
            patch.object(migration.sa, "inspect", return_value=inspector),
            self.assertRaisesRegex(RuntimeError, "missing required columns: detail"),
        ):
            migration.upgrade()

    def test_non_empty_legacy_reset_requires_explicit_flag(self) -> None:
        migration = _load_agent_migration()
        operations = FakeOperations()
        inspector = Mock()
        inspector.get_table_names.return_value = ["detected_anomaly"]
        result = Mock()
        result.scalar_one.return_value = 2
        operations.bind = Mock()
        operations.bind.execute.return_value = result

        with (
            patch.object(migration, "op", operations),
            patch.object(migration.sa, "inspect", return_value=inspector),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaisesRegex(RuntimeError, "ALLOW_AGENT_WORKFLOW_RESET=true"),
        ):
            migration._require_destructive_reset()

    def test_non_empty_legacy_reset_accepts_explicit_flag(self) -> None:
        migration = _load_agent_migration()
        operations = FakeOperations()
        inspector = Mock()
        inspector.get_table_names.return_value = ["detected_anomaly"]
        result = Mock()
        result.scalar_one.return_value = 1
        operations.bind = Mock()
        operations.bind.execute.return_value = result

        with (
            patch.object(migration, "op", operations),
            patch.object(migration.sa, "inspect", return_value=inspector),
            patch.dict("os.environ", {"ALLOW_AGENT_WORKFLOW_RESET": "true"}, clear=True),
        ):
            migration._require_destructive_reset()


if __name__ == "__main__":
    from unittest import main

    main()
