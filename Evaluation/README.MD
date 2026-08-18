# Online Boutique Chaos Evaluation

Run scenario-driven evaluations using predefined Chaos Mesh Schedules.

Evaluation owns its runner deployment: `deploy.sh`,
`kubernetes/secret.example.yml`, and `kubernetes/pod.yaml`. Copy
the example to ignored `kubernetes/secret.yml` and replace the
required SSH and `POSTGRES_DSN` `++++++++` placeholders before running
`./deploy.sh`; replace all four optional S3 placeholders or leave all four
unchanged. The script uses kubectl's current context. Infrastructure must install
the platform and namespaces first, but does not install this runner.

```text
collections/
├── chaos/          # Complete Schedule YAML resources used by real-scenario
└── real-scenario/  # Relocatable, user-impacting production analogues
```

Every scenario must select a placement profile from
`../Infrastructure/kubernetes/online-boutique/kustomize/overlays/`. The runner
uncordons that profile's nodes,
renders and archives the overlay, verifies all referenced nodes after prerun
recreates Online Boutique, and verifies the live pod-to-node mapping before
baseline collection. Runs with different observed placement fingerprints are not
compared by reporting.

Each `./run.sh` scenario is `prerun/run.sh`, then `testbed/run.sh`, then
`postrun/run.sh`. Prerun wipes agent workflow tables and recreates
`online-boutique`. Postrun writes database sessions into
`results/<run-id>/sessions/` so later S3 sync includes them.

Run one scenario:

```bash
./run.sh --loadgenerator burst \
  --scenario ./collections/real-scenario/01-node-cpu-worker-1.json \
  --baseline-minutes 5 \
  --prometheus-url http://localhost:9090
```

Run the full agent/non-agent batch:

```bash
./run_tc.sh ./collections/real-scenario
```

Run the curated real-world suite once with agents and constant load:

```bash
./run_single.sh
```

The real-world suite is ordered with node-level incidents first, followed by
CPU-only pod incidents.

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
