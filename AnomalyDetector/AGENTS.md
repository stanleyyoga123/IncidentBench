# AnomalyDetector Agent Guide

## Responsibility

AnomalyDetector is the detection plane for the workspace. It queries bounded
Prometheus recording-rule windows, evaluates threshold and Z-score monitors,
and submits confirmed detector signals to AgentOrchestrator over authenticated
HTTP. It never connects to PostgreSQL.

This repository does not own database DDL or cluster installation:

- Schema and Alembic migrations belong to `../Orchestrator/`.
- Kubernetes manifests, Prometheus rules, runtime Secret templates, and cluster
  installation belong to `../Infrastructure/`.
- Fault injection and service restart controls belong to `../Evaluation/`.

Read the workspace `../AGENTS.md` and `../docs/` before making cross-component
changes.

## Runtime Flow

1. `src/main.py` starts FastAPI/Uvicorn.
2. The API lifespan starts `DetectorManager.detect_forever()`.
3. `PrometheusSeriesProvider` fetches one aligned recent window for every
   required recording rule.
4. Threshold and Z-score monitors resolve the effective runtime profile for
   each metric series.
5. Anomalies receive deterministic event IDs and are submitted as one batch.
6. Cooldown starts only after the entire batch is acknowledged as committed or
   duplicate. Failed delivery remains eligible on the next cycle.

The service is stateless with respect to metric history. It fetches a fresh
window each cycle and does not perform startup backfill.

## Important Paths

- `src/api/`: health and versioned detector-profile endpoints.
- `src/adaptation/`: built-in profiles, bounded mutations, scope resolution,
  version history, and decision provenance.
- `src/manager/detector.py`: query/detect/deliver/acknowledge loop.
- `src/collector/metrics/`: Prometheus rule catalog and concurrent provider.
- `src/detector/monitor/`: profile-aware monitor dispatch.
- `src/detector/logic/`: pure threshold and Z-score algorithms.
- `src/controller/orchestrator.py`: bounded authenticated HTTP delivery.
- `src/schema/`: Pydantic transport and detection models.
- `tests/`: unit, provider, manager, profile, and API tests.
- `../Infrastructure/values/prometheus/recording-rules.*`: metric contract.
- `../Infrastructure/kubernetes/agents/anomaly-detector.yaml`: Deployment and
  ClusterIP Service.

## Adaptability Contract

Profiles resolve from most specific to least specific:

1. exact `method/resource/name/metric`;
2. resource-wide wildcard name;
3. built-in global wildcard.

Runtime profile mutations are versioned, require a reason, and use optional
optimistic concurrency through `expected_version`. Mutation endpoints require
`X-Detector-Profile-Token`; they are disabled when
`detector.profile_api_token` is empty. Reads are unauthenticated inside the
ClusterIP boundary.

Only parameters listed in a profile's `mutable_parameters` may change. Keep
safety bounds in `src/adaptation/profile.py`; do not let API clients change
metric direction or other detection semantics. Replica-count thresholds are
intentionally immutable so feedback cannot suppress a zero-instance outage.

The registry is currently in-memory. A restart restores built-in defaults.
Durable profile storage should be introduced through Orchestrator migrations
without breaking `/api/v1/detector/profiles` or removing provenance from
anomaly details.

## API

- `GET /health`
- `GET /api/v1/detector/profiles`
- `GET /api/v1/detector/profiles/resolve`
- `GET /api/v1/detector/profiles/{id}`
- `GET /api/v1/detector/profiles/{id}/history`
- `POST /api/v1/detector/profiles`
- `PATCH /api/v1/detector/profiles/{id}`
- `POST /api/v1/detector/profiles/{id}/reset`

The OpenAPI document is available at `/docs` while the service is running.
For agent callers, `docs/agent-api.md` is the authoritative operation catalog
and safe mutation workflow.

## Configuration

Settings use Pydantic's dotted nested environment names. Start from
`.env.example`. Required runtime integrations are Prometheus and
AgentOrchestrator.
The profile API listens on `detector.api_host` and `detector.api_port` (8080 by
default).

Run locally:

```bash
./run.sh
```

Do not run live-cluster or live-service commands unless the user explicitly
requests them and the target is known.

## Development Rules

- Keep detector logic pure and independently testable; API concerns belong in
  `src/api/`, and profile concerns belong in `src/adaptation/`.
- Preserve a shared profile registry across all monitors in one process.
- Resolve profiles at detection time so an update affects the next cycle.
- Record exact effective parameters on every emitted anomaly.
- Add bounds and tests for every newly mutable parameter.
- Treat missing required Prometheus recording rules as fatal configuration;
  transient HTTP or payload failures may skip a cycle.
- Do not recreate database tables, infrastructure manifests, or fault-install
  scripts in this repository.
- Preserve unrelated dirty worktree changes.

## Verification

After Python changes run:

```bash
PYTHONPATH=src pytest -q
python -m compileall -q src tests
```

After metric-contract changes also validate the Prometheus rules in
Infrastructure. After deployment configuration changes parse the Kubernetes
YAML and run the Infrastructure Ansible syntax check when its collections are
installed.
