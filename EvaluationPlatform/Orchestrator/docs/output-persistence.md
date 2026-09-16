# Agent output persistence

Generated answers and execution outcomes are separate facts. A model can produce
an answer even when parsing, tool execution, or recovery verification fails.

## Save sequence

1. RCA, Remediator, and LearningAgent send generated text to
   `POST /api/v1/internal/{service}/jobs/{job_id}/output` before parsing or verification.
2. Remediator also checkpoints its parsed result before checking verified recovery.
3. The worker finishes the job. Omitted output fields preserve their checkpointed
   values. A temporary checkpoint request failure includes the generated answer
   in the failure-completion request as a fallback.
4. A rejected lease/maintenance write (HTTP 409) does not fall back to an unchecked
   finish write. Lease reconciliation handles the abandoned job.
5. Runner's normal session export keeps `raw_output`, `result`, `status`, and
   `error` together, including on failed jobs.

Output checkpoints require the store token and a matching, unexpired running job
lease. They do not release the execution slot or assert that remediation worked.

## Autonomous outcomes

Unsuccessful or unverified remediation and expired remediation leases finish as
`failed`. Workflow reconciliation records failure, its error and completion time,
and releases the workflow from further reconciliation. No manual review decision
is required. The same ambiguous mutation is not blindly replayed; later detector
incidents can initiate a fresh investigation.

Old clients may still submit `needs_review` during rolling upgrades. Orchestrator
normalizes those requests to `failed` and reconciles old review workflows to a
terminal failure. Historical archive files retain their original contents.

## Validation

Unit tests cover output before parse/verification rejection, checkpoint-failure
fallback, stale-lease rejection, terminal workflow finalization, and preservation
of failed outputs through Runner's session exporter. Live validation uses synthetic
inputs and real deployed job services/model calls. Its exported files are kept
under `Runner/results/output-persistence-validation-20260915/`; these are software
validation evidence, not workload experiment measurements.
