# MCPTools

MCPTools serves the former monolithic agent tools over authenticated MCP
Streamable HTTP at `/mcp`. The same image runs as `investigation` and
`remediation` profiles with distinct bearer tokens, allowlists, and Kubernetes
service accounts. The remediation profile stores session files on its mounted
PVC and never writes workflow data directly to PostgreSQL.

`kubernetes/` owns both profile Deployments and Services, their RBAC, the
remediation PVC, overlay/underlay probe DaemonSets, and the two placeholder
Secrets. Replace every `++++++++` in `kubernetes/secret.yml`, then run
`./deploy.sh` against kubectl's current context; it refuses placeholders.
Use distinct investigation and remediation tokens. The investigation value
must match RCAAgent's `MCP_TOKEN`; the remediation value must match
RemediatorAgent's `MCP_TOKEN`. Deploy MCPTools before either job service.
