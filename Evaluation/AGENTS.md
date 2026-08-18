This project evaluates the Anomaly Detection and Kubernetes RCA & Remediation
Agent against Online Boutique microservices.

The runner is collection-driven:

- `collections/chaos/` contains complete Chaos Mesh `Schedule` YAML files used
  by the real-scenario suite.
- `../Infrastructure/kubernetes/online-boutique/kustomize/overlays/` contains
  pre-authored Kustomize placement profiles.
- `collections/real-scenario/` contains JSON scenarios referencing YAML
  filename stems and one required placement profile.
- `chaos: []` represents an idle recovery step.
- Multiple references in one step are applied together.

Example commands:

```bash
./run.sh --loadgenerator constant --scenario ./collections/real-scenario/01-node-cpu-worker-1.json --baseline-minutes 5 --prometheus-url http://localhost:9090
./run.sh --loadgenerator burst --scenario ./collections/real-scenario/10-pod-cartservice-cpu-all.json --duration 300
./run_tc.sh ./collections/real-scenario
```

Important modules:

- `prerun/run.sh` wipes current agent workflow tables and recreates
  `online-boutique` from the central Infrastructure Kustomize.
- `testbed/` is the experiment executor (formerly `src/`).
- `postrun/run.sh` dumps anomaly, RCA, remediation, and workflow rows into
  the run `sessions/` folder for later S3 upload.
- `testbed/chaos/catalog/` parses and validates Schedule YAML collections.
- `testbed/scenarios/` parses collection-driven scenario JSON.
- `testbed/placement/` resolves, renders, and validates placement profiles.
- `testbed/chaos/execution/` applies all Schedules for a step and safely removes
  them afterward.
- `testbed/kubernetes/chaos_schedule_client.py` is the kubectl boundary for
  Schedule resources.
- `testbed/evaluator/` collects Kubernetes snapshots and Prometheus metrics.
- `testbed/reporting/` aggregates metadata schema version 2 runs.
- The evaluation-runner ServiceAccount, ClusterRoleBinding, and Pod in
  `kubernetes/pod.yaml`, placeholder `kubernetes/secret.yml`, and
  default-current-context `deploy.sh` stay here. Replace required `++++++++`
  placeholders before deployment. Cluster/platform installation, inventory,
  node preparation, and Online Boutique manifests belong in
  `../Infrastructure/` and are resolved through `INFRASTRUCTURE_ROOT`.

Scenario format:

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

Experiment flow:

Each scenario is `prerun/run.sh`, then `testbed/run.sh`, then
`postrun/run.sh`. `./run.sh` orchestrates those three programs.

1. Prerun truncates live agent tables (`anomaly_event`, `agent_workflow`,
   `rca_job`, `remediation_job`, `agent_tool_call`, `remediation_artifact`)
   and clears `agent_execution_slot`, then deletes and recreates
   `online-boutique` from the central Kustomize.
2. Testbed scales agent deployments down.
3. Testbed uncordons the selected placement nodes, preflights them, waits
   for rollouts, and verifies Ready pod placement.
4. Start Locust and collect a baseline.
5. Scale agents up unless `--skip-agents` is set.
6. Execute ordered scenario steps.
7. For a non-idle step, remove stale Schedules, apply all references, wait for
   the step duration, then foreground-delete and verify every Schedule.
8. Collect Prometheus `query_range` metrics using a 15-second step and 1-minute
   rate window.
9. Postrun writes `sessions/` JSON (anomaly, RCA session, remediation run,
   remediation session, workflow) into the run output directory.

Placement profiles must cover all 11 application Deployments, retain
`role: services`, and define one non-empty required
`kubernetes.io/hostname In (...)` affinity expression per Deployment. The
allowed nodes for every Deployment must provide at least 6 CPU in aggregate.
The runner explicitly uncordons referenced nodes to clear scheduling state left
by earlier remediation, but does not modify labels, taints, tolerations,
replica counts, or HPAs. After prerun recreates the namespace, a referenced
node that is absent, NotReady, unschedulable, incorrectly labelled, or blocked
by an untolerated taint fails the run before baseline collection.

Every pod-targeted chaos Schedule must have an `app In (...)` expression whose
values exactly equal all Deployments eligible for its selected node in the
scenario placement profile. Bootstrap rejects stale or partial selectors.

Schedule requirements:

- `apiVersion: chaos-mesh.org/v1alpha1`
- `kind: Schedule`
- namespace `chaos-mesh`
- fixed `@every` cadence
- `historyLimit: 1`
- `concurrencyPolicy: Forbid`
- child duration shorter than the cadence
- Schedule name no longer than 57 characters

The default application namespace is `online-boutique`; it affects metrics and
snapshots only. Chaos targets and namespaces are defined entirely by the YAML.
Every Schedule must be absent before the runner advances to the next step.
`--skip-reset` is not supported because placement must be applied and verified
for every run.
