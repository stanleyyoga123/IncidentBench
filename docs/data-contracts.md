# Data and API contracts

## Anomaly envelope

Required fields are `event_id`, timezone-aware `detected_at`, `resource`, `name`,
`metric`, `method`, and `detail`. Optional provenance is `profile_id`,
`profile_version`, and `profile_parameters`. `event_id` is deterministic over
the stable detection content; duplicate values do not create new rows.

## RCA result

The structured result contains `remediation_required`, `incident_state`,
`summary`, `failed_investigations`, `evidence`, `impact_scope`, `uncertainty`,
and a bounded `remediation_plan`. Raw model text is audit context only.

## Remediation request/result

Requests contain workflow and RCA IDs, an RCA result snapshot, its canonical
JSON SHA-256, and approval actor/reason. Results contain execution summary,
changes, verification, artifacts, raw audit context, and errors.

## Database

`anomaly_event` belongs to `agent_workflow`; workflows reference `rca_job` and
`remediation_job`. `agent_execution_slot` has exactly one row (`id=1`).
`agent_tool_call` records service/job/tool/arguments/result/outcome.
`remediation_artifact` stores job-scoped filename, content, and SHA-256.

Jobs and workflows use UUID identities, status/version, timestamps, attempts,
errors, lease owner/expiry, JSONB request/result, and idempotency keys.

## Deployment credentials

Committed `kubernetes/secret.example.yml` files contain only `++++++++`
placeholders. Copy them to ignored `kubernetes/secret.yml` before deployment.
Pairwise bearer values must match exactly between detector/orchestrator,
orchestrator/RCA, orchestrator/remediator, RCA/investigation MCP, and
remediator/remediation MCP. The two MCP tokens and AgentOrchestrator's control
token remain distinct. DatabaseJob separately owns the PostgreSQL identity used
to construct each application's `DATABASE_DSN`.
