# Initialization

This directory owns cluster creation, node preparation, platform namespaces
and tools, and Helm values. It does not install PostgreSQL, migrations, agent
services, application Secrets, or the Evaluation runner. Those resources and
their default-current-context deploy scripts live with their components.

## Layout

- `ansible/`: inventory plus cluster, platform, and node-preparation playbooks.
- `values/`: Prometheus, Grafana, Loki, Alloy, Jaeger, and tracing configuration.
- `generated/`: ignored kubeconfig and pinned SSH host keys produced by Ansible.
- `backups/`: ignored placeholder for externally managed restores; never used
  by automation or images.

## Prerequisites

The Ansible controller needs Python 3, SSH access to every inventory host,
Helm, and kubectl. Install the Python and collection dependencies in an
isolated environment:

```bash
cd EvaluationPlatform/Initialization/ansible
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
```

Copy `inventory.example.ini` to ignored `inventory.ini`, then fill every node address and SSH user before targeting a cluster. The optional
encrypted `vault.yml` now contains only the chaos-cleaner public-key path:

```bash
cd EvaluationPlatform/Initialization/ansible
./create-vault.sh
```

Application and database credentials are not generated from this Vault. Replace
the committed `++++++++` placeholders only after copying each component's
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, and never
commit populated Secrets.

## Supported topology

The bundled scenarios expect a control-plane node, one tools node labelled
`role=tools`, and six service workers named `worker-node-1` through
`worker-node-6`, labelled `role=services`. Hostnames in `inventory.example.ini`
are placeholders. For another layout, update inventory and labels together with
Runner's node-IP mapping, application placement profiles, and chaos selectors.
See the [topology guide](../../docs/infrastructure.md#cluster-topology).

## Provision a cluster

Create the restricted Evaluation cleaner key once:

```bash
ssh-keygen -t ed25519 -f "$HOME/.ssh/evaluation-chaos-cleaner" \
  -C evaluation-chaos-cleaner
```

Then install the platform:

```bash
cd EvaluationPlatform/Initialization/ansible
ansible-playbook site.yml \
  --ask-vault-pass \
  -e @/absolute/path/to/secrets.vault.yml
```

`site.yml` performs only these phases:

1. Install the k3s server and join tool/service nodes using the stable channel.
2. Fetch a generated kubeconfig and apply the `role=tools`/`role=services` labels.
3. Install Istio, Prometheus and detector rules, Loki, Alloy, Grafana, Jaeger,
   and Chaos Mesh.
4. Install pinned chaosd and the restricted host cleanup account on service nodes.

Run a single platform phase with a playbook under `playbooks/`. Syntax checks
do not contact a cluster.

Istio is deliberately pinned by `istio_chart_version` in
`ansible/group_vars/all.yml`. Apply only the pinned Istio base, control plane,
and ingress gateway, without touching the other platform charts, with:

```bash
cd EvaluationPlatform/Initialization/ansible
ansible-playbook playbooks/istio.yml
```

## Build images

From the repository root, copy `deployment/image.env.example` to ignored
`deployment/image.env`, customize `IMAGE_REGISTRY` and `IMAGE_TAG`, then use the
same settings for building and deploying:

```bash
source deployment/image.env
./build.sh
```

Images are named `IMAGE_REGISTRY/<component>:IMAGE_TAG`. Runner's build script
uses the repository root as its context; the other components use their own
folders. Docker allowlists/exclusions keep local credentials out of build inputs.
Component deploy scripts render image markers in memory, so do not apply
marker-bearing workload YAML directly. Initialization has no component image.

## Runtime boundary

Evaluation owns `deploy.sh`, its runner Secrets, `kubernetes/pod.yaml`,
named `hooks/prerun/<name>/run.sh`, `hooks/postrun/<name>/run.sh` hooks, and every application deployment input under
`EvaluationPlatform/Runner/resources/applications/`. Infrastructure exposes only cluster, node,
inventory, storage, and shared platform prerequisites through
`INFRASTRUCTURE_ROOT`. Application namespaces are created by Evaluation, not by
the platform playbook.

## Local database

From the workspace root:

```bash
docker compose --env-file EvaluationPlatform/Orchestrator/Database/.env \
  -f EvaluationPlatform/Orchestrator/Database/compose/database.yml up -d postgres
docker compose --env-file EvaluationPlatform/Orchestrator/Database/.env \
  -f EvaluationPlatform/Orchestrator/Database/compose/database.yml run --rm migration
```

Copy `EvaluationPlatform/Orchestrator/Database/.env.example` to the ignored `.env` and replace every
placeholder before running these commands.

## Validation

```bash
cd EvaluationPlatform/Initialization/ansible
ansible-inventory --graph
ansible-playbook site.yml --syntax-check
cd ../../Runner
kubectl kustomize applications/online-boutique/kustomize >/dev/null
```

Syntax checks are safe and local. Do not run provisioning, chart upgrades,
namespace resets, or chaos cleanup against a live cluster as routine validation.
