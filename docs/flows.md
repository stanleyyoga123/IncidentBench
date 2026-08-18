# Runtime flows

## Detection and RCA

1. AnomalyDetector fetches the aligned Prometheus window and evaluates the
   active detector profiles.
2. It builds deterministic event IDs and submits one authenticated batch.
3. AgentOrchestrator commits all events before returning acknowledgement.
4. Only then does AnomalyDetector start per-series cooldown.
5. Every 60 seconds AgentOrchestrator claims the oldest 100 pending events and
   creates one RCA job.
6. RCAAgent acquires the global lease, gathers evidence through investigation
   MCPTools, persists a structured result and audits, then releases the lease.
7. A no-action result completes the workflow. A remediation plan enters
   `awaiting_approval`, which consumes no execution slot.

Delivery uses bounded retries and no local outbox. A failed event is eligible
for detection next cycle. If the underlying anomaly recovers before that next
cycle, the event can be lost; this is an accepted fail-and-re-detect tradeoff.

## Approval and remediation

1. A control caller approves with actor, reason, and expected workflow version.
2. AgentOrchestrator snapshots the RCA result, calculates its canonical SHA-256,
   and submits a remediation job.
3. RemediatorAgent validates approval/hash and waits for the shared lease.
4. It validates current state, writes session artifacts, runs Ansible check mode,
   performs guarded live execution, then verifies directly.
5. Success completes the workflow. A crash or ambiguous failure after execution
   begins becomes `needs_review`; only an explicit retry decision can proceed.

Decline closes the workflow without remediation. Failed RCA or reviewed
remediation can be retried with a fresh versioned idempotency key.

## Evaluation

Evaluation scales/waits for all six deployments, injects workload/faults,
captures evidence, and finalizes cleanup. Service restart logic remains in
Evaluation. Evaluation also owns its runner Secret, Ansible role/playbook, and
deploy script. MCPTools owns the network-probe DaemonSets; Infrastructure owns
only the prerequisite cluster platform and namespaces.
