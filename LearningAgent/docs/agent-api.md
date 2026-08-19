# LearningAgent API

The ClusterIP endpoint is `http://learning-agent.agents.svc.cluster.local:8083`.
All job operations require `Authorization: Bearer <LEARNING_SUBMIT_TOKEN>`.

- `POST /api/v1/learning/jobs` (`create_learning_job`) accepts a workflow ID,
  canonical source snapshot, matching SHA-256, and optional `Idempotency-Key`.
  It returns `202` with a durable job.
- `GET /api/v1/learning/jobs/{id}` (`get_learning_job`) returns status,
  attempts, structured atomic lessons, raw audit output, and errors.
- `GET /health` (`get_learning_agent_health`) returns process health.

The submitted `source` must contain the same `workflow_id`, `completion_type`,
non-empty `anomalies`, structured `rca`, optional `remediation`, and at most 100
`tool_calls`. `remediation` is required only for `completion_type=remediated`.
Calculate `source_sha256` over compact, key-sorted canonical JSON. Reusing an
`Idempotency-Key` returns the already persisted job.

Terminal successful results contain `summary` and `lessons`. Every lesson has
`category`, `title`, `guidance`, `applies_when`, `avoid`, `evidence_refs`,
optional `resource`/`name`/`metric`, `tags`, and confidence from 0 to 1. Invalid
model JSON fails the attempt; after attempt three the job is terminal `failed`.

Learning jobs share the global execution slot with RCA and remediation. The
service never connects directly to PostgreSQL or Kubernetes.
