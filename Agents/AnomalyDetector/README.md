# Anomaly Detector

This service detects Kubernetes deployment and node anomalies from Prometheus
time series and commits anomaly records to AgentOrchestrator over HTTP. Detection is based only on
observed Prometheus data; no external forecasting service is required.

The service does not create its database table. Apply the shared Alembic
migrations in `../../EvaluationPlatform/Orchestrator/Database` before starting the detector.

## Data flow

Prometheus recording rules precompute the deployment and node aggregations every
30 seconds. Each detector cycle requests one aligned 30-minute range from the
Prometheus HTTP API, converts the response to `MetricSeries`, runs every monitor
against the same snapshot, and then discards the samples. The application does
not maintain a local metric store or perform a startup backfill.

## Prometheus recording rules

Validate the plain rule file:

```bash
promtool check rules ../../EvaluationPlatform/Initialization/values/prometheus/recording-rules.yml
```

Install or upgrade the `prometheus-community/prometheus` release with the
provided values override:

```bash
helm upgrade --install prometheus prometheus-community/prometheus \
  --namespace monitoring \
  --reuse-values \
  -f ../../EvaluationPlatform/Initialization/values/prometheus/recording-rules.values.yaml
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
The default query window is 30 minutes at a 30-second step, providing 61
samples. Default Z-score profiles cap the lookback at 60 preceding points and
require at least 30; the three tail points use the available 58–60 preceding
samples. Custom profiles requiring more history need a larger query window.

Run continuously:

```bash
./run.sh
```

The process serves its health and detector-profile API on port `8080` while the
detection loop runs in the background.

The component owns `kubernetes/configmap.yaml`, `kubernetes/secret.example.yml`,
`kubernetes/manifest.yaml`, and `deploy.sh`. Copy the example Secret to ignored
`kubernetes/secret.yml`, replace every `++++++++`, then run `./deploy.sh`; the
script refuses placeholders and uses kubectl's current context. `AGENT_INGESTION_TOKEN` must exactly match the value
in AgentOrchestrator's Secret. Deploy only after AgentOrchestrator is healthy.

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
future AgentOrchestrator-backed registry can provide durability without changing the
API contract.

For a fresh database, run this first from the workspace root:

```bash
cd EvaluationPlatform/Orchestrator/Database
./run.sh
```

Run a single query-and-detect cycle:

```bash
PYTHONPATH=src python check.py
```

See the [local documentation index](docs/README.md) and the workspace
[data contracts](../../docs/data-contracts.md) for the detailed metric and
integration contracts.
