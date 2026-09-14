# Detector Documentation

## Z-score Detector

The production Z-score detector is implemented by `ZScoreLogic` in
`src/detector/logic/z_score.py` and configured by `ZScoreMonitor` in
`src/detector/monitor/z_score.py`.

It compares the newest metric samples against a rolling historical window. A
high Z-score alone is not enough to emit an anomaly; the point must also pass
direction, magnitude, near-constant-history, and persistence guards.

## Detection Flow

For each `MetricSeries`, `ZScoreLogic.predict()` evaluates the last `n_tail`
points.

For each evaluated point:

1. Select up to `lookback` prior values as history.
2. Skip the point if history has fewer than `min_history` values.
3. Compute `baseline_mean`, population `baseline_std`, `delta`, and `z_score`.
4. Suppress tiny movement in constant or almost-constant history.
5. Apply the configured direction guard: `both`, `high`, or `low`.
6. Apply `threshold`, `min_absolute_delta`, and `min_relative_delta`.
7. Emit only after `consecutive_anomalies_required` qualifying tail points.

## Tuning Parameters Explained

The detector has multiple gates because Z-score alone can be misleading. A
metric with a tiny standard deviation can produce a huge Z-score even when the
real movement is operationally irrelevant.

### `threshold`

The minimum absolute Z-score required before a point can be considered unusual.

Formula:

```text
z_score = (current_value - baseline_mean) / baseline_std
```

Example:

```text
baseline_mean = 100
baseline_std = 5
current_value = 130
z_score = (130 - 100) / 5 = 6
```

If `threshold = 5`, this point passes the Z-score gate.

### `min_absolute_delta`

The minimum raw movement required from the baseline mean.

Formula:

```text
absolute_delta = abs(current_value - baseline_mean)
```

Example for CPU utilization:

```text
baseline_mean = 50.0
current_value = 50.7
absolute_delta = 0.7
min_absolute_delta = 5.0
```

Even if the Z-score is high because history was very flat, this does not alert
because CPU only moved `0.7` percentage points.

A CPU value like this would pass:

```text
baseline_mean = 50.0
current_value = 58.0
absolute_delta = 8.0
min_absolute_delta = 5.0
```

Use `min_absolute_delta` when the metric has a meaningful unit:

```text
CPU request percent, deployment memory request saturation percent, node memory
utilization percent, response time seconds, 5xx rate, replica count
```

`deployment_memory_request_utilization_percent` is not a bounded 0-100 memory
capacity percentage. It is:

```text
container_memory_working_set_bytes / memory_request_bytes * 100
```

That means values above `100` are valid. For example, `180` means the
deployment is using about `180%` of its requested memory. In detector details,
this is described as memory request saturation so RCA and remediation agents do
not treat it like total node memory utilization.

### `min_relative_delta`

The minimum proportional movement required from the baseline mean.

Formula:

```text
relative_delta = abs(current_value - baseline_mean) / abs(baseline_mean)
```

Example for traffic:

```text
baseline_mean = 100 rps
current_value = 108 rps
relative_delta = 8 / 100 = 0.08
min_relative_delta = 0.10
```

This does not alert because traffic moved only `8%`.

This would pass:

```text
baseline_mean = 100 rps
current_value = 125 rps
relative_delta = 25 / 100 = 0.25
min_relative_delta = 0.10
```

Use `min_relative_delta` when the metric scale can vary a lot between services:

```text
traffic rps, disk io, network io, raw CPU usage
```

### Absolute vs Relative Delta

`min_absolute_delta` answers:

```text
Did the metric move by at least this raw amount?
```

`min_relative_delta` answers:

```text
Did the metric move by at least this percentage of its baseline?
```

If both are configured, both must pass.

Response time uses both:

```text
min_absolute_delta = 0.10
min_relative_delta = 0.50
```

That means latency must increase by at least `100ms` and at least `50%` from
baseline. This avoids alerting on tiny changes like `0.200s -> 0.230s`.

### `direction`

Controls whether the detector cares about high spikes, low drops, or both.

Values:

| Value | Meaning |
| --- | --- |
| `high` | Only values above baseline can alert. |
| `low` | Only values below baseline can alert. |
| `both` | Either direction can alert. |

Examples:

```text
response_time_p95_seconds -> high
deployment_cpu_request_utilization_percent -> high
traffic_rps -> both
app_instance_count -> both
```

Low response time is usually not a problem, so response time is high-only.

### `lookback`

The maximum number of prior points used as the baseline.

With 15-second samples:

```text
lookback = 120
120 points * 15 seconds = 30 minutes
```

The detector compares the newest values against this recent baseline.

### `min_history`

The minimum number of historical points required before scoring.

Example:

```text
min_history = 30
30 points * 15 seconds = 7.5 minutes
```

This avoids unstable alerts early in startup or when a metric has just appeared.

### `n_tail`

The number of newest points to evaluate.

Example:

```text
n_tail = 3
```

The detector checks the last 3 samples, not only the final sample.

### `consecutive_anomalies_required`

The number of consecutive tail points that must pass all gates before an anomaly
is emitted.

Example:

```text
n_tail = 3
consecutive_anomalies_required = 3
```

This suppresses a single spike. The detector only emits if all three newest
points are anomalous.

### Near-constant History Guards

The detector has three guards for flat history:

| Guard | Purpose |
| --- | --- |
| `epsilon` | Avoid division by zero when standard deviation is zero. |
| `min_constant_fraction` | Treat history as constant when one value dominates. |
| `min_normalized_std_threshold` | Treat history as almost constant when variation is tiny. |

These exist because stable-load data often has tiny variance. Without these
guards, a small harmless move can produce a very large Z-score.

## RCA-friendly Detection Detail

`Detection.detail` remains plain text for database compatibility, but it uses
stable `key = value` lines so RCA and remediation agents can parse it.

An anomaly detail includes:

```text
anomaly_type = z_score_point_anomaly
resource = deployments
name = frontend
metric = response_time_p95_seconds
timestamp = 32.0
current_value = 1.0
baseline_mean = 0.24333333333333335
baseline_std = 0.16265163865007803
delta_from_baseline = 0.7566666666666666
relative_delta_from_baseline = 3.1096
z_score = 4.65
z_score_threshold = 3
direction = high
observed_direction = increase
severity = high
lookback_points = 30
lookback_limit = 30
min_history_required = 30
tail_points_evaluated = 3
consecutive_anomalies = 3
consecutive_anomalies_required = 3
min_absolute_delta = 0.1
min_relative_delta = 0.5
latest_tail_values = 0.8, 0.9, 1.0
metric_semantics = request latency in seconds
interpretation = latency is above_baseline after persistence and magnitude guards
rca_hints = check correlated cpu, memory, pod restarts, dependency latency, error rate, and traffic changes
remediation_hints = consider scaling, rollback, dependency mitigation, or traffic shedding if user impact is confirmed
```

The important fields for agents are:

| Field | Use |
| --- | --- |
| `resource`, `name`, `metric` | Locate the affected service/node metric. |
| `timestamp` | Anchor RCA queries around the detection time. |
| `current_value`, `baseline_mean`, `baseline_std` | Compare current behavior with local baseline. |
| `delta_from_baseline`, `relative_delta_from_baseline`, `z_score` | Quantify anomaly magnitude. |
| `direction`, `observed_direction` | Explain whether the metric increased or decreased. |
| `severity` | Rough priority derived from Z-score magnitude. |
| `latest_tail_values` | Show the persisted tail that triggered the anomaly. |
| `metric_semantics` | Explain the unit and meaning of the metric for RCA/remediation agents. |
| `interpretation` | Human-readable detector conclusion. |
| `rca_hints` | Suggested signals to inspect next. |
| `remediation_hints` | Candidate mitigation actions to consider after impact confirmation. |

## Production Metric Configuration

`ZScoreMonitor` configures one `ZScoreLogic` per metric name. Shared defaults:

```text
threshold = 4
lookback = 60
min_history = 30
n_tail = 3
consecutive_anomalies_required = 3
```

Metric-specific guards:

| Metric group | Direction | Movement guard |
| --- | --- | --- |
| CPU utilization percent | high | `min_absolute_delta = 5.0` |
| Deployment memory request saturation percent | high | `min_absolute_delta = 2.0` |
| Node memory utilization percent | high | `min_absolute_delta = 2.0` |
| Response time p95 | high | `min_absolute_delta = 0.10`, `min_relative_delta = 0.50` |
| HTTP 5xx rate | high | `min_absolute_delta = 0.01` |
| Instance count | both | `min_absolute_delta = 1.0` |
| Traffic RPS | both | `min_relative_delta = 0.10` |
| Disk IO | both | `min_relative_delta = 0.10` |
| Network IO | both | `min_relative_delta = 0.10` |
| Deployment CPU usage | high | `min_relative_delta = 0.10` |

## Cooldown

Cooldown is scoped by `series.metadata.key`:

```text
resource:name:metric
```

One metric entering cooldown does not suppress other metrics, services, or
nodes.

## Verification

Run focused tests:

```bash
PYTHONPATH=src python -m unittest tests.test_z_score
```

Run compile checks:

```bash
python -m py_compile src/detector/logic/z_score.py src/detector/monitor/z_score.py
python -m compileall src
```
