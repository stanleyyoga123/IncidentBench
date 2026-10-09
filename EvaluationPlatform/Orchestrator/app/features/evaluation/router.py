from typing import Callable

from fastapi import APIRouter, Depends

from features.evaluation.evaluation_request import EvaluationRequest
from features.evaluation.evaluation_service import EvaluationService


def create_evaluation_router(
    evaluation: EvaluationService, control_auth: Callable
) -> APIRouter:
    app = APIRouter()
    control_auth = Depends(control_auth)

    @app.get(
        "/api/v1/evaluation",
        dependencies=[control_auth],
        operation_id="get_evaluation_state",
    )
    def state():
        return evaluation.state()

    def endpoint(action):
        def command(request: EvaluationRequest):
            return evaluation.command(action, request.run_id)

        return command

    for action in ("acquire", "pause", "resume", "reset", "release"):
        app.post(
            "/api/v1/evaluation/" + action,
            dependencies=[control_auth],
            operation_id="evaluation_" + action,
        )(endpoint(action))

    @app.get(
        "/api/v1/evaluation/export",
        dependencies=[control_auth],
        operation_id="export_evaluation_sessions",
    )
    def export(run_id: str):
        return evaluation.export(run_id)

    return app
