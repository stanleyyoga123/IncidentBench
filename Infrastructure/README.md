# Infrastructure

This directory owns cluster creation, node preparation, platform namespaces
and tools, and Helm values. It does not install PostgreSQL, migrations, agent
services, application Secrets, or the Evaluation runner. Those resources and
their default-current-context deploy scripts live with their components.

## Layout

- `ansible/`: inventory plus cluster, platform, and node-preparation playbooks.
- `kubernetes/`: Online Boutique platform/workload inputs.
- `values/`: Prometheus, Grafana, Loki, Alloy, Jaeger, and tracing configuration.
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

Update `inventory.ini` before targeting a different cluster. The optional
encrypted `vault.yml` now contains only the chaos-cleaner public-key path:

```bash
cd Infrastructure/ansible
./create-vault.sh
```

Application and database credentials are not generated from this Vault. Replace
the committed `++++++++` placeholders only after copying each component's
`kubernetes/secret.example.yml` to ignored `kubernetes/secret.yml`, and never
commit populated Secrets.

## Provision a cluster

Create the restricted Evaluation cleaner key once:

```bash
ssh-keygen -t ed25519 -f "$HOME/.ssh/evaluation-chaos-cleaner" \
  -C evaluation-chaos-cleaner
```

Then install the platform:

```bash
cd Infrastructure/ansible
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
cd Infrastructure/ansible
ansible-playbook playbooks/istio.yml
```

## Build images

Build component images from their component directories. The Evaluation image
must use the workspace root as its Docker build context because it embeds the
central Online Boutique manifests:

```bash
docker build -f Evaluation/Dockerfile -t <registry>/agent-evaluator:<tag> .
docker build -f DatabaseJob/Dockerfile -t <registry>/database-job:<tag> DatabaseJob
```

Set immutable image tags in component manifests before a reproducible release.

## Runtime boundary

Evaluation owns `deploy.sh`, its runner Secrets, `kubernetes/pod.yaml`,
`prerun/run.sh`, and `postrun/run.sh`. Runtime scripts still read Online Boutique
and inventory inputs through `INFRASTRUCTURE_ROOT`.

## Local database

From the workspace root:

```bash
docker compose --env-file DatabaseJob/.env \
  -f DatabaseJob/compose/database.yml up -d postgres
docker compose --env-file DatabaseJob/.env \
  -f DatabaseJob/compose/database.yml run --rm migration
```

Copy `DatabaseJob/.env.example` to the ignored `.env` and replace every
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
