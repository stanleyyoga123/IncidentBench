# Infrastructure

This directory is the only source of truth for cluster creation, node
preparation, platform tools, deployment manifests, Helm values, and runtime
configuration assembly. Application directories contain application code;
Evaluation retains only experiment-time restart and cleanup behavior.

## Layout

- `ansible/`: inventory, cluster/tool/node/application playbooks, and roles.
- `kubernetes/`: authored manifests for PostgreSQL, agents, and Online Boutique.
- `values/`: Prometheus, Grafana, Loki, Alloy, Jaeger, and tracing configuration.
- `compose/database.yml`: local PostgreSQL plus the Orchestrator migration.
- `generated/`: ignored kubeconfig and pinned SSH host keys produced by Ansible.
- `backups/`: ignored placeholder for externally managed restores; never used
  by automation or images.

## Prerequisites

The Ansible controller needs Python 3, SSH access to every inventory host,
Helm, and kubectl. Install the Python and collection dependencies in an
isolated environment:

```bash
cd Infrastructure/ansible
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
```

Update `inventory.ini` before targeting a different cluster. Copy
`vault.example.yml` to the ignored `vault.yml`, replace its placeholders, and
encrypt it with `ansible-vault encrypt vault.yml`. The required variables are
also documented in `group_vars/all.yml`; no secret values belong in the
inventory, manifests, or command line history.

## Provision a cluster

Create the restricted Evaluation cleaner key once:

```bash
ssh-keygen -t ed25519 -f "$HOME/.ssh/evaluation-chaos-cleaner" \
  -C evaluation-chaos-cleaner
```

Then run the complete, ordered deployment:

```bash
cd Infrastructure/ansible
ansible-playbook site.yml \
  --ask-vault-pass \
  -e @/absolute/path/to/secrets.vault.yml
```

`site.yml` performs these phases:

1. Install the k3s server and join tool/service nodes using the stable channel.
2. Fetch a generated kubeconfig and apply the `role=tools`/`role=services` labels.
3. Install Istio, Prometheus and detector rules, Loki, Alloy, Grafana, Jaeger,
   and Chaos Mesh.
4. Install pinned chaosd and the restricted host cleanup account on service nodes.
5. Provision PostgreSQL, run Alembic to `head`, deploy MCPTools, RCAAgent,
   RemediatorAgent, AgentOrchestrator, then AnomalyDetector, and create
   the Evaluation runner.

Run a single phase with a playbook under `playbooks/`. The platform and
application playbooks use `generated/kubeconfig.yaml` and do not contact a
cluster during syntax checks.

## Build images

Build component images from their component directories. The Evaluation image
must use the workspace root as its Docker build context because it embeds the
central Online Boutique manifests:

```bash
docker build -f Evaluation/Dockerfile -t <registry>/agent-evaluator:<tag> .
docker build -f Orchestrator/Dockerfile -t <registry>/database-orchestrator:<tag> Orchestrator
```

Set immutable image tags in `ansible/group_vars/all.yml` or in a release vars
file before a reproducible deployment.

## Runtime boundary

Evaluation's `services/restart.sh`, `cleanup_chaos_state.sh`, and
`check_chaos_state.sh` remain in Evaluation because they execute during an
experiment. They read deployment inputs from `INFRASTRUCTURE_ROOT` (the sibling
`Infrastructure` directory locally and `/infrastructure` in the runner image).

## Local database

From the workspace root:

```bash
docker compose --env-file Orchestrator/.env \
  -f Infrastructure/compose/database.yml up -d postgres
docker compose --env-file Orchestrator/.env \
  -f Infrastructure/compose/database.yml run --rm migration
```

Copy `Orchestrator/.env.example` to the ignored `.env` and replace every
placeholder before running these commands.

## Validation

```bash
cd Infrastructure/ansible
ansible-inventory --graph
ansible-playbook site.yml --syntax-check
kubectl kustomize ../kubernetes/online-boutique/kustomize >/dev/null
```

Syntax checks are safe and local. Do not run provisioning, chart upgrades,
namespace resets, or chaos cleanup against a live cluster as routine validation.
