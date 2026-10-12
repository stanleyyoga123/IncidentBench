from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from features.agent_workflow.workflow_store_client import WorkflowStoreClient
from infrastructure.workflow_conflict_error import WorkflowConflictError
from infrastructure.persistence_unavailable_error import PersistenceUnavailableError


def store_with_response(response: httpx.Response) -> WorkflowStoreClient:
    return WorkflowStoreClient(httpx.Client(base_url="http://platform", transport=httpx.MockTransport(lambda request: response)))


def test_missing_workflow_maps_to_none_and_mutation_maps_to_key_error():
    store = store_with_response(httpx.Response(404, json={"detail": "workflow not found"}))
    assert store.get_workflow(uuid4()) is None
    with pytest.raises(KeyError):
        store.decide(uuid4(), "approved", "operator", "confirmed", 1)
    store.close()


def test_store_conflict_preserves_domain_error():
    store = store_with_response(httpx.Response(409, json={"detail": "stale workflow version"}))
    with pytest.raises(WorkflowConflictError, match="stale workflow version"):
        store.reset_for_retry(uuid4(), 1, "operator", "retry failed submission")
    store.close()


def test_claim_handles_no_pending_events_and_validates_received_workflow():
    store = store_with_response(httpx.Response(204))
    assert store.claim_pending(100) is None
    store.close()
    store = store_with_response(httpx.Response(200, json={"workflow": {"id": "invalid"}, "anomalies": []}))
    with pytest.raises(ValidationError):
        store.claim_pending(100)
    store.close()


def test_store_http_failure_is_visible_to_dispatch():
    store = store_with_response(httpx.Response(503, json={"detail": "unavailable"}))
    with pytest.raises(PersistenceUnavailableError):
        store.claim_pending(100)
    store.close()


def test_store_timeout_is_visible_to_dispatch():
    def timeout(request):
        raise httpx.ReadTimeout("persistence timed out", request=request)
    store = WorkflowStoreClient(httpx.Client(base_url="http://platform", transport=httpx.MockTransport(timeout)))
    with pytest.raises(PersistenceUnavailableError):
        store.execution_available()
    store.close()
