# Agent lifecycle orchestration

AgentOrchestrator coordinates the existing incident workflow through the same
RCA, remediation and learning job APIs. It owns decisions and downstream calls;
EvaluationOrchestrator performs all persistence through authenticated HTTP.

1. Detector events enter `POST /api/v1/anomalies`. Forward them to the persistence
   service and acknowledge only after committed acceptance/duplicate results.
2. Every 60 seconds, check the global slot and claim up to 100 oldest pending
   events from one namespace scope. Retrieve at most 40 active relevant lessons
   within 24,000 serialized characters and submit the RCA job with its existing
   deterministic idempotency key.
3. Reconcile every five seconds. Successful RCA requiring remediation enters
   `awaiting_approval`; automatically approve as `agent-orchestrator`, construct
   the canonical SHA-256 snapshot, and submit remediation. The approval wait
   consumes no execution slot. Explicit decline/retry routes remain available.
4. Successful no-action RCA and completed remediation output enter learning.
   Submit the existing hashed source snapshot with bounded tool audits.
   Completion status does not itself prove service recovery.
5. Finalize after learning success or its third failure. Preserve the existing
   terminal behavior for ambiguous remediation failure; do not replay mutations.

Worker jobs, leases, tool audits, raw outputs, artifacts and lessons continue to
use the EvaluationOrchestrator job-store API. The singleton execution slot still
serializes all three job types, including direct submissions. No table, status,
result schema, idempotency format or archive layout changes in this split.

## Response-loss recovery

Reconciliation includes the existing `rca_submitting` and
`remediation_submitting` states. If a persistence response is lost after commit,
the next pass resumes from the durable workflow instead of deleting it or
marking a successfully submitted job failed. Submission reuses the original
idempotency key: attempt 1 for an initial phase, or the persisted workflow
version for an explicit retry. This recovers the same job; it does not replay
an already executed remediation under a new identity. Lifecycle operations are
serialized within the single coordinator, and its Deployment uses `Recreate`.

## Maintenance

A read-only PostgreSQL connection holds the existing shared advisory lock over
an entire dispatch operation, including nested HTTP job submissions. It checks
`evaluation_control.maintenance` before allowing work. EvaluationOrchestrator
uses the matching exclusive lock for acquire/pause/reset transitions and shared
locks around persistence mutations. Shared lock acquisition is nonblocking to
avoid nested dispatch deadlocks when a transition is waiting.

This is a deliberate narrow database dependency to preserve the current
synchronization without a migration or a new distributed lease protocol.
AgentOrchestrator contains no workflow SQL writes. Both orchestrators stay
running during baseline; Runner scales only its configured worker deployments.

## Service boundary

`app/features/agent_workflow/` owns coordinator logic, loops, downstream clients,
HTTP workflow-store client and detector/workflow routes. `app/infrastructure/`
owns authentication, conflict handling and read-only maintenance locking.
The service has its own build, deployment, ConfigMap and Secret. No runtime
imports reach into EvaluationPlatform's application package.
