# Anomaly Detector

This service detects Kubernetes deployment and node anomalies from Prometheus
time series and commits anomaly records to AgentOrchestrator over HTTP. Detection is based only on
observed Prometheus data; no external forecasting service is required.

The service does not create its database table. Apply the shared Alembic
migrations in `../Orchestrator` before starting the detector.

## Data flow

Prometheus recording rules precompute the deployment and node aggregations every
30 seconds. Each detector cycle requests one aligned 65-minute range from the
Prometheus HTTP API, converts the response to `MetricSeries`, runs every monitor
against the same snapshot, and then discards the samples. The application does
not maintain a local metric store or perform a startup backfill.

## Prometheus recording rules

Validate the plain rule file:

```bash
promtool check rules ../Infrastructure/values/prometheus/recording-rules.yml
```

Install or upgrade the `prometheus-community/prometheus` release with the
provided values override:

```bash
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --reuse-values \
  -f ../Infrastructure/values/prometheus/recording-rules.values.yaml
```

Verify that the rules are loaded:

```bash
curl -fsS 'http://localhost:9090/api/v1/rules?type=record'
```

Deploy the rules before the detector. Missing required rules are treated as a
fatal configuration error.

## Configuration

Copy `.env.example` to `.env` and set the Prometheus endpoint plus the
AgentOrchestrator ingestion URL/token.
The default query window is 65 minutes at a 30-second step, providing 131
samples for the 120-point baseline and three-point detector tail.

Run continuously:

```bash
./run.sh
```

The process serves its health and detector-profile API on port `8080` while the
detection loop runs in the background.

## Runtime detector profiles

The first adaptability control surface is available under
`/api/v1/detector/profiles`. Profiles are versioned and resolved in this order:
exact resource/name, resource wildcard, then the built-in global default.

Other agents and MCP-style HTTP adapters should use the complete
[agent API contract](docs/agent-api.md). It documents stable tool names,
authentication, schemas, parameter bounds, error handling, and safe mutation
workflows.

- `GET /api/v1/detector/profiles` lists active profiles.
- `GET /api/v1/detector/profiles/resolve` shows the effective profile for a
  method/resource/name/metric tuple.
- `GET /api/v1/detector/profiles/{id}` and `.../{id}/history` expose the active
  revision and audit history.
- `POST /api/v1/detector/profiles` creates a scoped override.
- `PATCH /api/v1/detector/profiles/{id}` changes bounded mutable parameters.
- `POST /api/v1/detector/profiles/{id}/reset` restores a default or removes a
  scoped override.

Mutation requests require `X-Detector-Profile-Token` to match
`detector.profile_api_token`. Mutations return `503` when no token is
configured. Reads do not require the token because the Kubernetes Service is
ClusterIP-only by default.

Example:

```bash
curl -X PATCH http://localhost:8080/api/v1/detector/profiles/default-threshold-http-5xx-rate \
  -H 'Content-Type: application/json' \
  -H 'X-Detector-Profile-Token: replace-with-a-long-random-token' \
  -d '{"parameters":{"threshold":0.08},"reason":"labelled false positives","expected_version":1}'
```

Updates affect the next detection cycle. Every emitted anomaly includes the
profile ID, version, and effective parameters in its detail. This initial
registry is intentionally in-memory: restarts restore built-in defaults. A
future Orchestrator-backed registry can provide durability without changing the
API contract.

For a fresh database, run this first from the workspace root:

```bash
cd Orchestrator
orchestrator.ingestion_token='<token>' ./run.sh
```

Run a single query-and-detect cycle:

```bash
PYTHONPATH=src python check.py
```

See the [local documentation index](docs/README.md) and the workspace
[data contracts](../docs/data-contracts.md) for the detailed metric and
integration contracts.
