# MCPTools

MCPTools serves the former monolithic agent tools over authenticated MCP
Streamable HTTP at `/mcp`. The same image runs as `investigation` and
`remediation` profiles with distinct bearer tokens, allowlists, and Kubernetes
service accounts. The remediation profile stores session files on its mounted
PVC and never writes workflow data directly to PostgreSQL.

Detailed transport, profile, tool, RBAC, network-probe, and remediation-session
documentation starts at [`docs/README.md`](docs/README.md).

`kubernetes/` owns both profile Deployments and Services, their RBAC, the
remediation PVC, overlay/underlay probe DaemonSets, and the two placeholder
Secrets. Copy `kubernetes/secret.example.yml` to ignored
`kubernetes/secret.yml`, replace every `++++++++`, then run `./deploy.sh`
against kubectl's current context; it refuses placeholders.
Use distinct investigation and remediation tokens. The investigation value
must match RCAAgent's `MCP_TOKEN`; the remediation value must match
RemediatorAgent's `MCP_TOKEN`. Deploy MCPTools before either job service.
