# AgentOrchestrator agent API

Base path `/api/v1`. Send `Authorization: Bearer <token>`. The ingestion token
can call only `POST /anomalies`; the control token can call workflow endpoints;
the store token can call only `/internal/...` job-store endpoints.

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `ingest_anomaly_events` | `POST /anomalies` | Commit 1–1000 event envelopes; returns accepted/duplicate counts. |
| `list_agent_workflows` | `GET /workflows` | List workflow status and job references. |
| `get_agent_workflow` | `GET /workflows/{id}` | Read one workflow/version/decision/error. |
| `approve_agent_workflow` | `POST /workflows/{id}/approve` | Supply actor, reason, expected_version and submit remediation. |
| `decline_agent_workflow` | `POST /workflows/{id}/decline` | Close without mutation. |
| `retry_agent_workflow` | `POST /workflows/{id}/retry` | Explicitly resubmit a failed/reviewed phase. |
| `get_agent_orchestrator_health` | `GET /health` | Health and global-slot availability. |
| `create_internal_rca_job` | `POST /internal/rca/jobs` | Persist an RCA job for RCAAgent. |
| `get_internal_rca_job` | `GET /internal/rca/jobs/{id}` | Read a persisted RCA job. |
| `create_internal_remediation_job` | `POST /internal/remediation/jobs` | Persist a remediation job. |
| `get_internal_remediation_job` | `GET /internal/remediation/jobs/{id}` | Read a persisted remediation job. |
| `claim_agent_execution` | `POST /internal/execution/claim` | Claim the singleton slot or return 204. |
| `renew_agent_execution` | `POST /internal/execution/renew` | Extend a held execution lease. |
| `finish_internal_rca_job` | `POST /internal/rca/jobs/{id}/finish` | Apply RCA retry policy and release the slot. |
| `finish_internal_remediation_job` | `POST /internal/remediation/jobs/{id}/finish` | Finish as `succeeded` or `needs_review`. |
| `record_internal_rca_tool_call` | `POST /internal/rca/jobs/{id}/tool-calls` | Insert an RCA tool-call audit. |
| `record_internal_remediation_tool_call` | `POST /internal/remediation/jobs/{id}/tool-calls` | Insert a remediator audit; write_file upserts artifacts. |
| `upsert_internal_remediation_artifact` | `POST /internal/remediation/jobs/{id}/artifacts` | Upsert a named artifact. |
| `list_internal_remediation_artifacts` | `GET /internal/remediation/jobs/{id}/artifacts` | List artifact filenames. |

Treat HTTP 409 as a stale version or invalid transition and re-read before
deciding. Treat duplicate ingestion as success. Never auto-approve remediation.
