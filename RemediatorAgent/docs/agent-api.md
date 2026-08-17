# RemediatorAgent agent API

Use the remediation submission bearer token.

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `create_remediation_job` | `POST /api/v1/remediation/jobs` | Submit approved RCA snapshot/hash/workflow; returns 202. |
| `get_remediation_job` | `GET /api/v1/remediation/jobs/{id}` | Read execution, verification, changes, artifacts, and errors. |
| `get_remediator_agent_health` | `GET /health` | Service health. |

The snapshot must say `remediation_required=true`, include actor/reason, and
match its canonical JSON SHA-256. `needs_review` is terminal until a human or
control agent explicitly reviews and retries through AgentOrchestrator.
