# Runtime flows

## Detection and RCA

1. AnomalyDetector fetches the aligned Prometheus window and evaluates the
   active detector profiles.
2. It builds deterministic event IDs and submits one authenticated batch.
3. AgentOrchestrator commits all events before returning acknowledgement.
4. Only then does AnomalyDetector start per-series cooldown.
5. Every 60 seconds AgentOrchestrator claims up to the oldest 100 pending events
   from one namespace scope and creates one RCA job. Cluster-scoped events form
   their own batch.
6. RCAAgent acquires the global lease through AgentOrchestrator, gathers
   evidence through investigation MCPTools, persists a structured result and
   audits via the job-store APIs, then releases the lease.
7. A no-action result enters learning. A remediation plan enters
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
4. Success requires a live execution, explicit verified recovery, and subsequent
   Kubernetes and non-empty Prometheus evidence before entering learning. The
   model still assesses whether that evidence meets the approved success criteria.
   Stale, unnecessary, unsafe, or unverified plans stop for `needs_review` without
   forcing a mutation. A crash or ambiguous failure after execution
   begins becomes `needs_review`; only an explicit retry decision can proceed.

Failed RCA or reviewed remediation can be retried with a fresh versioned
idempotency key.

## Learning and future RCA context

1. After successful no-action RCA or verified remediation, AgentOrchestrator
   submits a canonical, hashed workflow snapshot to LearningAgent.
2. LearningAgent claims the shared global slot and returns zero or more
   evidence-linked atomic lessons. It has no MCP tools or database credentials.
3. AgentOrchestrator publishes valid lessons and completes the workflow. After
   three learning failures it completes without lessons and records the error.
4. For each new RCA workflow, AgentOrchestrator excludes lessons scoped to a
   different namespace, then ranks active lessons by exact workload/metric,
   metric/resource, metric, resource, then recency. It sends at
   most 40 lessons within 24,000 serialized characters.
5. RCAAgent places them in the user prompt as untrusted hypotheses and verifies
   them against current evidence.

## Evaluation

The Runner resolves JSON configuration, claims the bundled Orchestrator's evaluation
ownership and maintenance state, and invokes named pre-run shell hooks. The full
reset and post-run session export use authenticated Orchestrator APIs. Configured
worker deployments stop before reset and baseline; Orchestrator remains online.
After baseline, the integration starts workers and resumes dispatch. Finalization
stops workers, removes chaos and captures evidence before post-run exports.
Failures remain recorded and unsafe cleanup prevents subsequent runs. See the
[Runner interface](../EvaluationPlatform/Runner/README.md).
