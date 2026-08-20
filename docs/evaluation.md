# Evaluation platform

## Goal

Evaluation measures the end-to-end effect of detection, RCA, and remediation
under repeatable Online Boutique workload and controlled faults. It captures raw
evidence for later analysis; it does not declare success solely because an agent
produced a remediation message.

Evaluation independently owns `deploy.sh`, `kubernetes/secret.example.yml`, and
`kubernetes/pod.yaml`. Copy the example to ignored
`kubernetes/secret.yml` and replace the required SSH and `POSTGRES_DSN`
`++++++++` placeholders before deployment. Either replace all four optional S3
placeholders or leave all four unchanged; the deploy script then skips the S3
Secret. It uses kubectl's current context, while Infrastructure installs only
the prerequisite namespaces and platform tools.

## Inputs

### Workload

Locust load profiles are selected with `--loadgenerator`: currently constant,
burst, sinus, or daily. The `daily` profile follows coded 24-hour stages in
`testbed/loadgenerator/daily.py`; each stage's `percentage_users` is applied to
`DAILY_BASE_USERS`. The target defaults to a locally forwarded frontend but
batch runs normally use the in-cluster frontend service.

### Placement

Each scenario names an overlay under
`Infrastructure/kubernetes/online-boutique/kustomize/overlays`. The profile
must cover all 11 application Deployments, preserve `role=services`, and define
one non-empty required hostname-affinity expression per Deployment. Each
Deployment's eligible nodes must provide at least six aggregate CPU cores.

The runner renders the selected overlay and the default Kustomization and
requires identical SHA-256 output before mutating the cluster. It then verifies
actual Ready pod placement and records a fingerprint.

### Chaos

Scenarios refer to complete YAML files under `collections/chaos` by filename
stem. Multiple references in one step begin together. The catalog contains the
node CPU, delay, loss, and pod CPU Schedules used by
`collections/real-scenario`.

The primary scenario collection is `collections/real-scenario`: 16 one-hour
faults with a 10-minute recovery step, ordered as node delay/loss incidents
then CPU-only pod incidents. `collections/long-scenario` is one day aligned to
the `daily` load curve with a one-hour baseline: idle until 02:00, worker-3
isolation delay, worker-3 loss, productcatalog CPU on all replicas, then
worker-5 isolation delay. `collections/chaos` is the shared Schedule catalog.

## Safety model

- Full cluster/host chaos cleanup occurs before setup and in finalization.
- `prerun/run.sh` recreates `online-boutique` and wipes agent workflow tables.
- Application reset uncordons only placement-referenced nodes; it does not
  change labels, taints, tolerations, replica counts, or HPAs.
- Missing, NotReady, unschedulable, incorrectly labeled, or blocked nodes fail
  after prerun recreates the namespace and before baseline collection.
- Every Schedule must be absent before the next step.
- Host cleaner/audit failure is unsafe and aborts the run.
- Finalization runs on success, failure, exception, and interruption.
- The evaluation runner has powerful permissions and belongs only in an
  isolated research cluster.

## Run modes

One run can be agent-enabled or use `--skip-agents`. `run_tc.sh` performs both
modes for each JSON file in a selected directory and can sync completed or
failed artifacts to S3 when configured.

Example:

```bash
cd Evaluation
./run_tc.sh ./collections/real-scenario
```

Key options for one run:

- `--scenario`: required JSON path.
- `--loadgenerator`: required load profile.
- `--baseline-minutes`: baseline duration; otherwise `--duration` is used.
- `--grace-period`: delay after agent startup before chaos.
- `--skip-agents`: control run.
- `--prometheus-url`: explicit metrics endpoint.
- `--postgres-dsn`: prerun database wipe and postrun session export.
- `--port-forward`: manages a frontend port-forward for local execution.
- `--output-dir`: stable artifact directory.

`./run.sh` runs `prerun/run.sh`, then `testbed/run.sh`, then `postrun/run.sh`
for every scenario. `--help` and incomplete arguments skip prerun/postrun.

## Outputs and analysis

The run directory is the unit of evidence. Preserve its metadata, inputs,
commands, snapshots, metric data, `sessions/` database export, and failure
outputs together. Do not compare runs by copying only charts or aggregate CSV
rows.

The reporting pipeline accepts metadata schema version 2 and emits per-step
summaries plus paired agent/no-agent comparisons. Qualitative post-processing
is outside this component.

## Interpreting results

At minimum, assess:

- detection latency from chaos active time to anomaly row;
- investigation and remediation completion latency;
- precision of identified resource/cause against scenario ground truth;
- whether actions were necessary, bounded, and relevant;
- recovery in latency, error rate, throughput, saturation, and replicas;
- collateral impact and persistent cluster changes;
- cleanup success and run validity;
- difference from the matching no-agent control.

An experiment is invalid for causal comparison when cleanup failed, exact inputs
cannot be recovered, placement fingerprints differ, or the load/application
window is incomplete.
