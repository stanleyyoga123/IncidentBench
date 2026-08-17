# AgentOrchestrator agent API

Base path `/api/v1`. Send `Authorization: Bearer <token>`. The ingestion token
can call only `POST /anomalies`; the control token can call workflow endpoints.

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `ingest_anomaly_events` | `POST /anomalies` | Commit 1–1000 event envelopes; returns accepted/duplicate counts. |
| `list_agent_workflows` | `GET /workflows` | List workflow status and job references. |
| `get_agent_workflow` | `GET /workflows/{id}` | Read one workflow/version/decision/error. |
| `approve_agent_workflow` | `POST /workflows/{id}/approve` | Supply actor, reason, expected_version and submit remediation. |
| `decline_agent_workflow` | `POST /workflows/{id}/decline` | Close without mutation. |
| `retry_agent_workflow` | `POST /workflows/{id}/retry` | Explicitly resubmit a failed/reviewed phase. |
| `get_agent_orchestrator_health` | `GET /health` | Health and global-slot availability. |

Treat HTTP 409 as a stale version or invalid transition and re-read before
deciding. Treat duplicate ingestion as success. Never auto-approve remediation.
