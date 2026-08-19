# RCAAgent agent API

Use the RCA submission bearer token.

| operationId | Method/path | Purpose |
| --- | --- | --- |
| `create_rca_job` | `POST /api/v1/rca/jobs` | Submit anomaly payloads, optional caller context, and up to 40 validated historical lessons; returns 202 and durable ID. |
| `get_rca_job` | `GET /api/v1/rca/jobs/{id}` | Read status, attempts, structured result, raw audit context, and errors. |
| `get_rca_agent_health` | `GET /health` | Service health. |

Always send an `Idempotency-Key`. Poll terminal states `succeeded` or `failed`;
queued/running are non-terminal. A successful result is evidence, not approval.
The public job API persists by calling AgentOrchestrator's internal job-store.
Historical lessons are inserted in the user prompt as untrusted hypotheses and
never replace current MCP evidence.
