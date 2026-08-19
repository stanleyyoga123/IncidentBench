# Runtime flows

## Detection and RCA

1. AnomalyDetector fetches the aligned Prometheus window and evaluates the
   active detector profiles.
2. It builds deterministic event IDs and submits one authenticated batch.
3. AgentOrchestrator commits all events before returning acknowledgement.
4. Only then does AnomalyDetector start per-series cooldown.
5. Every 60 seconds AgentOrchestrator claims the oldest 100 pending events and
   creates one RCA job.
6. RCAAgent acquires the global lease through AgentOrchestrator, gathers
   evidence through investigation MCPTools, persists a structured result and
   audits via the job-store APIs, then releases the lease.
7. A no-action result completes the workflow. A remediation plan enters
   `awaiting_approval` briefly; reconcile immediately auto-approves as
   `agent-orchestrator` and submits Remediator. That wait does not consume the
   execution slot.

Delivery uses bounded retries and no local outbox. A failed event is eligible
for detection next cycle. If the underlying anomaly recovers before that next
cycle, the event can be lost; this is an accepted fail-and-re-detect tradeoff.

## Remediation

1. When RCA sets `remediation_required=true`, AgentOrchestrator auto-approves
   as `agent-orchestrator`, snapshots the RCA result, calculates its canonical
   SHA-256, and submits a remediation job. Control `POST /workflows/{id}/approve`
   remains available; `decline` still works only while status is
   `awaiting_approval`.
2. RemediatorAgent validates the snapshot hash and approval metadata, then waits
   for the shared lease.
3. It validates current state, writes session artifacts, runs Ansible check mode,
   performs guarded live execution, then verifies directly.
4. Success completes the workflow. A crash or ambiguous failure after execution
   begins becomes `needs_review`; only an explicit retry decision can proceed.

Failed RCA or reviewed remediation can be retried with a fresh versioned
idempotency key.

## Evaluation

Evaluation scales/waits for all six deployments, injects workload/faults,
captures evidence, and finalizes cleanup. Service restart logic remains in
Evaluation. Evaluation also owns its runner Secret, Ansible role/playbook, and
deploy script. MCPTools owns the network-probe DaemonSets; Infrastructure owns
only the prerequisite cluster platform and namespaces.
