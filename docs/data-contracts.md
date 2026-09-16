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

## Evaluation interface

Versioned scenario/global/suite JSON resolves experiment behavior; environment JSON
contains endpoints and token-variable names. The shell-hook context contains the
resolved scenario, run ID, scenario path and non-secret environment configuration.
`evaluation_control` persists serial ownership, maintenance, and reset idempotency.
[Evaluation API](../EvaluationPlatform/Orchestrator/docs/evaluation-api.md) documents
authentication, transitions and the version-1 export envelope. Existing session
arrays and metadata version 2 remain compatible with the offline grader.


## Offline archive grading

The Grader uses the original Runner archive format: Locust CSV counters,
Prometheus service metrics, metadata and exported sessions. No Runner update or
additional scenario is required. Methodology `archive-recovery-v3` separates a
descriptive service recovery proxy from semantic quality and unverified safety.
The evaluation policy is owned by the Grader. See the
[methodology](../EvaluationPlatform/Grader/docs/methodology.md),
[metrics](../EvaluationPlatform/Grader/docs/metrics.md), and
[input contract](../EvaluationPlatform/Grader/docs/evidence-contract.md).

## Durable agent outputs and autonomous failure

`POST /api/v1/internal/{service}/jobs/{job_id}/output` accepts `lease_owner`,
`raw_output`, and optional structured `result` for `rca`, `remediation`, or
`learning`. It uses the store token and requires a running, unexpired matching
job lease. Each engine checkpoints generated text before parsing or verification;
Remediator additionally checkpoints its parsed result before completion.
Finish calls preserve checkpointed fields when no replacement is supplied.
The existing session exports include these fields on unsuccessful jobs too.

Remediation jobs with nonempty final agent text finish as `succeeded` and enter
learning, even when that text reports execution errors or unverified recovery.
This status means output completion, not service recovery; grading and learning
assess the recorded evidence separately. Empty output, runtime/persistence errors
preventing completion, and expired leases still finish as `failed`, release the
execution slot, and automatically finalize the workflow and anomalies. They do not wait for human review or replay
an ambiguous mutation. New incidents proceed normally. Legacy `needs_review`
finish requests are accepted during rolling upgrades and normalized to `failed`;
legacy review workflows are finalized by reconciliation. Existing archived files
are immutable and cannot recover text that was never persisted.
