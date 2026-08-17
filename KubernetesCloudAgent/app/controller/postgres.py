from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from config import SETTINGS
from schema.anomaly import AnomalyBatch, AnomalyRow


DETECTED_ANOMALY_TABLE = "detected_anomaly"
IN_PROGRESS_TABLE = "in_progress"
COMPLETED_TABLE = "completed"
REMEDIATION_TABLE = "remediation"
REMEDIATION_ANSIBLE_RUN_TABLE = "remediation_ansible_run"
ANOMALY_COLUMNS = (
    "id",
    "timestamp",
    "resource",
    "name",
    "metrics",
    "method",
    "detail",
)


class PostgresAnomalyStore:
    def __init__(self, dsn: str | None = None):
        self._dsn = dsn or SETTINGS.postgres.dsn

    @contextmanager
    def _connection(self) -> Iterator[Connection[dict[str, Any]]]:
        with Connection.connect(self._dsn, row_factory=dict_row) as conn:
            yield conn

    def fetch_detected_anomalies(self) -> list[AnomalyRow]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._select_all_statement(DETECTED_ANOMALY_TABLE))
                rows = cur.fetchall()
        return self._validate_rows(rows)

    def fetch_in_progress_anomalies(self) -> list[AnomalyRow]:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(self._select_all_statement(IN_PROGRESS_TABLE))
                rows = cur.fetchall()
        return self._validate_rows(rows)

    def move_detected_to_in_progress(self) -> list[AnomalyRow]:
        return self._move_rows(DETECTED_ANOMALY_TABLE, IN_PROGRESS_TABLE)

    def move_in_progress_to_completed(self, anomaly_id: int) -> AnomalyRow | None:
        moved_rows = self._move_rows(
            IN_PROGRESS_TABLE,
            COMPLETED_TABLE,
            anomaly_id=anomaly_id,
        )
        return moved_rows[0] if moved_rows else None

    def move_in_progress_batch_to_completed(
        self,
        anomaly_ids: list[int],
    ) -> list[AnomalyRow]:
        return self._move_rows(
            IN_PROGRESS_TABLE,
            COMPLETED_TABLE,
            anomaly_ids=anomaly_ids,
        )

    def move_all_in_progress_to_completed(self) -> list[AnomalyRow]:
        return self._move_rows(IN_PROGRESS_TABLE, COMPLETED_TABLE)

    def record_remediation_session(
        self,
        session_id: str,
        batch: AnomalyBatch,
        remediation_output: str,
        changes: dict[str, Any],
    ) -> int:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            session_id,
                            anomaly_ids,
                            anomalies,
                            grouped_anomalies,
                            remediation_output,
                            changes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """
                    ).format(table=self._table_identifier(REMEDIATION_TABLE)),
                    (
                        session_id,
                        batch.row_ids(),
                        Jsonb(batch.model_dump(mode="json")),
                        Jsonb(
                            [
                                group.model_dump(mode="json")
                                for group in batch.grouped_by_name()
                            ]
                        ),
                        remediation_output,
                        Jsonb(changes),
                    ),
                )
                remediation_id = cur.fetchone()["id"]
            conn.commit()
        return int(remediation_id)

    def record_remediation_ansible_run(
        self,
        session_id: str,
        ansible_file_content: str,
        stdout: str,
        check: bool,
        extra_vars: dict[str, Any],
    ) -> int:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            session_id,
                            stdout,
                            ansible_file_content,
                            check_mode,
                            extra_vars
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING id
                        """
                    ).format(
                        table=self._table_identifier(REMEDIATION_ANSIBLE_RUN_TABLE)
                    ),
                    (
                        session_id,
                        stdout,
                        ansible_file_content,
                        check,
                        Jsonb(extra_vars),
                    ),
                )
                ansible_run_id = cur.fetchone()["id"]
            conn.commit()
        return int(ansible_run_id)

    def record_remediation_session_and_complete(
        self,
        session_id: str,
        batch: AnomalyBatch,
        remediation_output: str,
        changes: dict[str, Any],
    ) -> int:
        with self._connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL(
                        """
                        INSERT INTO {table} (
                            session_id,
                            anomaly_ids,
                            anomalies,
                            grouped_anomalies,
                            remediation_output,
                            changes
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """
                    ).format(table=self._table_identifier(REMEDIATION_TABLE)),
                    (
                        session_id,
                        batch.row_ids(),
                        Jsonb(batch.model_dump(mode="json")),
                        Jsonb(
                            [
                                group.model_dump(mode="json")
                                for group in batch.grouped_by_name()
                            ]
                        ),
                        remediation_output,
                        Jsonb(changes),
                    ),
                )
                remediation_id = cur.fetchone()["id"]
                self._execute_move_rows(
                    cur,
                    IN_PROGRESS_TABLE,
                    COMPLETED_TABLE,
                    anomaly_ids=batch.row_ids(),
                )
            conn.commit()
        return int(remediation_id)

    def _move_rows(
        self,
        source_table: str,
        target_table: str,
        anomaly_id: int | None = None,
        anomaly_ids: list[int] | None = None,
    ) -> list[AnomalyRow]:
        if anomaly_id is not None and anomaly_ids is not None:
            raise ValueError("Use anomaly_id or anomaly_ids, not both")
        if anomaly_ids == []:
            return []

        with self._connection() as conn:
            with conn.cursor() as cur:
                rows = self._execute_move_rows(
                    cur,
                    source_table,
                    target_table,
                    anomaly_id=anomaly_id,
                    anomaly_ids=anomaly_ids,
                )
            conn.commit()
        return self._validate_rows(rows)

    def _execute_move_rows(
        self,
        cur: Any,
        source_table: str,
        target_table: str,
        anomaly_id: int | None = None,
        anomaly_ids: list[int] | None = None,
    ) -> list[dict[str, Any]]:
        where_clause = sql.SQL("")
        params: tuple[Any, ...] = ()
        if anomaly_id is not None:
            where_clause = sql.SQL(" WHERE id = %s")
            params = (anomaly_id,)
        elif anomaly_ids is not None:
            where_clause = sql.SQL(" WHERE id = ANY(%s)")
            params = (anomaly_ids,)

        move_query = sql.SQL(
            """
            WITH moved AS (
                DELETE FROM {source}
                {where_clause}
                RETURNING {columns}
            ),
            upserted AS (
                INSERT INTO {target} ({columns})
                SELECT {columns} FROM moved
                ON CONFLICT (id) DO UPDATE SET
                    timestamp = EXCLUDED.timestamp,
                    resource = EXCLUDED.resource,
                    name = EXCLUDED.name,
                    metrics = EXCLUDED.metrics,
                    method = EXCLUDED.method,
                    detail = EXCLUDED.detail
                RETURNING {columns}
            )
            SELECT {columns}
            FROM upserted
            ORDER BY timestamp ASC, id ASC
            """
        ).format(
            source=self._table_identifier(source_table),
            target=self._table_identifier(target_table),
            where_clause=where_clause,
            columns=self._column_identifiers(),
        )
        cur.execute(move_query, params)
        return cur.fetchall()

    def _select_all_statement(self, table_name: str) -> sql.SQL:
        return sql.SQL(
            "SELECT {columns} FROM {table} ORDER BY timestamp ASC, id ASC"
        ).format(
            columns=self._column_identifiers(),
            table=self._table_identifier(table_name),
        )

    def _table_identifier(self, table_name: str) -> sql.Identifier:
        return sql.Identifier(table_name)

    def _column_identifiers(self) -> sql.SQL:
        return sql.SQL(", ").join(sql.Identifier(column) for column in ANOMALY_COLUMNS)

    def _validate_rows(self, rows: list[dict[str, Any]]) -> list[AnomalyRow]:
        return [AnomalyRow.model_validate(row) for row in rows]


@lru_cache
def get_postgres_store() -> PostgresAnomalyStore:
    return PostgresAnomalyStore()
