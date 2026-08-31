# Collection-Driven Evaluation Architecture

The runner consumes scenario JSON from `collections/online-boutique-scenario`,
`collections/teastore-scenario`, or `collections/long-scenario`, complete Chaos Mesh
`Schedule` resources from `collections/chaos`, and application-owned deployment
and placement inputs from `applications/`. Online Boutique's Kustomize tree is
under `applications/online-boutique/kustomize`. TeaStore's ClusterIP tree is
under `applications/teastore/kustomize`. The runner never renders a
chaos resource or monitors recurrence children in Python.

The root runner establishes exclusive ownership of agent lifecycle before
prerun: it scales all agent-platform deployments to zero and verifies that no
replicas remain ready before truncating durable workflow state. This avoids
deadlocks with active workers left by a manual deployment or interrupted run.

## Collection contract

Scenario chaos references are exact YAML filename stems, and placement is an
exact profile-directory name:

```json
{
  "name": "real-node-delay-worker-3-one-hour",
  "placement": "canonical-six-node",
  "steps": [
    {
      "name": "01-worker-node-3-remote-location-chaos",
      "chaos": ["node-delay-worker-3", "node-delay-peers-to-worker-3"],
      "duration": 3600
    },
    {"name": "02-recovery", "chaos": [], "duration": 600}
  ]
}
```

Every YAML file is a single `chaos-mesh.org/v1alpha1` `Schedule` in the
`chaos-mesh` namespace. Collection validation requires `@every` cadence,
`historyLimit: 1`, `concurrencyPolicy: Forbid`, and a child duration shorter
than the interval.

The scenario's required `placement` value is an exact placement-directory name.
Each Online Boutique profile renders its full configuration and must cover all
11 application Deployments. Each Deployment retains `role: services`, has no
required node affinity, and adds exactly one soft
`kubernetes.io/hostname` topology-spread constraint with `maxSkew: 1` and
`ScheduleAnyway`.

The bundled `canonical-six-node` profile permits every service on all six nodes
labelled `role=services`. It controls distribution instead of node identity:

| Deployment | Baseline replicas | HPA min/max | Scheduling |
| --- | ---: | ---: | --- |
| frontend | 6 | 6 / 30 | soft spread across service nodes |
| all other application Deployments | 2 | 2 / 30 | soft spread across service nodes |

TeaStore's `canonical-six-node` overlay uses the same `role: services` spread
contract for seven Deployments. `teastore-webui` starts at three replicas with
HPA 3/3, `teastore-db` and `teastore-registry` stay at one replica without an
HPA, and the remaining services start at two replicas with HPA 2/30.
The web UI requests 1500m CPU and 2Gi memory, may burst to two CPU cores and
3Gi memory, and uses the lower HPA maximum to keep recovery within cluster
capacity. Across TeaStore, canonical requests use conventional rounded
quantities while keeping the existing limits as anchors.

The `role: services` selector defines eligibility. The spread rule asks the
scheduler to balance matching replicas across hostnames but deliberately does
not leave a pod Pending solely because perfect balance is unavailable.

The `cpu-constrained-six-node` profile inherits the complete canonical profile
and changes only application CPU limits. For all 11 Deployments, the rendered
CPU limit equals the existing request. This models a restrictive resource
policy with no burst headroom while retaining identical replicas, HPA targets,
node eligibility, and topology spreading. The email, checkout, and
product-catalog CPU-headroom scenarios use this profile and each expects one
scoped Deployment resource correction.

Pod-targeted chaos Schedules use an `app In (...)` expression and omit node
selectors. Resource-saturation scenarios follow every Running replica so
vertical or bounded horizontal scaling can be evaluated independently of soft
scheduler placement. The checkout capacity-loss scenario deliberately affects
one replica at a time so a bounded N+1 HPA policy can absorb the loss.

## Runtime flow

`ScenarioLoader` validates JSON against both the chaos and placement catalogs.
The selected profile is rendered once, validated, archived with its SHA-256
hash, and checked against the central Infrastructure Kustomize render. A mismatch
fails the testbed before chaos. `prerun/run.sh` already applied that default
Kustomization; no placement-manifest environment variable is needed.

`prerun/run.sh` wipes the live agent tables, deletes other catalog application
namespaces, and recreates the selected application namespace before the testbed
starts. The application reset phase then uncordons
every referenced node to clear persistent scheduling state left by an earlier
remediation. It logs every command and then verifies that each node exists, is
Ready and schedulable, carries the expected services and hostname labels, and
has no untolerated blocking taint. Labels and taints are never changed. After
waiting for rollouts, the phase verifies live spread constraints and Ready
pod placement. It records a canonical per-Deployment node-count map and
fingerprint before baseline collection.
Before capturing that baseline or starting Locust, the runner waits for the
selected application's profile-defined `startup_delay_seconds`. TeaStore uses a
180-second warm-up so its registry entries, persistence initialization, image
service, and recommender training can settle after Kubernetes reports the pods
Ready. Applications that omit the field start load immediately.
Agent/control comparison requires the same rendered placement SHA-256, not the
same observed pod-to-node fingerprint; the latter remains diagnostic evidence
because soft spreading permits multiple valid placements.

`postrun/run.sh` is a separate program from the testbed. After the experiment
exits, it exports `anomaly_event`, `rca_job` plus RCA tool calls,
`remediation_job`, remediator tool calls and artifacts, `learning_job` plus its
ordered `incident_lesson` rows, and `agent_workflow`
into `sessions/` under the run output directory.

For each non-idle step,
`ScheduledStepExecutor` removes stale copies, applies all referenced Schedules,
starts the deadline after the last successful apply, and background-deletes all
Schedules in reverse order so a terminating Schedule cannot continue launching
new recurrence children. Cleanup independently verifies both the Schedule and
all child experiments carrying its `managed-by` label are absent; a failure
prevents later steps from starting.

`cleanup_chaos_state.sh` is the authoritative whole-cluster cleanup. Bootstrap
runs it before every setup and finalization runs it after load generation stops,
including failed and interrupted experiments. It deletes all Chaos Mesh
Schedule, Workflow, and experiment CRs across namespaces, performs guarded
finalizer recovery, and connects to every configured worker from
`Infrastructure/ansible/inventory.ini` to remove and verify residual `netem` or `tbf`
traffic-control state and orphaned CPU stress processes. `run_single.sh` runs
the same cleanup after every scenario and aborts the batch if verification
fails. The runner pod also has a pre-stop cleanup hook and a 16-minute
termination grace period. PhysicalMachineChaos step cleanup repeats the host
check for its selected nodes after the Schedule is absent; pod-targeted
Schedules do the same for their `nodes` selector. SSH or verification failure
is treated as unsafe cleanup and prevents the application reset or next
scenario from starting.

The main dependency direction is:

```text
CLI -> bootstrap -> orchestration -> chaos execution -> Kubernetes client
            |            |                |-> catalog
            |-> placement render/validation
                         |-> evaluator    |-> artifacts
                         |-> domain
```

## Results

Metadata schema version 2 stores the normalized scenario, placement definition,
render hash, node preflight, observed placement and fingerprint, archived
Schedule definitions, content hashes, per-Schedule command results,
active-window timestamps, cleanup verification, metrics, and run status. Exact
inputs are copied to `inputs/scenario.json`, `inputs/chaos/`, and
`inputs/placement/`. Postrun adds `sessions/` JSON exports of anomaly, RCA,
remediation, and workflow rows.

`grader/` compares each succeeded `rca_job.result` and
`remediation_job.result` independently with the manually maintained
scenario-named Markdown ground truth and the exact manifests archived under
`inputs/chaos/`. `grader/rubric.json` supplies the criterion ids, class labels,
scores, and weights. The judge returns only classifications; Python converts
those classes into 0–1 scores and a weighted overall score. Alignment for the
metric gate is derived from the correctness criterion score. For remediation
only, scenario JSON arrays under `grader/penalties/` list harmful actions; the
judge marks which apply and Python subtracts those amounts from the overall
score, floored at 0. It does not read
requests, raw output, tool calls, reasoning, anomalies, or learning records.
For each completed remediation, it also reports
per-series and family medians for all 13 Prometheus files over the specified
five-minute before and after windows anchored at `completed_at`, applies the
configured 15% direction policy and core-health gate, and writes per-run JSON,
Markdown, judge checkpoints, a flat summary CSV, per-kind rubric score CSVs,
and an aggregate report under `grades/`. Missing archived inputs make only the
affected run `ungraded`.

`visualizer/` is another standalone, read-only reporting path. It reads every
Prometheus query-range family and normalizes timestamps from `metadata.json`
and the anomaly, RCA, remediation, and remediation-tool session exports. Each
run gets three distinct output folders: one line plot per metric, one aligned
metric-plus-timeline figure per metric, and the timeline alone. The timeline
folder also contains a CSV of the exact normalized events used in the plot.
Elapsed minute zero is `metadata.started_at`; a missing start falls back to the
earliest timestamp and is recorded as a warning. The visualizer performs no
semantic grading, service calls, or cluster operations.

Reporting supports version 2 only and groups agent/non-agent comparisons by
scenario, placement reference, observed placement fingerprint, step index, step
name, and the sorted set of chaos references. Runs with different observed
fingerprints remain in summaries but do not produce an agent/non-agent
comparison.

`--skip-reset` is intentionally unsupported: every run must apply and verify its
scenario-selected placement.

## Commands

```bash
./run.sh --loadgenerator burst \
  --scenario ./collections/online-boutique-scenario/01-node-delay-worker-3.json \
  --baseline-minutes 5 \
  --prometheus-url http://localhost:9090

./run_tc.sh ./collections/online-boutique-scenario
./run_tc.sh ./collections/teastore-scenario

./run_single.sh ./collections/long-scenario

./run_all.sh

./run.sh --loadgenerator daily \
  --scenario ./collections/long-scenario/01-multi-fault-one-day.json
```
