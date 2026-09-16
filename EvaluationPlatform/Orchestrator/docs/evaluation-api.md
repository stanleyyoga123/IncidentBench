# Evaluation control API

Orchestrator owns all workflow database access. Migrations and PostgreSQL deployment live in `../Database/`; the HTTP service never creates tables. Evaluation endpoints use the existing control bearer token (`AGENT_CONTROL_TOKEN`), separate from ingestion and job-store tokens.

| Method and path | Operation ID | Behavior |
| --- | --- | --- |
| GET `/api/v1/evaluation` | `get_evaluation_state` | Inspect owner, maintenance, reset status |
| POST `/api/v1/evaluation/acquire` | `evaluation_acquire` | Claim a run and enter maintenance; same-owner retry is idempotent |
| POST `/api/v1/evaluation/pause` | `evaluation_pause` | Enter maintenance and wait for active dispatch/store requests to leave |
| POST `/api/v1/evaluation/resume` | `evaluation_resume` | Leave maintenance after workers are ready |
| POST `/api/v1/evaluation/reset` | `evaluation_reset` | Full transactional reset once per owning run |
| GET `/api/v1/evaluation/export?run_id=ID` | `export_evaluation_sessions` | Read a consistent snapshot of the six session exports |
| POST `/api/v1/evaluation/release` | `evaluation_release` | Release owner while remaining in maintenance |

POST bodies are `{ "run_id": "unique-run-id" }`. Run IDs contain letters, digits, dots, underscores or hyphens, up to 128 characters. Authentication failures return 401, ownership/maintenance conflicts 409, and malformed input 422. State responses contain `id`, nullable `run_id`, `maintenance`, and `reset_done`.

The durable `evaluation_control` singleton is created by migration `20260913_0005`. PostgreSQL advisory transaction locks synchronize control transitions with dispatch and mutating API operations across processes. Running requests use nonblocking shared locks to avoid nested HTTP submission deadlocks when maintenance is waiting. During maintenance, ingestion, job creation, claims and other non-evaluation POST routes return 409; scheduler loops do not dispatch. Existing GET APIs and health stay available.

The reset caller must first pause and confirm workers have stopped. The bundled shell integration waits until deployment selectors have no pods, including terminating pods. Orchestrator does not have Kubernetes credentials and cannot independently prove worker shutdown. Only trusted control-token holders should invoke reset. The transaction clears workflow/job/audit/artifact/lesson tables and recreates the empty execution-slot singleton. It leaves ownership and maintenance intact. Repeating reset for the same acquired run does not erase later data again.

Export requires the owning run in maintenance, uses a repeatable-read transaction, and contacts no agent services. Its envelope is `{ "schema_version": 1, "run_id": "...", "sessions": { ... } }`, with keys `anomaly`, `rca_session`, `remediation_run`, `remediation_session`, `learning_session`, and `workflow`. Arrays preserve the existing SQL export shapes, nested audits/artifacts/lessons, and deterministic ordering. Runner writes each array as `sessions/<key>.json`.

## Interrupted-run recovery

A process restart does not clear ownership or maintenance. Failed cleanup/export leaves ownership held. There is no timeout that silently hands a possibly unsafe deployment to another run.

1. Stop the failed runner process and inspect its `run-status.json`, `hooks.json`, logs, and `run-context.json`. Inspect GET `/api/v1/evaluation` using the control token; confirm its owner matches the archived run ID.
2. From Runner, rerun the bundled `stop` action with that context and output directory. It pauses dispatch and waits for workers to stop. If ownership acquisition timed out, use the run ID in the context to inspect ownership before doing anything else.
3. Run the documented authoritative `scripts/cleanup_chaos_state.sh --yes` from the Runner directory against the confirmed evaluation cluster; verify cleanup succeeds. Inspect captured application placement/state before a new evaluation.
4. Rerun `hooks/postrun/export-sessions/run.sh CONTEXT OUTPUT` from the Runner directory and any other failed post-run hooks. Preserve partial evidence even when jobs did not complete.
5. Invoke the bundled `release` action with the same context/output, or use Runner's `scripts/reset_evaluation_lock.sh --run-id INTERRUPTED_RUN_ID` with its configured environment and control token. The script checks ownership, pauses, and releases without deleting results. The next run receives a new ID, resets all data in its pre-run hook, and resumes after baseline.

Recovery commands intentionally require an operator decision and confirmed target. Do not resume old remediation jobs or reset away partial evidence as an automatic retry.
