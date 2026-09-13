# Experiment input capture and live tracking

The Runner writes resolved settings and input provenance before integration
preparation or pre-run hooks, even when preparation fails. Validation-only
execution creates no output.

| Artifact | Contents and timing |
| --- | --- |
| `resolved-scenario.json` | Effective merged load parameters/defaults, timings, deployments, integration, ordered hooks and steps; saved before preparation |
| `run-context.json` | Run UUID, resolved scenario and non-secret environment, including endpoints, node IPs, inventory path and credential variable name; saved before preparation |
| `inputs/source/configuration/` | Original scenario/global/environment JSON content and full suite JSON with overrides; saved before preparation |
| `inputs/source/` | Selected hook/integration scripts, shared helpers, cleanup script, application profile/local journey, bundled traffic code/defaults, registry, schemas and original chaos templates; saved before preparation |
| `inputs/manifest.json` | Source/archive paths, hashes, sizes, suite position/count/spacing, Python version and allowlisted machine/traffic environment overrides |
| `run-status.json` | Outer phase, UTC start/update/end times, errors, cleanup safety and final exit code; updated throughout execution |
| `events.jsonl` | Append-only UTC timeline of outer transitions, hook starts/finishes and engine messages |
| `hooks.json`, `hooks/*.log` | Hook order, active/completed/failed status, start/end times, return codes and individual stdout/stderr; records written before and after each hook |
| `runner.log` | Timestamped engine messages, including baseline and chaos step progress |
| `metadata.json` | Current engine phase/start time, outcomes, runtime settings, placement comparisons and completed chaos steps; available after bootstrap |
| `inputs/scenario.json`, `inputs/chaos/`, `inputs/placement/` | Execution scenario, resolved chaos YAML, placement source and rendered manifest; available after bootstrap/rendering |
| `application-install.json`, `commands/`, `loadgenerator/`, `injector/`, `metrics/`, `snapshots/`, `sessions/` | Installation, command, traffic, chaos, measurement and exported solution evidence as operations complete |

Configuration snapshots preserve JSON content with normalized formatting; hashes
describe archived bytes. `resolved-scenario.json` is authoritative for effective
settings. Original relative references in source snapshots are provenance, not
runnable paths inside the archive; the manifest records original locations.

The console prints the output directory before preparation. From Runner:

```bash
cat results/MY-RUN/run-status.json
cat results/MY-RUN/hooks.json
tail -f results/MY-RUN/events.jsonl
tail -f results/MY-RUN/runner.log
```

`updated_at` records transitions, not a heartbeat. A long baseline or hook can
stay in one phase for minutes; inspect its logs and traffic output for activity.
Child programs may buffer output. A process kill can leave a running status;
follow interrupted-run recovery before restarting.

## Capture boundaries

This is not a self-contained replay bundle. Inventory contents, kubeconfigs,
credential values, environment dumps, container images, external installer
dependencies and unlisted custom helper/import dependencies are not copied.
Application source paths and rendered placement are recorded, but arbitrary
installer source trees are not copied. Custom hooks should save additional
non-secret inputs under `inputs/`. Never embed credentials in scripts or
manifests selected for archival; use credential environment references instead.

Source snapshots are collected at suite launch. Do not edit code or resources
while a suite runs: execution still uses the checkout. Later-phase artifacts
may be absent when an earlier phase fails; the early config snapshot survives.
Historical archives remain unchanged.

## S3 visibility

The `upload` post-run hook syncs available inputs and progress records. It does
not stream live progress and runs before its own completion and final release/
status writes. Local final records are authoritative. Rerun the hook after
completion to refresh S3; see [S3 sync](../hooks/postrun/upload/README.md).

## Final node cleanup

Before node normalization, the engine archives the selected placement's node
names in `inputs/placement/nodes.json`. After the final evidence snapshot, the
outer finalizer stops workers, removes chaos, then uncordons only those nodes
and checks their schedulability. Results and command output are saved in
`node-cleanup.json` before post-run export/upload. This runs after failures and
interruptions too, provided ownership is held, workers stop, and chaos cleanup
succeeds. A failed uncordon or verification marks cleanup unsafe and prevents
release/continuation to the next batch run. Other placement nodes are still
attempted when one fails.

If preparation failed before placement resolution, no node normalization ran;
uncordoning is skipped with a recorded reason. Worker-stop or chaos-cleanup
failure also skips uncordoning, leaving cleanup unsafe. This restores the
experiment's schedulable baseline; it does not restore pre-existing cordon flags,
remove taints, or certify general node health.
