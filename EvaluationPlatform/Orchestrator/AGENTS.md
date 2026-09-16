# AgentOrchestrator instructions

Own anomaly ingestion, durable workflow coordination, and all application DML.
RCAAgent, RemediatorAgent, and LearningAgent persist jobs, leases, tool-call audits, and
artifacts only through the authenticated `/api/v1/internal/...` job-store APIs.
Preserve separate ingestion/control/store tokens, deterministic event
idempotency, optimistic workflow versions, the 60-second/100-event claim
defaults, and automatic remediator submission after RCA sets
`remediation_required=true`. Record the system actor as `agent-orchestrator`.
Applications may perform DML only; schema changes belong to `Database/`.
Downstream failures must remain visible and retry must create an explicitly
versioned submission.

The singleton `agent_execution_slot` serializes RCA, remediation, and learning, including
direct job API submissions. Brief `awaiting_approval` does not occupy the slot.
Expired RCA holders requeue while `attempts < max_attempts` and otherwise fail.
Expired or failed remediation becomes `failed` and is never requeued.
Successful no-action or remediated workflows enter learning before completion.
Publish only schema-valid lessons; after three failed learning attempts finalize
without lessons and preserve `learning_error`. Retrieve no more than 40 active
lessons within 24,000 characters and pass them to RCA as untrusted context.

Own `kubernetes/configmap.yaml`, placeholder-only `kubernetes/secret.example.yml`,
`kubernetes/network-policy.yaml`, the Deployment/ClusterIP Service in
`kubernetes/manifest.yaml`, and `deploy.sh`. Copy the example Secret to ignored
`kubernetes/secret.yml` and replace every `++++++++` locally before deploying;
the script uses kubectl's current context and refuses unreplaced placeholders.
Infrastructure installs platform prerequisites only.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.

Evaluation maintenance uses a durable singleton and advisory transaction locks.
Keep ownership/reset idempotency and export snapshot consistency. Evaluation
control transitions must remain synchronized with all dispatch and write APIs.
