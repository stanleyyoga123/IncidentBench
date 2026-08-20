This project evaluates the Anomaly Detection and Kubernetes RCA & Remediation
Agent against Online Boutique microservices.

The runner is collection-driven:

- `collections/chaos/` contains complete Chaos Mesh `Schedule` YAML files used
  by the real-scenario and long-scenario suites.
- `../Infrastructure/kubernetes/online-boutique/kustomize/overlays/` contains
  pre-authored Kustomize placement profiles.
- `collections/real-scenario/` contains JSON scenarios referencing YAML
  filename stems and one required placement profile.
- `collections/long-scenario/` contains one 24-hour multi-fault scenario.
- `chaos: []` represents an idle recovery step.
- Multiple references in one step are applied together.

Example commands:

```bash
./run.sh --loadgenerator constant --scenario ./collections/real-scenario/01-node-delay-worker-3.json --baseline-minutes 5 --prometheus-url http://localhost:9090
./run.sh --loadgenerator daily --scenario ./collections/long-scenario/01-multi-fault-one-day.json
```

Important modules:

- `prerun/run.sh` wipes current agent workflow tables and recreates
  `online-boutique` from the central Infrastructure Kustomize.
- `testbed/` is the experiment executor (formerly `src/`).
- `postrun/run.sh` dumps anomaly, RCA, remediation, learning, and workflow rows into
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
- `analyzer/` plots metrics (t=0 at first chaos), extracts operational errors,
  and scores RCA/remediation with an OpenAI judge plus Python rubrics.
- The evaluation-runner ServiceAccount, ClusterRoleBinding, and Pod in
  `kubernetes/pod.yaml`, placeholder `kubernetes/secret.yml`, and
  default-current-context `deploy.sh` stay here. Replace required `++++++++`
  placeholders before deployment. Cluster/platform installation, inventory,
  node preparation, and Online Boutique manifests belong in
  `../Infrastructure/` and are resolved through `INFRASTRUCTURE_ROOT`.

Scenario format:

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

Experiment flow:

Each scenario is `prerun/run.sh`, then `testbed/run.sh`, then
`postrun/run.sh`. `./run.sh` orchestrates those three programs.

1. Prerun truncates live agent tables (`anomaly_event`, `agent_workflow`,
   `rca_job`, `remediation_job`, `learning_job`, `incident_lesson`,
   `agent_tool_call`, `remediation_artifact`)
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
   remediation session, learning session with lessons, workflow) into the run
   output directory.

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

Analyze copied run folders (gitignored `results/`) after an experiment:

```bash
PYTHONPATH=. python -m analyzer --input results --output analysis
PYTHONPATH=. python -m analyzer --input results --output analysis --skip-judge
PYTHONPATH=. python -m analyzer --input results --output analysis --reuse-judge
```

`JUDGE_URL` defaults to the local vLLM OpenAI-compatible server
(`http://localhost:8000/v1`) and `JUDGE_MODEL` defaults to
`Qwen/Qwen3.6-35B-A3B`. Override with `--base-url`, `--model`, and `--token`.
The judge uses Chaos Mesh `chaos_definitions` as ground truth. An RCA session
that names the injected locus and fault is a true positive (`matched_injection=yes`
forces localization correct). Sessions that chase unrelated detector leads are
scored as false alarms instead of `not_applicable`. Run-level RCA and
remediation scores credit the best injection match rather than averaging every
false alarm. `--reuse-judge` rescores from `analysis/runs/*/judge.json` without
calling vLLM. Pass `--skip-judge` for plots and operational errors only.
