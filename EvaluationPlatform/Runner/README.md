# Scenario-driven runner

The runner owns load, application placement verification, Chaos Mesh execution, metrics and run artifacts. A selectable integration owns the solution lifecycle. Named shell hooks own pre/post work. Runner code and credentials never access the solution database.

## Layout and researcher edits

- `testbed/`: execution engine, fixed `schemas/`, and `loadgenerator/defaults.json`.
- `resources/`: editable `applications/`, `scenarios/`, `chaos/`, and `suites/`.
- `config/`: shared global settings, environment examples and ignored local `environment.json`, plus the editable `load-shapes.json` registry.
- `hooks/`: importable lifecycle/helpers and customizable `integrations/`, `prerun/`, and `postrun/` scripts.
- `scripts/`: build, deployment and chaos cleanup operations.
- `results/`: raw run archives. Grading outputs, visualization outputs, and `analyzer.py` live in `../Grader/`.

From this directory, copy `config/environment.example.json` to `config/environment.json` and fill your endpoints, inventory path and node IPs. Supply the referenced token through the environment. Validate before running:

```bash
python -m testbed.main --suite resources/suites/all.json --environment config/environment.json --validate-only
python -m testbed.main --scenario resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json --environment config/environment.json --output-dir results/my-run
./run.sh
```

Build with `scripts/build.sh`; deploy with `scripts/deploy.sh` only against an authorized target. For grading and analysis:

```bash
cd ../Grader
./grade.sh --input ../Runner/results --output grades
python analyzer.py
```

## Configuration

The executable interface is:

```bash
python -m testbed.main (--scenario FILE | --suite FILE) --environment FILE [--output-dir DIR] [--validate-only]
```

Run the Python CLI from the Runner directory; CLI paths are relative to your working directory. `./run.sh` is an editable launcher with the all-suite and local environment paths written directly in it; it does not forward arguments. Scenario `global_config` references are relative to that scenario file. Suite scenario references are relative to the suite file. Environment inventory paths are relative to the environment JSON file. Output directories must be new; an existing directory is never overwritten.

All documents use `schema_version: 1`. Schemas live in `testbed/schemas/`. Unknown keys, duplicate JSON keys, invalid values, unknown hooks, and unknown integrations fail validation. Global defaults merge recursively with the scenario, then suite overrides. Arrays replace in full, including hook lists, deployment lists and daily stages. There is no recursive inheritance between global files.

Example scenario:

```json
{
  "schema_version": 1,
  "global_config": "../../../config/bundled.json",
  "name": "example-burst",
  "application": "online-boutique",
  "placement": "canonical-six-node",
  "load": {
    "type": "burst",
    "parameters": {
      "baseline_users": 50,
      "peak_users": 200,
      "baseline_seconds": 120,
      "peak_seconds": 30,
      "spawn_rate": 25,
      "bias_users": 0,
      "seed": 7
    }
  },
  "timing": {"baseline_seconds": 600, "grace_seconds": 60},
  "steps": [
    {"name": "incident", "chaos": ["node-delay-worker-3"], "duration": 300},
    {"name": "recovery", "chaos": [], "duration": 300}
  ]
}
```

Global config supplies shared `load`, `timing`, `integration`, `agents_enabled`, `deployments`, `prerun`, and `postrun`. The bundled configuration preserves the existing six worker/MCP deployments; Orchestrator is deliberately absent because its HTTP interface must remain available. Each deployment has `namespace`, `name`, and positive `replicas` for activation. Shutdown always uses zero and waits for all matching pods, including terminating pods, to disappear.

Traffic parameters:

| Shape | Parameters |
| --- | --- |
| `constant` | `users`, `bias_users`, `spawn_rate`, `seed` |
| `burst` | `baseline_users`, `peak_users`, `baseline_seconds`, `peak_seconds`, `bias_users`, `spawn_rate`, `seed` |
| `sinus` | `min_users`, `max_users`, `period_seconds`, `bias_users`, `spawn_rate`, `seed` |
| `daily` | `base_users`, `stages` containing cumulative `duration`, `percentage_users`, and `spawn_rate` |

Defaults are fixed in `testbed/loadgenerator/defaults.json` and materialized into the resolved scenario. A daily curve repeats after its final stage. Its clock starts with Locust, including the baseline. Total traffic runtime is baseline + activation grace + scenario step durations. Global defaults use only a load type so changing shape does not inherit incompatible parameters; if you add global shape parameters, scenario overrides must remain compatible with that shape.

Suites list ordered `{ "scenario": "...", "overrides": { ... } }` entries and `inter_run_seconds`. `resources/suites/paired.json` runs matching scenarios with `agents_enabled` true and false. Both variants use the bundled preparation/reset; false leaves workers stopped after baseline. `config/none.json` selects no external solution at all.

Environment JSON owns endpoints, node IPs, inventory, port forwarding, optional S3 destination, and the *name* of the token environment variable. URLs cannot contain credentials. Node-delay YAML uses `${node_ip:worker-node-N}`; only referenced schedules require matching `node_ips`. The archived YAML contains the resolved IP, and its digest describes the actual applied file. Node names and placement topology remain explicit experiment inputs: change placement overlays and chaos selectors together for a different topology.

For TeaStore use at least a ten-minute baseline, and for Sock Shop at least six minutes; their existing baseline health checks remain active. Curated ordinary scenarios retain the batch default of a 60-minute baseline; Sock Shop scenarios explicitly set shorter durations. Application warm-up remains in its profile.

## Lifecycle and hook interface

Integration script: `hooks/integrations/<name>/run.sh ACTION CONTEXT_JSON OUTPUT_DIR`, where ACTION is `prepare`, `activate`, `stop`, or `release`. Hook script: `hooks/prerun/<name>/run.sh CONTEXT_JSON OUTPUT_DIR` or the equivalent under `hooks/postrun/`. All execute via Bash with the Runner as working directory. Scripts are trusted local code, selected by safe names rather than inline shell commands.

The context contains `schema_version`, unique `run_id`, absolute `scenario_path`, resolved `scenario`, and non-secret `environment`. Credentials are inherited through environment variables; never print them, enable shell tracing, or copy them into artifacts. Scripts may write artifacts under OUTPUT_DIR. Exit zero means success. Each invocation has a 30-minute timeout, ordered entries in `hooks.json`, and a separate log in `hooks/`.

Execution order:

1. Validate every run in the suite before any cluster work.
2. Integration `prepare`; bundled acquires durable ownership/maintenance and scales configured workers down.
3. Ordered pre-run hooks; bundled requests full HTTP reset, installs the application, then grants MCP remediation permissions.
4. Clear stale chaos, render/archive inputs, normalize and verify placement, warm up the application, start traffic and collect baseline.
5. Integration `activate` only when agents are enabled; bundled waits for worker readiness, then resumes Orchestrator dispatch.
6. Execute ordered chaos/recovery steps and collect metrics.
7. Always finalize load, port forwarding, chaos and evidence; integration `stop` is idempotent and may be invoked again during outer finalization.
8. Attempt every post-run hook even when an earlier post-run hook fails. Export requires ownership in maintenance. Release ownership only after safe cleanup and successful hooks; maintenance remains enabled until the next run activates.

Pre-run failure prevents baseline/chaos. `run-status.json` reports outer failures even when preparation fails before normal metadata is created. Unsafe cleanup or unreleased ownership stops the suite. An acquire conflict never stops another run's deployments. The bundled deployment has durable database-backed ownership; the `none` and example integrations also have a local checkout lock. Custom multi-host integrations must implement their own shared ownership in `prepare`.

Bundled hooks are intentionally small shell files. `reset-solution/run.sh` visibly calls `api-reset`; `export-sessions/run.sh` calls `api-export`. Reusable HTTP/scale/install mechanics are in `hooks/runtime.py`. There are no partial reset options: bundled pre-run always clears workflows, jobs, audits, artifacts, lessons and the execution slot through Orchestrator.

## Extend the platform

- **Another solution:** copy `hooks/integrations/example/`, implement its four actions, add its deployment list to a global JSON file, and select your own pre/post hooks. Kubernetes lifecycle helpers accept any configured deployment names. Select `none` for a workload-only run.
- **A hook:** add a named folder and `run.sh`, consume the context contract, and include its name in the ordered JSON list. Keep reset or cleanup choices visible in the script.
- **An application:** add `resources/applications/<id>/profile.yaml`, its installation inputs and placement profiles, and a Python Locust journey module. Follow [application profiles](resources/applications/README.md). The installer has no MCP dependency; only the bundled `grant-remediation` hook grants it.
- **A load shape:** add a Locust shape module, register its module/class in `config/load-shapes.json`, add defaults to `testbed/loadgenerator/defaults.json`, and extend the load parameter branches of the three JSON schemas. The executor imports the registered class and sets validated parameters before Locust instantiates it.
- **A chaos scenario:** add complete Schedule YAML to `resources/chaos`, then reference it from steps. Preserve the existing cadence/duration constraints. Add matching manual ground truth and penalties in Grader for semantic scoring.
- **An exporter:** produce the [grader input contract](../Grader/README.md). See `hooks/postrun/example-export/run.sh` for a synthetic example. Missing or unevaluable results should remain explicit; never invent successful outputs.

## Runner pod and local configuration

Install `requirements.txt` plus kubectl, Helm and SSH. The pod image uses the same workspace hierarchy under `/workspace`. `scripts/deploy.sh` applies runner Secrets and mounts an inventory ConfigMap built from `../Initialization/ansible/inventory.ini`. Fill the required SSH and `ORCHESTRATOR_CONTROL_TOKEN` placeholders; optional AWS credentials may remain unset. The S3 destination comes from environment JSON. The optional upload hook uploads artifacts available at that phase; final local status remains authoritative if upload or release fails.

Legacy `.env` load files are not loaded and have been removed. Experiment settings come from JSON; `config/environment.json` remains required for machine settings, and credential environment variables remain required for the selected integration. Keep secrets outside JSON and consult the root quickstart for token pairing and deployment order.

## S3 result sync

The bundled post-run list already includes `upload` after `export-sessions`. Set `s3_results_uri` in `config/environment.json` to `s3://YOUR-BUCKET/evaluation-results` and supply AWS credentials through the AWS CLI credential chain. A null destination skips sync. See the [S3 upload hook](hooks/postrun/upload/README.md) for configuration, retries and final-status timing.

## Track an experiment

Every new run saves resolved settings and original configuration layers before preparation, with a hashed source manifest under `inputs/`. `run-status.json`, `hooks.json`, and `events.jsonl` expose lifecycle progress; `runner.log` and `metadata.json` expose engine progress. See [input capture and live tracking](docs/experiment-visibility.md) for commands, artifact timing, exclusions and S3 visibility.

The [Sock Shop scenario set](docs/scenario.md#sock-shop-scenarios) mirrors all 23 Online Boutique fault families, with a dedicated `resources/suites/sock-shop.json` suite and paired agent/no-agent entries.
