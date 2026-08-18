# MCPTools instructions

This service owns cluster/observability/network/profiling/remediation tools, not
workflow persistence. Keep stable tool names and schemas. The investigation
profile must expose no remediation tools and must reject mutating kubectl before
execution; RBAC is defense in depth. Live Ansible execution requires a successful
check-mode record for the exact playbook content. Artifact tools require an
explicit session ID and paths must remain below the configured session root.

Own `kubernetes/` for both profile ConfigMaps and Deployments/Services,
ServiceAccounts and RBAC, the remediation artifact PVC, and the utility
network-probe DaemonSets. Also own placeholder-only `kubernetes/secret.yml` and
`deploy.sh`; replace every `++++++++` locally before deploying. The script uses
kubectl's current context and refuses unreplaced placeholders. Infrastructure
installs platform prerequisites and namespaces only.

Run `PYTHONPATH=app pytest -q` and `python -m compileall -q app tests`.
