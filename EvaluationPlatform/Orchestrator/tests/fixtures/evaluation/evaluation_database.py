from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock


class EvaluationDatabase:
    """Offline SQL driver limited to evaluation controls and exports.

    Unexpected workflow queries fail, so evaluation feature tests cannot silently
    reach the agent workflow persistence boundary.
    """

    def __init__(self) -> None:
        self._state: dict[str, Any] = {
            "id": 1, "run_id": None, "maintenance": False, "reset_done": False,
        }

    @contextmanager
    def connection(self) -> Iterator[MagicMock]:
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        def execute(query: str, params: tuple = ()) -> None:
            normalized = " ".join(query.split())
            if "pg_try_advisory_xact_lock_shared" in normalized:
                cursor.fetchone.return_value = {"locked": True}
            elif "pg_advisory" in normalized:
                return
            elif normalized.startswith("SET TRANSACTION"):
                return
            elif normalized.startswith("SELECT") and "evaluation_control" in normalized:
                cursor.fetchone.return_value = self._state.copy()
            elif "SET run_id=%s" in normalized:
                self._state.update(run_id=params[0], maintenance=True, reset_done=False)
            elif "SET maintenance=true" in normalized:
                self._state["maintenance"] = True
            elif "SET maintenance=false" in normalized:
                self._state["maintenance"] = False
            elif "SET reset_done=true" in normalized:
                self._state["reset_done"] = True
            elif "SET run_id=NULL" in normalized:
                self._state["run_id"] = None
            elif normalized.startswith(("TRUNCATE", "DELETE FROM agent_execution_slot", "INSERT INTO agent_execution_slot")):
                return
            elif "json_agg" in normalized:
                cursor.fetchone.return_value = {"data": []}
            else:
                raise AssertionError(f"Unexpected evaluation database query: {normalized}")

        cursor.execute.side_effect = execute
        yield connection
