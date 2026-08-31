# Data and API contracts

## Anomaly envelope

Required fields are `event_id`, timezone-aware `detected_at`, `resource`, `name`,
`metric`, `method`, and `detail`. `namespace` is required for namespaced
deployment events and null for cluster-scoped node events. Optional provenance is `profile_id`,
`profile_version`, and `profile_parameters`. `event_id` is deterministic over
the stable detection content; duplicate values do not create new rows.

## RCA result

The structured result contains `remediation_required`, `incident_state`,
`summary`, `failed_investigations`, `evidence`, `impact_scope`, `uncertainty`,
and a bounded `remediation_plan`. Raw model text is audit context only.

## Remediation request/result

Requests contain workflow and RCA IDs, an RCA result snapshot, its canonical
JSON SHA-256, and approval actor/reason. After RCA requires remediation,
AgentOrchestrator fills those fields as `agent-orchestrator` / automatic
approval. Results contain execution summary, changes, verification, artifacts,
raw audit context, and errors.

## Learning request/result

Learning requests contain a workflow ID and canonical SHA-256-protected source
snapshot: anomalies, structured RCA, optional remediation, and bounded tool-call
audits. Results contain a summary and zero or more atomic lessons categorized as
investigation, diagnosis, remediation, verification, or guardrail. Lessons carry
applicability, avoidance guidance, evidence references, optional scope/tags, and
confidence. Namespace-scoped lessons retain their application namespace;
cluster-wide lessons use a null namespace. They remain untrusted historical
hypotheses.

## Database

`anomaly_event` belongs to `agent_workflow`; workflows reference `rca_job` and
`remediation_job` and `learning_job`; learning jobs publish `incident_lesson` rows.
`agent_execution_slot` has exactly one row (`id=1`).
`agent_tool_call` records service/job/tool/arguments/result/outcome.
`remediation_artifact` stores job-scoped filename, content, and SHA-256.
AgentOrchestrator is the only application that performs DML against these
tables.

Jobs and workflows use UUID identities, status/version, timestamps, attempts,
errors, lease owner/expiry, JSONB request/result, and idempotency keys.

## Deployment credentials

Committed `kubernetes/secret.example.yml` files contain only `++++++++`
placeholders. Copy them to ignored `kubernetes/secret.yml` before deployment.
Pairwise bearer values must match exactly between detector/orchestrator,
orchestrator/RCA, orchestrator/remediator, orchestrator/learning, all job-service store
token, RCA/investigation MCP, and remediator/remediation MCP. The two MCP
tokens and AgentOrchestrator's control token remain distinct. DatabaseJob
separately owns the PostgreSQL identity used to construct AgentOrchestrator's
`DATABASE_DSN`. RCAAgent, RemediatorAgent, and LearningAgent have no database credentials.
