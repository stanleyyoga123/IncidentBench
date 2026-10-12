from collections.abc import Callable, Iterator
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from features.agent_workflow.schemas.attach_job_request import AttachJobRequest
from features.agent_workflow.schemas.job_state_request import JobStateRequest
from features.agent_workflow.schemas.lesson_retrieval_request import LessonRetrievalRequest
from features.agent_workflow.schemas.pending_claim_request import PendingClaimRequest
from features.agent_workflow.schemas.pending_claim_response import PendingClaimResponse
from features.agent_workflow.schemas.rca_state_request import RCAStateRequest
from features.agent_workflow.schemas.submission_failure_request import SubmissionFailureRequest
from features.agent_workflow.schemas.workflow_decision_request import WorkflowDecisionRequest
from features.agent_workflow.schema import AnomalyBatchRequest, IngestionResponse, RetryRequest, Workflow
from features.agent_workflow.workflow_store import WorkflowStore
from infrastructure.maintenance_gate import MaintenanceGate


def create_orchestration_router(
    store: WorkflowStore, maintenance_gate: MaintenanceGate, authorize: Callable,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/internal/orchestration")

    def mutation_guard(_authorization: None = Depends(authorize)) -> Iterator[None]:
        with maintenance_gate.running():
            yield

    read = [Depends(authorize)]
    write = [Depends(mutation_guard)]

    @router.post("/anomalies", response_model=IngestionResponse, dependencies=write,
                 operation_id="persist_orchestration_anomalies")
    def ingest(request: AnomalyBatchRequest) -> IngestionResponse:
        accepted, duplicates, records = store.ingest(request.anomalies)
        return IngestionResponse(accepted=accepted, duplicates=duplicates,
                                 event_ids=[item.event_id for item in request.anomalies], records=records)

    @router.get("/execution/available", response_model=bool, dependencies=read,
                operation_id="get_orchestration_execution_availability")
    def execution_available() -> bool:
        return store.execution_available()

    @router.post("/workflows/claim", response_model=PendingClaimResponse, dependencies=write,
                 operation_id="claim_orchestration_pending_events")
    def claim_pending(request: PendingClaimRequest):
        claimed = store.claim_pending(request.limit)
        if claimed is None:
            return Response(status_code=204)
        workflow, anomalies = claimed
        return PendingClaimResponse(workflow=workflow, anomalies=anomalies)

    @router.get("/workflows/reconcilable", response_model=list[Workflow], dependencies=read,
                operation_id="list_orchestration_reconcilable_workflows")
    def list_reconcilable() -> list[Workflow]:
        return store.list_reconcilable()

    @router.get("/workflows", response_model=list[Workflow], dependencies=read,
                operation_id="list_orchestration_persisted_workflows")
    def list_workflows() -> list[Workflow]:
        return store.list_workflows()

    @router.get("/workflows/{workflow_id}", response_model=Workflow, dependencies=read,
                operation_id="get_orchestration_persisted_workflow")
    def get_workflow(workflow_id: UUID) -> Workflow:
        workflow = store.get_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return workflow

    @router.get("/workflows/{workflow_id}/anomalies", response_model=list[dict], dependencies=read,
                operation_id="get_orchestration_workflow_anomalies")
    def anomaly_payloads(workflow_id: UUID) -> list[dict]:
        return store.anomaly_payloads(workflow_id)

    @router.get("/workflows/{workflow_id}/tool-calls", response_model=list[dict], dependencies=read,
                operation_id="get_orchestration_workflow_tool_calls")
    def tool_calls(workflow_id: UUID) -> list[dict]:
        return store.tool_calls_for_workflow(get_workflow(workflow_id))

    @router.post("/lessons/retrieve", response_model=list[dict], dependencies=read,
                 operation_id="retrieve_orchestration_historical_lessons")
    def retrieve_lessons(request: LessonRetrievalRequest) -> list[dict]:
        return store.retrieve_lessons(request.anomalies)

    @router.post("/workflows/{workflow_id}/decision", response_model=Workflow, dependencies=write,
                 operation_id="persist_orchestration_workflow_decision")
    def decide(workflow_id: UUID, request: WorkflowDecisionRequest) -> Workflow:
        return store.decide(workflow_id, request.decision, request.actor,
                            request.reason, request.expected_version)

    @router.post("/workflows/{workflow_id}/retry", response_model=Workflow, dependencies=write,
                 operation_id="persist_orchestration_workflow_retry")
    def retry(workflow_id: UUID, request: RetryRequest) -> Workflow:
        return store.reset_for_retry(workflow_id, request.expected_version,
                                     request.actor, request.reason)

    @router.post("/workflows/{workflow_id}/rca/attach", status_code=204, dependencies=write,
                 operation_id="attach_orchestration_rca_job")
    def attach_rca(workflow_id: UUID, request: AttachJobRequest) -> None:
        store.attach_rca_job(workflow_id, request.job_id)

    @router.post("/workflows/{workflow_id}/rca/state", status_code=204, dependencies=write,
                 operation_id="persist_orchestration_rca_state")
    def set_rca_state(workflow_id: UUID, request: RCAStateRequest) -> None:
        store.set_rca_state(workflow_id, request.status, result=request.result, error=request.error)

    @router.post("/workflows/{workflow_id}/remediation/attach", status_code=204, dependencies=write,
                 operation_id="attach_orchestration_remediation_job")
    def attach_remediation(workflow_id: UUID, request: AttachJobRequest) -> None:
        store.attach_remediation_job(workflow_id, request.job_id)

    @router.post("/workflows/{workflow_id}/remediation/state", status_code=204, dependencies=write,
                 operation_id="persist_orchestration_remediation_state")
    def set_remediation_state(workflow_id: UUID, request: JobStateRequest) -> None:
        store.set_remediation_state(workflow_id, request.status, error=request.error)

    @router.post("/workflows/{workflow_id}/learning/attach", status_code=204, dependencies=write,
                 operation_id="attach_orchestration_learning_job")
    def attach_learning(workflow_id: UUID, request: AttachJobRequest) -> None:
        store.attach_learning_job(workflow_id, request.job_id)

    @router.post("/workflows/{workflow_id}/learning/state", status_code=204, dependencies=write,
                 operation_id="persist_orchestration_learning_state")
    def set_learning_state(workflow_id: UUID, request: JobStateRequest) -> None:
        store.set_learning_state(workflow_id, request.status, error=request.error)

    @router.post("/workflows/{workflow_id}/submission-failed", status_code=204, dependencies=write,
                 operation_id="orchestration_fail_submission")
    def fail_submission(workflow_id: UUID, request: SubmissionFailureRequest) -> None:
        store.fail_submission(workflow_id, request.error)

    @router.post("/workflows/{workflow_id}/downstream-failed", status_code=204, dependencies=write,
                 operation_id="orchestration_mark_submission_failed")
    def mark_submission_failed(workflow_id: UUID, request: SubmissionFailureRequest) -> None:
        store.mark_submission_failed(workflow_id, request.error)

    return router
