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
./run_all.sh
```

`run_all.sh` runs the complete real-scenario collection through `run_single.sh`
with constant load, followed by the long-scenario collection with daily load.
It stops if either batch fails. `run_single.sh` accepts an optional explicit
load-generator argument after the scenario folder.

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
- `grader/` judges only final RCA and
  remediation result objects against manually maintained Markdown plus exact
  archived chaos manifests, then compares all Prometheus families around each
  completed remediation. The LLM classifies each criterion from
  `grader/rubric.json`; Python converts those classes into 0–1 scores and a
  weighted overall score. Remediation may then subtract scenario penalties from
  `grader/penalties/<scenario>.json`.
- `visualizer/` is the read-only metrics and lifecycle timeline path. It writes
  separate metric-only, metric-with-timeline, and timeline-only folders using
  elapsed time from the archived run start. Timeline lanes cover chaos-active
  windows, anomalies, RCA/remediation boundaries, and check/live
  `remediator.run_ansible` calls.
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
`role: services`, contain no required node affinity, and define exactly one
soft `kubernetes.io/hostname` topology-spread constraint per Deployment with
`maxSkew: 1`, `whenUnsatisfiable: ScheduleAnyway`, and an app-specific label
selector. The canonical profile starts every Deployment at two replicas except
`frontend`, which starts at six. Matching HPA minima are 2 and 6, and every HPA
maximum is 30.
The runner explicitly uncordons referenced nodes to clear scheduling state left
by earlier remediation, but does not modify labels, taints, tolerations,
replica counts, or HPAs. After prerun recreates the namespace, a referenced
node that is absent, NotReady, unschedulable, incorrectly labelled, or blocked
by an untolerated taint fails the run before baseline collection.

Every pod-targeted chaos Schedule must have one non-empty, unique `app In (...)`
expression and must omit `selector.nodes`. Pod CPU experiments target every
Running replica of the selected service so they remain valid under soft
placement.

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

Grade copied run folders (gitignored `results/`) with the output-and-metrics
grader:

```bash
PYTHONPATH=. python -m grader --input results --output grades
```

The grader requires archived `inputs/scenario.json` and every referenced
`inputs/chaos/*.yaml`, and uses the matching manual file under
`grader/ground_truth/`. It reads only `rca_session.json` and
`remediation_run.json` final result fields for semantic grading. Criterion
ids, class labels, scores, and weights come from `grader/rubric.json`.
Remediation penalties come from `grader/penalties/`. See
`grader/README.md` for the 15% metric policies, core-health gate, judge cache,
artifact schemas, `rca_rubric_score.csv` / `remediation_rubric_score.csv`,
persistent `grades/grader.log`, and `--verbose` console mode.

Render run timelines without contacting the cluster or an LLM:

```bash
PYTHONPATH=. python -m visualizer --input results/result-3 --output visualizations
```

The input may be one run or a directory of runs. Use `--view` to render all
three plot groups or only one. See `visualizer/README.md` for output files.
