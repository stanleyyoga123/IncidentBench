# AgentOrchestrator lifecycle API

Base path `/api/v1` on `agent-orchestrator:8080`. Existing paths, operation IDs,
request/response payloads, and ingestion/control tokens are preserved.

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `ingest_anomaly_events` | `POST /anomalies` | Commit 1–1000 event envelopes; returns accepted/duplicate counts. |
| `list_agent_workflows` | `GET /workflows` | List workflow status and job references. |
| `get_agent_workflow` | `GET /workflows/{id}` | Read one workflow/version/decision/error. |
| `approve_agent_workflow` | `POST /workflows/{id}/approve` | Optional manual approve; the reconciler auto-approves as `agent-orchestrator` when RCA requires remediation. |
| `decline_agent_workflow` | `POST /workflows/{id}/decline` | Close without mutation while status is still `awaiting_approval`. |
| `retry_agent_workflow` | `POST /workflows/{id}/retry` | Explicitly resubmit a failed/reviewed phase. |
| `get_agent_orchestrator_health` | `GET /health` | Health and global-slot availability. |

Internal job storage, lesson APIs, and evaluation export are hosted by
[EvaluationOrchestrator](../../../EvaluationPlatform/Orchestrator/docs/agent-api.md).
A detector acknowledgement still means the batch was committed or already
present. Workflow decisions retain `expected_version`; invalid or stale
transitions return 409. Maintenance blocks ingestion and lifecycle mutations.
