# Evaluation platform

## Goal

Evaluation measures the end-to-end effect of detection, RCA, and remediation
under repeatable Online Boutique workload and controlled faults. It captures raw
evidence for later analysis; it does not declare success solely because an agent
produced a remediation message.

## Inputs

### Workload

Locust load profiles are selected with `--loadgenerator`: currently constant,
burst, or sinus. The target defaults to a locally forwarded frontend but batch
runs normally use the in-cluster frontend service.

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
stem. Multiple references in one step begin together. Collections include pod,
node, network, and physical-machine failure modes. Exact available collections
should be discovered from the tree rather than hard-coded into automation.

The current scenario collections cover ad hoc work, canonical multi-step
scenarios, combined pod/node faults, multiple-pod and multiple-single faults,
node network faults, curated real-world scenarios, single-node scenarios, and
single-pod scenarios. `collections/chaos` is the common resource catalog used by
all of them.

## Safety model

- Full cluster/host chaos cleanup occurs before setup and in finalization.
- Application reset uncordons only placement-referenced nodes; it does not
  change labels, taints, tolerations, replica counts, or HPAs.
- Missing, NotReady, unschedulable, incorrectly labeled, or blocked nodes fail
  before namespace reset.
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
- `--postgres-dsn`: permits database cleanup during application reset.
- `--port-forward`: manages a frontend port-forward for local execution.
- `--output-dir`: stable artifact directory.

## Outputs and analysis

The run directory is the unit of evidence. Preserve its metadata, inputs,
commands, snapshots, metric data, and failure outputs together. Do not compare
runs by copying only charts or aggregate CSV rows.

The reporting pipeline accepts metadata schema version 2 and emits per-step
summaries plus paired agent/no-agent comparisons. The separate scenario
evaluator can call an OpenAI-compatible endpoint for qualitative analysis; this
is post-processing and is not part of experiment execution.

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
