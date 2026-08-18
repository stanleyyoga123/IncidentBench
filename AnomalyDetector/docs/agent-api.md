# AnomalyDetector API for Agents

This document is the agent-facing contract for inspecting and changing the
runtime parameters used by AnomalyDetector. It is written like an MCP tool
catalog: each HTTP operation has a stable tool name, input contract, output
contract, side effects, and failure behavior.

AnomalyDetector currently exposes HTTP/OpenAPI, not a native MCP server. An MCP
gateway can map each `operationId` below directly to a tool without changing
the semantics described here.

## Connection

Use the in-cluster address from workloads running in Kubernetes:

```text
http://anomaly-detector.agents.svc.cluster.local:8080
```

For local administration, forward the ClusterIP service and use localhost:

```bash
kubectl port-forward -n agents service/anomaly-detector 8080:8080
```

```text
http://127.0.0.1:8080
```

Interactive OpenAPI documentation is served at `/docs`, and the machine-
readable OpenAPI document is served at `/openapi.json`.

All request and response bodies use `application/json`.

## Authentication

Read operations do not require authentication. Mutation operations require:

```http
X-Detector-Profile-Token: <detector-profile-token>
```

The token is configured through `detector.profile_api_token` and supplied as
`DETECTOR_PROFILE_API_TOKEN` in the component-owned
`kubernetes/secret.example.yml`. Copy it to ignored `kubernetes/secret.yml` and
replace its `++++++++` placeholder locally before deployment.

Never put the token in prompts, logs, anomaly reasons, query parameters, or
committed configuration. Send it only as the request header. A mutation returns
`503` when the server has no configured token and `401` when the supplied token
is missing or incorrect.

## Agent operating rules

An agent changing a detector profile should use this sequence:

1. Call `get_anomaly_detector_health`. Stop if the service is unavailable or
   `mutations_enabled` is false.
2. Call `resolve_detector_profile` with the exact detector method, resource,
   name, and metric involved in the evaluated alert.
3. Inspect `mutable_parameters`, the current `parameters`, and `version`.
4. Prefer a scoped override for one workload or resource class. Do not modify a
   global default unless the evidence applies globally.
5. Make one bounded change at a time and provide an auditable `reason` that
   refers to evaluation evidence without embedding secrets.
6. Always send `expected_version` on updates and resets, even though the field
   is optional at the HTTP level.
7. On `409`, read the profile again and reconsider the change. Do not blindly
   replay a stale write.
8. Read the returned profile and optionally call `resolve_detector_profile` to
   verify that the intended scope now selects it.
9. Use `reset_detector_profile` to roll back. Do not attempt to reconstruct old
   defaults manually.

Changes affect the next detection cycle. They do not retroactively change
existing anomaly rows.

The current profile registry is `in_memory`. Every service restart discards
runtime changes and restores built-in defaults. Agents must not describe an
update as durable configuration.

## Profile resolution

For a metric series, AnomalyDetector selects the first active match:

1. exact `(method, resource, name, metric)`;
2. resource-wide `(method, resource, "*", metric)`;
3. global `(method, "*", "*", metric)`.

Typical resource values are `deployments` and `nodes`. For deployments, `name`
is the Kubernetes Deployment name. For nodes, it is the node name.

Creating an exact override for `deployments/checkout/http_5xx_rate` does not
change any other deployment. Creating an override with `name: "*"` changes all
matching resources that do not already have a more specific override.

## Tool catalog

| MCP-style tool name / OpenAPI `operationId` | HTTP operation | Mutates state |
| --- | --- | --- |
| `get_anomaly_detector_health` | `GET /health` | No |
| `list_detector_profiles` | `GET /api/v1/detector/profiles` | No |
| `resolve_detector_profile` | `GET /api/v1/detector/profiles/resolve` | No |
| `get_detector_profile` | `GET /api/v1/detector/profiles/{profile_id}` | No |
| `get_detector_profile_history` | `GET /api/v1/detector/profiles/{profile_id}/history` | No |
| `create_detector_profile_override` | `POST /api/v1/detector/profiles` | Yes |
| `update_detector_profile` | `PATCH /api/v1/detector/profiles/{profile_id}` | Yes |
| `reset_detector_profile` | `POST /api/v1/detector/profiles/{profile_id}/reset` | Yes |

## Shared response schema

Most operations return a `DetectorProfile`:

```json
{
  "id": "default-threshold-http-5xx-rate",
  "version": 1,
  "method": "threshold",
  "resource": "*",
  "name": "*",
  "metric": "http_5xx_rate",
  "parameters": {
    "threshold": 0.05,
    "direction": "high",
    "consecutive_anomalies_required": 3
  },
  "mutable_parameters": [
    "threshold",
    "n_tail",
    "consecutive_anomalies_required"
  ],
  "source": "default",
  "reason": "built-in detector defaults",
  "active": true,
  "created_at": "2026-08-17T05:00:00Z"
}
```

Field semantics:

| Field | Meaning |
| --- | --- |
| `id` | Stable identity. Built-in IDs are readable; scoped override IDs are UUIDs. |
| `version` | Monotonically increasing revision number for this ID. |
| `method` | `threshold` or `z_score`. |
| `resource` | Resource scope, normally `deployments`, `nodes`, or `*`. |
| `name` | Deployment/node name or `*`. |
| `metric` | Prometheus-derived detector metric. |
| `parameters` | Complete effective configuration passed to detector logic. |
| `mutable_parameters` | Only these keys may be supplied in a create/update request. |
| `source` | `default`, `operator`, or `reset`. |
| `reason` | Audit reason supplied for the latest revision. |
| `active` | Whether profile resolution may select this revision. |
| `created_at` | UTC timestamp for the revision. |

Do not infer mutability from the contents of `parameters`; use
`mutable_parameters` from the returned profile.

## `get_anomaly_detector_health`

Checks whether the API and background detection loop are healthy.

```http
GET /health
```

Example response:

```json
{
  "status": "ok",
  "detector_loop": "running",
  "profile_persistence": "in_memory",
  "active_profiles": 17,
  "mutations_enabled": true
}
```

Interpretation:

- HTTP `200` and `status: "ok"`: the process is ready.
- HTTP `503` and `status: "degraded"`: the background loop stopped; do not
  mutate profiles until the service is recovered.
- `mutations_enabled: false`: reads remain available, but mutations return
  `503`.

## `list_detector_profiles`

Lists every active global default and scoped override.

```http
GET /api/v1/detector/profiles
```

Response:

```json
{
  "persistence": "in_memory",
  "count": 17,
  "profiles": []
}
```

Use this operation for discovery and inventory. Do not attempt to determine the
effective profile for one workload by scanning this list; use
`resolve_detector_profile`, which applies precedence correctly.

## `resolve_detector_profile`

Returns the active profile that the next detection cycle would use for a metric
series.

```http
GET /api/v1/detector/profiles/resolve?method=threshold&resource=deployments&name=checkout&metric=http_5xx_rate
```

Inputs:

| Query parameter | Required | Allowed values |
| --- | --- | --- |
| `method` | Yes | `threshold`, `z_score` |
| `resource` | Yes | Exact runtime resource, usually `deployments` or `nodes` |
| `name` | Yes | Exact Deployment/node name |
| `metric` | Yes | A metric supported by the selected method |

Returns `200` with a `DetectorProfile`, or `404` if that detector method does
not support the metric and no matching profile exists.

Agents should call this operation immediately before a mutation so that the
profile ID and version are current.

## `get_detector_profile`

Gets the latest revision for a known profile ID.

```http
GET /api/v1/detector/profiles/{profile_id}
```

This operation can return an inactive scoped override after it has been reset.
Use `active` to distinguish that case. Returns `404` for an unknown ID.

## `get_detector_profile_history`

Returns all in-memory revisions for a profile, ordered oldest to newest.

```http
GET /api/v1/detector/profiles/{profile_id}/history
```

Response:

```json
{
  "persistence": "in_memory",
  "profile_id": "default-threshold-http-5xx-rate",
  "revisions": []
}
```

Use history to explain who/what changed the runtime profile and why. History is
lost on restart with the rest of the in-memory registry. Returns `404` for an
unknown ID.

## `create_detector_profile_override`

Creates a new exact or wildcard scoped override by inheriting the currently
resolved profile and replacing only the supplied mutable parameters.

```http
POST /api/v1/detector/profiles
X-Detector-Profile-Token: <detector-profile-token>
Content-Type: application/json
```

Request:

```json
{
  "method": "threshold",
  "resource": "deployments",
  "name": "checkout",
  "metric": "http_5xx_rate",
  "parameters": {
    "threshold": 0.08,
    "consecutive_anomalies_required": 4
  },
  "reason": "evaluation run eval-20260817-04 labelled repeated 5xx alerts false positive"
}
```

Returns `201` with the new version-1 `DetectorProfile`. Unspecified parameters
are inherited from the previously effective profile.

Do not use `resource: "*", name: "*"` to replace a built-in global profile;
that scope already exists and returns `409`. Update the returned built-in ID
only when a global change is truly intended.

Common failures:

- `401`: token missing or invalid.
- `409`: an active profile already exists at that exact scope.
- `422`: unsupported metric, empty change set, immutable key, unsafe value, or
  invalid reason.
- `503`: mutations are disabled because no server-side token is configured.

## `update_detector_profile`

Creates a new revision of an existing active profile. Scope, method, metric,
and profile ID cannot change.

```http
PATCH /api/v1/detector/profiles/{profile_id}
X-Detector-Profile-Token: <detector-profile-token>
Content-Type: application/json
```

Request:

```json
{
  "parameters": {
    "threshold": 0.08
  },
  "reason": "three reviewed alerts were normal retry traffic",
  "expected_version": 1
}
```

Returns `200` with the new revision. `parameters` is a partial update; the
response contains the complete effective parameter set.

`expected_version` is optional only for simple human administration. Agents
should always provide it. A stale value returns `409`, protecting against lost
updates from concurrent evaluators.

## `reset_detector_profile`

Rolls a profile back without requiring the caller to know old parameter values.

```http
POST /api/v1/detector/profiles/{profile_id}/reset
X-Detector-Profile-Token: <detector-profile-token>
Content-Type: application/json
```

Request:

```json
{
  "reason": "false-positive rate increased after evaluation run eval-20260817-04",
  "expected_version": 2
}
```

Reset behavior depends on scope:

- A global built-in profile receives a new active revision containing its
  original built-in parameters.
- A scoped override receives a new inactive revision. Subsequent resolution
  falls back to the next matching resource-wide or global profile.

Returns `200` with the reset revision, `404` if the ID is unknown/inactive, or
`409` if `expected_version` is stale.

## Mutable parameters and bounds

### Z-score profiles

| Parameter | Allowed value | Effect |
| --- | --- | --- |
| `threshold` | finite number, `2.5`–`8.0` | Required Z-score magnitude. Higher is less sensitive. |
| `lookback` | integer, `30`–`120` | Maximum baseline points. |
| `min_history` | integer, `30`–current `lookback` | Minimum baseline points before evaluation. |
| `n_tail` | integer, `1`–`10` | Number of latest points evaluated. |
| `consecutive_anomalies_required` | integer, `1`–`10`, not greater than `n_tail` | Persistence required before emission. |
| `min_absolute_delta` | finite number, at least `0` | Minimum change in the metric's native unit. |
| `min_relative_delta` | finite number, `0`–`5` | Minimum proportional change from baseline. |

Increasing `threshold`, magnitude guards, or persistence generally suppresses
noise but can delay or miss incidents. Increasing `lookback` smooths the
baseline but reacts more slowly to legitimate regime changes.

The API does not allow changes to semantic and stability parameters such as
`direction`, `epsilon`, `min_normalized_std_threshold`, or
`min_constant_fraction`.

### Threshold profiles

All threshold profiles allow:

| Parameter | Allowed value |
| --- | --- |
| `n_tail` | integer, `1`–`10` |
| `consecutive_anomalies_required` | integer, `1`–`10`, not greater than `n_tail` when `n_tail` is present |

Metric-specific threshold bounds:

| Metric | Allowed `threshold` |
| --- | --- |
| `deployment_cpu_request_utilization_percent` | `70.0`–`100.0` |
| `deployment_memory_request_utilization_percent` | `70.0`–`100.0` |
| `node_cpu_utilization_percent` | `70.0`–`100.0` |
| `node_memory_utilization_percent` | `70.0`–`100.0` |
| `response_time_p95_seconds` | `0.1`–`10.0` seconds |
| `http_5xx_rate` | `0.001`–`0.50` ratio |
| `app_instance_count` | Immutable; only persistence parameters may change |

`direction` is immutable. In particular, agents cannot change high-value
detectors into low-value detectors or suppress a zero-instance outage by
changing the replica-count threshold.

## Supported method/metric combinations

Threshold profiles exist for:

- `deployment_cpu_request_utilization_percent`
- `deployment_memory_request_utilization_percent`
- `response_time_p95_seconds`
- `http_5xx_rate`
- `app_instance_count`
- `node_cpu_utilization_percent`
- `node_memory_utilization_percent`

Z-score profiles exist for:

- `deployment_cpu_request_utilization_percent`
- `deployment_disk_io_bytes_per_second`
- `deployment_network_io_bytes_per_second`
- `deployment_cpu_usage`
- `app_instance_count`
- `traffic_rps`
- `response_time_p95_seconds`
- `http_5xx_rate`
- `node_cpu_utilization_percent`
- `node_network_io_bytes_per_second`

## Error contract

Errors use FastAPI's JSON shape:

```json
{
  "detail": "human-readable explanation"
}
```

| Status | Meaning | Agent action |
| --- | --- | --- |
| `401` | Invalid/missing mutation token | Stop; obtain credentials through the configured secret path. |
| `404` | Profile or method/metric match not found | Recheck method, scope, metric, and active state. |
| `409` | Existing scope or stale expected version | Re-read current state and reconsider; do not blind-retry. |
| `422` | Schema, bounds, mutability, or relational validation failed | Correct the proposal; do not widen bounds client-side. |
| `503` | Detector degraded or mutations disabled | Stop mutation workflow and escalate operationally. |

## Complete agent example

The following sequence creates and later removes a checkout-specific override:

```bash
BASE_URL=http://127.0.0.1:8080

curl -fsS "$BASE_URL/health"

curl -fsS \
  "$BASE_URL/api/v1/detector/profiles/resolve?method=threshold&resource=deployments&name=checkout&metric=http_5xx_rate"

curl -fsS -X POST "$BASE_URL/api/v1/detector/profiles" \
  -H 'Content-Type: application/json' \
  -H 'X-Detector-Profile-Token: <detector-profile-token>' \
  -d '{
    "method": "threshold",
    "resource": "deployments",
    "name": "checkout",
    "metric": "http_5xx_rate",
    "parameters": {"threshold": 0.08},
    "reason": "reviewed evaluation evidence identified repeated false positives"
  }'
```

Store the returned override `id` and `version`. To roll it back:

```bash
curl -fsS -X POST \
  "$BASE_URL/api/v1/detector/profiles/<profile-id>/reset" \
  -H 'Content-Type: application/json' \
  -H 'X-Detector-Profile-Token: <detector-profile-token>' \
  -d '{
    "reason": "rollback after evaluation",
    "expected_version": 1
  }'
```

## MCP adapter guidance

An HTTP-to-MCP adapter should expose one tool per OpenAPI `operationId` and
retain the input names exactly. It should:

- inject the mutation token from server-side secret configuration rather than
  accepting it as a model-generated tool argument;
- mark create, update, and reset tools as state-changing;
- return the HTTP status and JSON body without rewriting validation details;
- avoid automatic retries for `POST`/`PATCH`, especially after `409`;
- set short request timeouts because these endpoints do not wait for a detector
  cycle or external service;
- never expose the API beyond the intended trusted network boundary without
  adding stronger authentication and transport security.

The adapter must not turn anomaly evaluation into an automatic unbounded tuning
loop. Feedback collection, approval policy, experiment attribution, durable
storage, and rollback policy are separate control-plane responsibilities.
