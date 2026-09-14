# Kubernetes incident evaluation platform

Run reproducible load and chaos experiments against a replaceable incident-response solution. The bundled solution detects anomalies, performs RCA and guarded remediation, and learns evidence-linked lessons. Researchers can replace that solution through shell adapters while keeping the runner and grader.

```text
EvaluationPlatform/
  Initialization/          Cluster, nodes, platform tools, inventory
  Orchestrator/            Bundled solution HTTP interface and workflow state
    Database/              PostgreSQL deployment and Alembic migrations
  Runner/                  Applications, scenarios, load, chaos, hooks, capture
  Grader/                  Offline grading and visualization
Agents/                    Detector, RCA, remediation, learning, MCP tools
```

Start with [Runner configuration and extension interfaces](EvaluationPlatform/Runner/README.md), [initialization](EvaluationPlatform/Initialization/README.md), [evaluation API](EvaluationPlatform/Orchestrator/docs/evaluation-api.md), and [grading](EvaluationPlatform/Grader/README.md).

## Prepare a deployment

1. Copy `EvaluationPlatform/Initialization/ansible/inventory.example.ini` to ignored `inventory.ini`. Fill SSH addresses, users, and Chaosd endpoints for your nodes. Review `group_vars/all.yml` and `vault.example.yml`; see the initialization guide for cluster prerequisites, Ansible dependencies and playbook order.
2. Copy each deployed component's `kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`. Replace required `++++++++` values. Keep ingestion, control, job-store, service-submission, and the two MCP tokens distinct; matching peers must receive the same value for their shared token.
3. Copy `EvaluationPlatform/Runner/config/environment.example.json` to ignored `environment.json`. Set service endpoints, inventory path, and `node_ips` to the actual node InternalIPs. The documentation addresses in the example are not cluster addresses. Export the variable named by `control_token_env`, normally `ORCHESTRATOR_CONTROL_TOKEN`, with the Orchestrator's `AGENT_CONTROL_TOKEN` value. Do not put credentials in JSON.
4. Deploy in dependency order: Initialization prerequisites → Orchestrator/Database → both MCP profiles → LearningAgent, RCAAgent, RemediatorAgent → Orchestrator → AnomalyDetector → optional Runner pod. Each component retains its own `deploy.sh` (Runner uses `scripts/deploy.sh`); commands use the current Kubernetes context. Database migrations are a separate job, never application startup work.

For an existing deployment, stop the detector and job workers before deploying the new database migration and Orchestrator API. Migration `20260913_0005` adds evaluation ownership without clearing existing workflow data. The older legacy-table migration still requires its explicit reset flag when applicable. Do not set that flag merely to install this additive migration.

## Build component images

From the project root, build and push all eight component images, or select
individual components:

```bash
./build.sh
./build.sh rca-agent mcp-tools
./build.sh database-job runner
PLATFORM=linux/arm64 ./build.sh learning-agent
```

Run `./build.sh --help` for component names. Docker Buildx and registry login
with push access to the existing `stanleyyoga123/*:dev` repositories are required.
The default platform is `linux/amd64`; builds run sequentially and stop on the
first failure. Initialization and Grader have no component Docker images.

Individual scripts also work from the project root, for example
`./Agents/RCAAgent/build.sh` or
`./EvaluationPlatform/Runner/scripts/build.sh`. Each script resolves its own
build context; Runner uses the repository root. Building images does not deploy
them or run database migrations.

## Update all agent deployments

After platform prerequisites and database migrations are installed, run
`./deploy.sh` from the workspace root. It applies each component's current local
Kubernetes files in dependency order: MCPTools, LearningAgent, RCAAgent,
RemediatorAgent, Orchestrator, then AnomalyDetector. It restarts all seven
Deployments and waits for readiness so ConfigMap and Secret changes take effect.

Populate each component's ignored `kubernetes/secret.yml` first. The script uses
kubectl's current context; run it when evaluations and agent jobs are idle. It
stops on failure without rollback. It does not build images, deploy the Runner,
install infrastructure, or execute database migrations. Image tags come from
the manifests. For existing application namespace bindings, the MCPTools script
also accepts `APPLICATION_NAMESPACES="online-boutique teastore sock-shop"`.

## Scale down the agent platform

Run `./scale.sh` from the project root when evaluations and agent jobs are idle.
It sets replicas to zero for AnomalyDetector, Orchestrator, RCAAgent,
RemediatorAgent, LearningAgent, and both MCPTools deployments in namespace
`agents`, using kubectl's current context. It checks that all seven deployments
exist before scaling. Kubernetes terminates their pods asynchronously.

## Validate and run

Install `EvaluationPlatform/Runner/requirements.txt` in your Python environment, plus kubectl, Helm and SSH. From the Runner directory:

```bash
python -m testbed.main --scenario resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json \
  --environment config/environment.json --validate-only

python -m testbed.main --scenario resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json \
  --environment config/environment.json

python -m testbed.main --suite resources/suites/paired.json --environment config/environment.json
```

Validation reads configuration, catalogs and application sources, and checks local installer binaries. It does not contact or change the cluster. A real bundled run **clears all solution workflow and lesson data**, recreates application namespaces, scales configured deployments, and applies chaos. Use a dedicated evaluation cluster/deployment; runs are serial.

Standard scenarios use a 30-minute baseline; AnomalyDetector queries the latest
30 minutes at 30-second spacing. Explicit short test scenarios keep their own
baseline durations.

Constant-load scenarios target 200 concurrent users for TeaStore, 600 for
Online Boutique, and an initial 100 for Sock Shop, with an upward random bias
of up to 10% (20, 60, and 10 users respectively). These targets and bias values
are configured in each scenario's `load.parameters`.

Online Boutique's 23 standard scenario names use the `online-boutique-` prefix,
matching the application prefixes used by TeaStore and Sock Shop. Their JSON
file paths are unchanged; the grader also retains the historical `real-` names.

Run JSON owns experiment behavior. There are no load, timing, deployment, or agent-mode CLI overrides. Suite JSON describes repeated and paired experiments. Resolved scenarios, exact applied chaos YAML, placement fingerprints, metrics, lifecycle logs, and exported sessions remain in the output folder.

## Grade archived runs

Install `EvaluationPlatform/Grader/requirements.txt`, then from its directory:

```bash
./grade.sh --input ../Runner/results --output grades
PYTHONPATH=. python -m visualizer --input ../Runner/results --output visualizations
```

Configure the judge endpoint/model/token using the grader's documented CLI/environment interface. No database or live cluster access is needed for grading. Existing archived run formats remain supported.

If a run fails, consult `run-status.json`, `hooks.json`, and `hooks/`. Ownership remains held after unsafe cleanup or hook failures. Follow [interrupted-run recovery](EvaluationPlatform/Orchestrator/docs/evaluation-api.md#interrupted-run-recovery) before starting another run.
