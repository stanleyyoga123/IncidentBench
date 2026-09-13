# Runner architecture

`testbed/platform.py` resolves schemas and owns serial runs, pre/post hooks, integration lifecycle and outer failure handling. `testbed/bootstrap.py` builds the existing workload/chaos phases. Configuration never accepts arbitrary shell text; named folders provide executable extensions.

The generic engine has no deployment-name list or database connection. The bundled integration speaks to Orchestrator's evaluation API and scales deployments declared in JSON. Orchestrator remains running throughout. Application installation and MCP permission grants are separate hooks.

Traffic classes receive validated JSON parameters through their generated Locust entrypoint. Input archiving preserves the effective scenario, resolved chaos manifests and placement fingerprints. Existing metrics, placement comparison and offline report formats remain available.

See [configuration and extension contracts](../README.md) and the [Orchestrator evaluation API](../../Orchestrator/docs/evaluation-api.md).

`hooks/lifecycle.py` discovers scripts under `hooks/` and records their order and outcomes. `hooks/runtime.py` implements shared HTTP and Kubernetes helpers. Editable catalogs live under `resources/`, shared researcher configuration under `config/`, and fixed schemas and traffic defaults with `testbed/`.
