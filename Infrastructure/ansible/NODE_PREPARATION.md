# Node preparation

`inventory.ini` is the canonical definition of the control-plane, tool, and
service nodes. `playbooks/cluster.yml` installs k3s and applies workload-role
labels. Node-level chaos needs two additional playbooks after Chaos Mesh is
installed:

```bash
ansible-playbook playbooks/node-chaosd.yml
ansible-playbook playbooks/node-cleaner.yml \
  -e chaos_cleaner_public_key_file="$HOME/.ssh/evaluation-chaos-cleaner.pub"
```

`node-chaosd.yml` installs chaosd on every `service_nodes` host, creates a
per-node TLS certificate using the Chaos Mesh CA, removes the CA private key
from the node, and manages chaosd with systemd.

`node-cleaner.yml` creates a locked `chaos-cleaner` account, installs the
root-owned audit/cleanup helpers, limits passwordless sudo to those helpers,
and writes pinned host keys to `../generated/evaluation-runner-known_hosts`.
The private SSH key is never checked in or baked into an image.

The Evaluation runner uses the same inventory through a ConfigMap and the
restricted identity through Evaluation's component-owned Secret and
`Evaluation/ansible/roles/evaluation_runner` role.
TCP port 22 must be reachable from the runner on the tool node to all service
nodes. Re-run the cleaner playbook whenever a node is rebuilt or the helper
changes.

Read-only verification from the workspace root:

```bash
Evaluation/check_chaos_state.sh
```

The destructive cleanup script remains in Evaluation and requires an explicit
confirmation or `--yes`:

```bash
Evaluation/cleanup_chaos_state.sh
```

