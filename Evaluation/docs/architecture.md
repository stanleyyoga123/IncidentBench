# Collection-Driven Evaluation Architecture

The runner consumes scenario JSON from `collections/real-scenario`, complete
Chaos Mesh `Schedule` resources from `collections/chaos`, and pre-authored
Kustomize placement profiles from
`../../Infrastructure/kubernetes/online-boutique/kustomize/overlays`. It never
renders a chaos resource or monitors recurrence children in Python.

## Collection contract

Scenario chaos references are exact YAML filename stems, and placement is an
exact profile-directory name:

```json
{
  "name": "real-node-cpu-worker-1-one-hour",
  "placement": "canonical-six-node",
  "steps": [
    {
      "name": "01-worker-node-1-cpu-chaos",
      "chaos": ["node-cpu-worker-1"],
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
Each profile renders the full Online Boutique configuration and must cover all
11 application Deployments. Each Deployment retains `role: services` and adds
exactly one required `kubernetes.io/hostname` affinity expression. Profiles do
not change HPAs or replica counts.

The bundled `canonical-six-node` profile weights independently scaling services
by node capacity. Node 1 has 8 CPU/32 GiB; nodes 2, 3, and 6 have 4 CPU/16 GiB;
and nodes 4 and 5 have 2 CPU/8 GiB. It uses this map:

| Deployment | Allowed nodes |
| --- | --- |
| frontend | worker-node-1, worker-node-2 |
| adservice, cartservice, recommendationservice | worker-node-1 |
| checkoutservice, emailservice | worker-node-2, worker-node-4 |
| currencyservice, productcatalogservice, paymentservice | worker-node-3, worker-node-5 |
| redis-cart, shippingservice | worker-node-4, worker-node-6 |

Every Deployment's allowed-node set represents at least 6 CPU in aggregate.
The singleton node-1 assignments provide 8 CPU; all other assignments combine
a 4-CPU node with a 2-CPU node. The `role: services` node selector and required
hostname affinity are both present and are evaluated together by Kubernetes.

Pod-targeted chaos Schedules combine a node selector with an `app In (...)`
expression. Bootstrap derives the complete eligible service set for that node
from the rendered placement and rejects the collection if the expression is
missing, partial, duplicated, or contains an ineligible service.

## Runtime flow

`ScenarioLoader` validates JSON against both the chaos and placement catalogs.
The selected profile is rendered once, validated, archived with its SHA-256
hash, and checked against the central Infrastructure Kustomize render. A mismatch
fails the testbed before chaos. `prerun/run.sh` already applied that default
Kustomization; no placement-manifest environment variable is needed.

`prerun/run.sh` wipes the live agent tables and recreates `online-boutique`
before the testbed starts. The application reset phase then uncordons
every referenced node to clear persistent scheduling state left by an earlier
remediation. It logs every command and then verifies that each node exists, is
Ready and schedulable, carries the expected services and hostname labels, and
has no untolerated blocking taint. Labels and taints are never changed. After
waiting for rollouts, the phase verifies live Deployment constraints and Ready
pod placement. It records a canonical per-Deployment node-count map and
fingerprint before baseline collection.

`postrun/run.sh` is a separate program from the testbed. After the experiment
exits, it exports `anomaly_event`, `rca_job` plus RCA tool calls,
`remediation_job`, remediator tool calls and artifacts, `learning_job` plus its
ordered `incident_lesson` rows, and `agent_workflow`
into `sessions/` under the run output directory.

For each non-idle step,
`ScheduledStepExecutor` removes stale copies, applies all referenced Schedules,
starts the deadline after the last successful apply, and foreground-deletes all
Schedules in reverse order. Cleanup verifies every Schedule is absent and a
failure prevents later steps from starting.

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
remediation, and workflow rows. `analyzer/` reads those folders offline to
plot metrics (elapsed minutes, chaos start at 0), extract operational errors,
and score RCA/remediation sessions. Run-level scores credit the best injection
match; `--reuse-judge` rescores from existing `judge.json` without calling vLLM.

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
  --scenario ./collections/real-scenario/01-node-cpu-worker-1.json \
  --baseline-minutes 5 \
  --prometheus-url http://localhost:9090

./run_tc.sh ./collections/real-scenario
```
