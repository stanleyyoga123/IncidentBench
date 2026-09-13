# Multi-application Kubernetes Chaos Evaluation

Run scenario-driven evaluations against Online Boutique, TeaStore, or Sock Shop using
predefined Chaos Mesh Schedules. Each scenario selects an application profile;
the profile owns installation, runtime defaults, placement discovery, and its
Locust user journey.

For TeaStore, first follow [healthy baseline calibration](docs/healthy-baseline.md).
Its baseline now validates HTTP and semantic request failures before agents or
chaos start. Use at least ten baseline minutes; a dedicated no-chaos scenario
is available in `collections/baseline/01-teastore.json`.

Evaluation owns its runner deployment: `deploy.sh`,
`kubernetes/secret.example.yml`, and `kubernetes/pod.yaml`. Copy
the example to ignored `kubernetes/secret.yml` and replace the
required SSH and `POSTGRES_DSN` `++++++++` placeholders before running
`./deploy.sh`; replace all four optional S3 placeholders or leave all four
unchanged. The script uses kubectl's current context. Infrastructure must install
the shared platform namespaces and services first; Evaluation creates the
selected application namespace during prerun.

```text
collections/
├── chaos/                       # Complete Schedule YAML resources
├── online-boutique-scenario/    # Online Boutique node and service incidents
├── teastore-scenario/           # Matching TeaStore incidents
├── sock-shop-scenario/          # Ten-minute Sock Shop catalogue CPU incident
├── e2e-smoke/                   # Short smoke scenarios for both applications
└── long-scenario/               # One 24-hour multi-fault day
```

All application-owned definitions and deployment inputs live under
`applications/<application>/`. Online Boutique's complete Kustomize tree is
under `applications/online-boutique/kustomize`. TeaStore's ClusterIP Kustomize
tree is under `applications/teastore/kustomize`. Sock Shop's bounded-resource
Kustomize tree is under `applications/sock-shop/kustomize`.
The corresponding Locust journeys are `applications/online_boutique.py` and
`applications/teastore.py`, and `applications/sock_shop.py`;
`testbed/loadgenerator/` contains only reusable
traffic shapes and launch mechanics.
The runner archives the selected placement and verifies the live pod-to-node
mapping before baseline collection. Runs with different placement-definition
fingerprints are not compared. Infrastructure remains responsible only for
cluster, node, storage, and shared platform prerequisites.

The profile namespace is authoritative because chaos selectors and upstream
manifests also encode it. `--namespace` may repeat that value but cannot move an
application to a different namespace; `--host` remains available for alternate
ingress or port-forward targets.

Each `./run.sh` scenario is `prerun/run.sh`, then `testbed/run.sh`, then
`postrun/run.sh`. Prerun resolves the application, validates its source, wipes
agent workflow tables, deletes other catalog application namespaces, recreates
the selected namespace, and installs the scenario-selected placement. It writes
`application-install.json` into the run directory. Postrun writes database
sessions into `results/<run-id>/sessions/` so later S3 sync includes them.

Before prerun touches the workflow database, `run.sh` scales all seven agent
deployments to zero and waits until no replicas are ready. This also makes a
retry safe after an interrupted run and prevents worker transactions from
deadlocking the workflow-table reset. The testbed starts them again after the
agents-off baseline and scales them down during finalization.

Run one scenario:

```bash
./run.sh --loadgenerator burst \
  --scenario ./collections/online-boutique-scenario/01-node-delay-worker-3.json \
  --baseline-minutes 5 \
  --prometheus-url http://localhost:9090
```

Run the full agent/non-agent batch:

```bash
./run_tc.sh ./collections/online-boutique-scenario
```

Run the curated real-world suite once with agents and constant load:

```bash
./run_single.sh
```

The Online Boutique suite is ordered with node-level incidents first, followed
by service CPU, memory, bandwidth, capacity-loss, and CPU-headroom incidents.

Run the matching TeaStore suite:

```bash
./run_single.sh ./collections/teastore-scenario constant
```

Every service-scoped primary remediation is an ordinary Kubernetes mutation:
node cordon/drain, vertical resource sizing, or bounded HPA scaling. The suite
does not require restart, rollback, or image version changes as solutions.
The CPU-headroom cases use the `cpu-constrained-six-node` overlay, which
preserves canonical placement while setting every application CPU limit equal
to its request. Each scenario right-sizes only its affected Deployment's CPU
request and limit.

TeaStore's web UI baseline uses six replicas with HPA 6–30. Each replica
requests 500m CPU and 1Gi memory, with limits of 1000m CPU and 2Gi memory.
Persistence uses the same CPU size; image requests 750m; auth and
recommender request 250m; registry and MySQL request 250m CPU and 512Mi
memory. Canonical TeaStore requests stay below their limits so the six-node
service pool can schedule the full placement.

Run a short TeaStore smoke:

```bash
./run.sh --loadgenerator constant \
  --scenario ./collections/e2e-smoke/03-teastore-auth-cpu.json \
  --baseline-minutes 5
```

Run the ten-minute Sock Shop catalogue CPU scenario after a six-minute
baseline (installation and the 60-second warm-up are additional setup time):

```bash
./run.sh --loadgenerator constant \
  --scenario ./collections/sock-shop-scenario/01-pod-catalogue-cpu-all-ten-minutes.json \
  --baseline-minutes 6
```

Run the 24-hour compounding-incident day with the daily traffic curve:

```bash
./run.sh --loadgenerator daily --scenario ./collections/long-scenario/01-multi-fault-one-day.json --baseline-minutes 60
```

Times in that scenario are on the daily load clock (locust start = 00:00). A
60-minute baseline therefore idles until 01:00; the first chaos window is
02:00–04:00.

Traffic shapes and application behavior are separate. The reusable shapes are
`constant`, `burst`, `sinus`, and `daily`; Online Boutique, TeaStore, and Sock
Shop user journeys live under `applications/`. Edit the stage table
in `testbed/loadgenerator/daily.py`. Each stage's
`percentage_users` is a percent of `DAILY_BASE_USERS` (or `DAILY_BASE_USER`);
20 with a base of 600 is 120 users.

To upload every completed run directory to Amazon S3, install and authenticate
the AWS CLI, then set `S3_RESULTS_URI` in `.env` (or export it in the shell):

```bash
S3_RESULTS_URI=s3://my-evaluation-bucket/online-boutique-results
AWS_PROFILE=my-profile
```

When running inside the evaluation-runner pod, provide credentials through the
component-owned placeholder Secret. For a one-off environment, create the
optional Secret directly without writing credentials to disk:

```bash
kubectl -n agents create secret generic evaluation-runner-s3 \
  --from-literal=AWS_ACCESS_KEY_ID='<access-key-id>' \
  --from-literal=AWS_SECRET_ACCESS_KEY='<secret-access-key>' \
  --from-literal=AWS_DEFAULT_REGION='ap-southeast-2' \
  --from-literal=S3_RESULTS_URI='s3://my-evaluation-bucket/online-boutique-results'
```

Use an IAM principal restricted to writing and listing objects under this
bucket prefix. Recreate the runner pod after creating or updating the Secret.

`run_tc.sh` uploads both successful and failed-run artifacts with `aws s3 sync`.
Credentials are resolved by the standard AWS CLI credential chain and must not
be committed to this repository. When `S3_RESULTS_URI` is unset, runs remain
local only.

Before running from the evaluation-runner pod, provision its restricted
worker-node SSH cleaner and the required `evaluation-runner-ssh` Secret by
following
[Infrastructure node preparation](../Infrastructure/ansible/NODE_PREPARATION.md).
Startup is
fail-closed when any worker cannot be audited or still contains host-level
network or CPU chaos.

To force a cluster-wide cleanup from the evaluation-runner pod:

```bash
./cleanup_chaos_state.sh --yes
```

To inspect cluster metadata and real worker-node qdisc/stress state without
changing anything:

```bash
./check_chaos_state.sh
```

The report is grouped into `Cluster` and one `Worker node N` section per
inventory host. It identifies stale terminating metadata, active impairment,
residual pass-through qdiscs, and active host state with no matching metadata.
It is intended to run locally and defaults to
`~/.ssh/evaluation-chaos-cleaner` plus
`../Infrastructure/generated/evaluation-runner-known_hosts`. Pod-mounted credential paths
remain an automatic fallback.

This deletes all Schedule, Workflow, and experiment custom resources, safely
releases recovered terminating records, and runs the restricted host cleaner
twice across every inventory worker. The normal runner invokes the same script
before setup and during finalization; `run_single.sh` also invokes it after
every scenario and aborts the remaining batch if the final verification fails.

See [docs/architecture.md](docs/architecture.md) for collection validation,
execution, cleanup, metadata, and reporting behavior.
See [docs/result.md](docs/result.md) for the complete run artifact layout,
extracted metric families and units, derived calculations, grading outputs,
and result-validity checks.

Grade local run artifacts (default `results/`):

```bash
PYTHONPATH=. python -m grader --input results --output grades
```

The grader uses the manually maintained scenario answer keys in
[`grader/ground_truth/`](grader/ground_truth/) and the exact Chaos Mesh
manifests archived with each run. It grades final RCA and remediation results,
applies the configured rubric and remediation penalties, and compares only
the five-minute response-time P95 and HTTP 5xx-rate windows around completed
remediation jobs. Other collected metric families are not graded. See
[`grader/README.md`](grader/README.md) for judge configuration, scoring rules,
cache behavior, and generated artifacts.

Visualize metrics and lifecycle events without contacting the cluster or an
LLM:

```bash
PYTHONPATH=. python -m visualizer --input results/result-3 --output visualizations
```

The visualizer produces separate metric-only, metric-with-timeline, and
timeline-only folders. See [`visualizer/README.md`](visualizer/README.md) for
configuration and output details.
