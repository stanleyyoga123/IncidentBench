# Evaluation platform

## Goal

Evaluation measures the end-to-end effect of detection, RCA, and remediation
under repeatable application workloads and controlled faults. Online Boutique
and TeaStore are the supported systems. Evaluation captures raw
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

Locust traffic shapes are selected with `--loadgenerator`: currently constant,
burst, sinus, or daily. Application profiles independently select the Locust
user behavior, so a new application does not duplicate the traffic curves. The
`daily` profile follows coded 24-hour stages in
`testbed/loadgenerator/daily.py`; each stage's `percentage_users` is applied to
`DAILY_BASE_USERS`. Endpoint service, port, and user journey come from the
selected application profile; batch runs normally use its in-cluster service.

### Placement

Each scenario contains an `application` and a `placement`. Online Boutique
placements are Kustomize overlays under
`applications/online-boutique/kustomize`. TeaStore placements are ClusterIP
Kustomize overlays under `applications/teastore/kustomize`. The Online Boutique profile
must cover all 11 application Deployments, preserve `role=services`, and define
one soft hostname topology-spread constraint per Deployment. Required hostname
affinity is forbidden. The canonical profile uses `maxSkew: 1` and
`ScheduleAnyway`, starts every service at two replicas except `frontend` at
six, and configures matching HPA minima with a maximum of 30. TeaStore uses
the same scheduling contract for seven Deployments: `teastore-webui` starts at
six replicas, `teastore-db` at one, and the remaining services at two.

The runner archives the selected definition and exact rendered or live workload
manifest, then verifies Ready pod placement and records a fingerprint.

### Chaos

Scenarios refer to complete YAML files under `collections/chaos` by filename
stem. Multiple references in one step begin together. The catalog contains the
node CPU, delay, loss, and pod CPU Schedules used by
`collections/online-boutique-scenario` and `collections/teastore-scenario`.

Each application collection contains 23 one-hour faults with a 10-minute
recovery step: node delay/loss/CPU/memory incidents plus service-wide CPU,
memory, bandwidth, capacity-loss, and CPU-headroom pod incidents. Pod selectors
intentionally omit node names and target every Running replica of the selected
service, except capacity-loss cases which fail one replica per recurrence.
`collections/long-scenario` is one day aligned to
the `daily` load curve with a one-hour baseline: idle until 02:00, worker-3
isolation delay, worker-3 loss, productcatalog CPU on all replicas, then
worker-5 isolation delay. `collections/chaos` is the shared Schedule catalog.

## Safety model

- Full cluster/host chaos cleanup occurs before setup and in finalization.
- `prerun/run.sh` validates the selected application source before mutation,
  deletes other catalog application namespaces, recreates the selected
  namespace through the application installer, and wipes agent workflow
  tables. It reapplies MCPTools' namespace-scoped remediation RoleBinding
  after recreating the namespace. Sibling applications must not remain on
  service nodes; their CPU requests would make canonical TeaStore or Online
  Boutique rollouts unschedulable.
- Application reset uncordons only placement-referenced nodes; it does not
  change labels, taints, or tolerations. Prerun namespace recreation reapplies
  the canonical replica counts and HPAs.
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
./run_tc.sh ./collections/online-boutique-scenario
./run_all.sh
```

`run_all.sh` runs the Online Boutique collection, then the TeaStore collection,
once with agents and constant load, then runs each long scenario once with
agents and the daily load generator. It uses
the same cleanup, result upload, baseline, and inter-run settings as
`run_single.sh`, and stops before the next batch if a failure is reported.

Key options for one run:

- `--scenario`: required JSON path.
- `--loadgenerator`: required load profile.
- `--baseline-minutes`: baseline duration; otherwise `--duration` is used.
- `--grace-period`: delay after agent startup before chaos.
- `--skip-agents`: control run.
- `--prometheus-url`: explicit metrics endpoint.
- `--postgres-dsn`: prerun database wipe and postrun session export.
- `--port-forward`: manages the selected application's configured service port-forward.
- `--output-dir`: stable artifact directory.

`./run.sh` runs `prerun/run.sh`, then `testbed/run.sh`, then `postrun/run.sh`
for every scenario. `--help` and incomplete arguments skip prerun/postrun.

## Outputs and analysis

The run directory is the unit of evidence. Preserve its metadata, inputs,
commands, snapshots, metric data, `sessions/` database export, and failure
outputs together. Do not compare runs by copying only charts or aggregate CSV
rows.

The reporting pipeline accepts metadata schema version 2 and emits per-step
summaries plus paired agent/no-agent comparisons. Application id is part of the
pairing key, so runs from different microservice systems cannot be compared as a
pair. Qualitative post-processing is outside this component.

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
cannot be recovered, canonical placement-definition fingerprints differ,
baseline invariants fail, or the load/application window is incomplete. Exact
observed pod-to-node fingerprints remain diagnostic evidence and may differ
under soft topology spreading.
