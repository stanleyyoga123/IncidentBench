# EvaluationOrchestrator store API

Base path `/api/v1` on `evaluation-orchestrator:8080`. Existing worker job,
result, audit and artifact payloads and operation IDs are unchanged. Internal
routes use `AGENT_STORE_TOKEN`; lesson controls use `AGENT_CONTROL_TOKEN`.
Detector ingestion and lifecycle controls moved to
[AgentOrchestrator](../../../Agents/Orchestrator/docs/agent-api.md).

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `list_incident_lessons` | `GET /lessons` | List active/all reusable lessons. |
| `get_incident_lesson` | `GET /lessons/{id}` | Read one lesson and version. |
| `enable_incident_lesson` | `POST /lessons/{id}/enable` | Enable a lesson with actor/reason/version. |
| `disable_incident_lesson` | `POST /lessons/{id}/disable` | Disable a lesson with actor/reason/version. |
| `create_internal_rca_job` | `POST /internal/rca/jobs` | Persist an RCA job for RCAAgent. |
| `get_internal_rca_job` | `GET /internal/rca/jobs/{id}` | Read a persisted RCA job. |
| `create_internal_remediation_job` | `POST /internal/remediation/jobs` | Persist a remediation job. |
| `get_internal_remediation_job` | `GET /internal/remediation/jobs/{id}` | Read a persisted remediation job. |
| `create_internal_learning_job` | `POST /internal/learning/jobs` | Persist an idempotent learning job. |
| `get_internal_learning_job` | `GET /internal/learning/jobs/{id}` | Read a persisted learning job. |
| `claim_agent_execution` | `POST /internal/execution/claim` | Claim the singleton slot or return 204. |
| `renew_agent_execution` | `POST /internal/execution/renew` | Extend a held execution lease. |
| `finish_internal_rca_job` | `POST /internal/rca/jobs/{id}/finish` | Apply RCA retry policy and release the slot. |
| `finish_internal_remediation_job` | `POST /internal/remediation/jobs/{id}/finish` | Finish as `succeeded` or `failed`. |
| `finish_internal_learning_job` | `POST /internal/learning/jobs/{id}/finish` | Publish valid lessons or apply retry policy. |
| `record_internal_rca_tool_call` | `POST /internal/rca/jobs/{id}/tool-calls` | Insert an RCA tool-call audit. |
| `record_internal_remediation_tool_call` | `POST /internal/remediation/jobs/{id}/tool-calls` | Insert a remediator audit; write_file upserts artifacts. |
| `upsert_internal_remediation_artifact` | `POST /internal/remediation/jobs/{id}/artifacts` | Upsert a named artifact. |
| `list_internal_remediation_artifacts` | `GET /internal/remediation/jobs/{id}/artifacts` | List artifact filenames. |

`record_internal_agent_output`: `POST /api/v1/internal/{service}/jobs/{job_id}/output`
checkpoints `raw_output` and optional `result` while the request's `lease_owner`
owns the running job. It uses the store token, returning 204 or 409 for a stale
lease/maintenance. Services are `rca`, `remediation`, `learning`. Finish calls
preserve checkpointed fields when omitted. Remediation failures remain terminal
with retained output and do not replay ambiguous mutations.

The additional `/api/v1/internal/orchestration/...` persistence routes are used
by AgentOrchestrator for event ingestion, workflow claims/reads/transitions, job
attachment, lesson retrieval and audit snapshots. They require the store token;
mutations use the same maintenance gate. They do not call downstream agents.
Refer to `/openapi.json` for their typed request/response contracts.

See [evaluation API](evaluation-api.md) for Runner control and exports.
