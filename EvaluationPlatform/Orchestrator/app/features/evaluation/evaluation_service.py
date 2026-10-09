from typing import Any

from features.evaluation.evaluation_repository import EvaluationRepository
from infrastructure.workflow_conflict_error import WorkflowConflictError


class EvaluationService:
    def __init__(self, repository: EvaluationRepository) -> None:
        self._repository = repository

    def state(self) -> dict[str, Any]:
        return self._repository.state()

    def command(self, action: str, run_id: str) -> dict[str, Any]:
        with self._repository.transition() as (cur, state):
            if action == "acquire":
                if state["run_id"] not in (None, run_id):
                    raise WorkflowConflictError(
                        "another evaluation owns this deployment"
                    )
                if state["run_id"] is None:
                    self._repository.acquire(cur, run_id)
            else:
                if state["run_id"] != run_id:
                    raise WorkflowConflictError(
                        "evaluation run does not own this deployment"
                    )
                if action == "pause":
                    self._repository.pause(cur)
                elif action == "resume":
                    self._repository.resume(cur)
                elif action == "reset":
                    if not state["maintenance"]:
                        raise WorkflowConflictError(
                            "reset requires maintenance and stopped workers"
                        )
                    if not state["reset_done"]:
                        self._repository.reset(cur)
                elif action == "release":
                    if not state["maintenance"]:
                        raise WorkflowConflictError("release requires maintenance")
                    self._repository.release(cur)
                else:
                    raise ValueError("unknown evaluation action")
            return self._repository.transition_state(cur)

    def export(self, run_id: str) -> dict[str, Any]:
        with self._repository.export_snapshot() as (cur, state):
            if state["run_id"] != run_id or not state["maintenance"]:
                raise WorkflowConflictError("export requires owning run in maintenance")
            return {
                "schema_version": 1,
                "run_id": run_id,
                "sessions": self._repository.export_sessions(cur),
            }
