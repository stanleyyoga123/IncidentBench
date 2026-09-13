"""Validate, prepare, execute and finalize one run or a serial JSON suite."""
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from types import SimpleNamespace
from uuid import uuid4

from .configuration import ROOT, environment, read_json, resolve_scenario, validate
from hooks.lifecycle import Lifecycle, run_script
from .artifacts.run_journal import event, timestamp, write_json
from .artifacts.configuration_snapshot import capture, archive
from .kubernetes.node_cleanup import uncordon_placement_nodes


def preflight(spec, env=None):
    from .applications import ApplicationCatalog
    from .applications.installers import ApplicationInstaller
    from .chaos.catalog.chaos_catalog import ChaosCatalog
    from .command.command_runner import CommandRunner
    from .placement.placement_catalog import PlacementCatalog
    from .scenarios.scenario_loader import ScenarioLoader
    catalog = ApplicationCatalog(ROOT / 'resources/applications', ROOT.parents[1])
    profile = catalog.resolve(spec['application'])
    source = profile.installer.install_source(ROOT.parents[1])
    placement = PlacementCatalog(source / 'overlays' if profile.placement.mode == 'rendered' else profile.placement_root(ROOT.parents[1]), marker='kustomization.yaml' if profile.placement.mode == 'rendered' else 'profile.yaml')
    placement.resolve(spec['placement'])
    from .chaos.catalog.schedule_loader import ScheduleLoader
    chaos = ChaosCatalog(ROOT / 'resources/chaos', ScheduleLoader(node_ips=(env or {}).get('node_ips', {})))
    loader = ScenarioLoader(ROOT, chaos, placement, catalog)
    for index, step in enumerate(spec['steps'], 1):
        loader._parse_step(index, step)
    # Source validation performs no cluster calls; it also checks local binaries.
    ApplicationInstaller(CommandRunner(), ROOT, ROOT.parents[1]).validate(profile, spec['placement'])


def execution_namespace(spec, env, output, lifecycle):
    return SimpleNamespace(
        scenario=output / 'resolved-scenario.json', output_dir=output,
        loadgenerator=spec['load']['type'], load_parameters=spec['load']['parameters'],
        baseline_minutes=spec['timing']['baseline_seconds'] / 60,
        duration=spec['timing']['baseline_seconds'], grace_period=spec['timing']['grace_seconds'],
        skip_agents=not spec['agents_enabled'], namespace=None,
        agent_namespace=','.join(sorted({d['namespace'] for d in spec['deployments']})) or 'none',
        host=env.get('host'), prometheus_url=env.get('prometheus_url'),
        port_forward=env['port_forward'], port_forward_port=env['port_forward_port'],
        lifecycle=lifecycle, node_ips=env.get("node_ips", {}),
    )


def run_one(spec, env, output, execute, *, snapshot=None, invocation=None):
    output.mkdir(parents=True, exist_ok=False)
    run_id = str(uuid4())
    scenario_path = output / 'resolved-scenario.json'
    scenario_path.write_text(json.dumps(spec, indent=2) + '\n')
    context_path = output / 'run-context.json'
    context_path.write_text(json.dumps({'schema_version':1, 'run_id':run_id, 'scenario_path':str(scenario_path), 'scenario':spec, 'environment':env}, indent=2) + '\n')
    if snapshot is not None:
        archive(output, snapshot, invocation)
    print(f'Run artifacts: {output}', flush=True)
    lifecycle = Lifecycle(ROOT, context_path, output)
    status = {'schema_version':1, 'run_id':run_id, 'status':'preparing', 'errors':[], 'cleanup_safe':False}
    status['started_at'] = timestamp()
    def progress(phase):
        status['status'] = phase
        status['updated_at'] = timestamp()
        write_json(output / 'run-status.json', status)
        event(output, 'run_phase', phase=phase, run_id=run_id)
    progress('preparing')
    attempted = False
    code = 0
    try:
        attempted = True
        lifecycle.integration('prepare')
        progress('prerun')
        lifecycle.hooks('prerun')
        progress('running')
        code = execute(execution_namespace(spec, env, output, lifecycle))
    except KeyboardInterrupt:
        code = 130
        status['errors'].append('interrupted')
    except Exception as exc:
        code = 1
        status['errors'].append(str(exc))
    finally:
        # Once finalization starts, a second SIGINT/SIGTERM must not skip cleanup.
        handlers = {sig:signal.signal(sig, signal.SIG_IGN) for sig in (signal.SIGINT, signal.SIGTERM)}
        try:
            status['execution_returncode'] = code
            progress('finalizing')
            # An acquire conflict must never stop another researcher's deployment.
            state_path = output / 'evaluation-state.json'
            owns = spec['integration'] != 'bundled' or (state_path.exists() and read_json(state_path).get('run_id') == run_id)
            if attempted and owns:
                stopped = False
                try:
                    lifecycle.integration('stop')
                    stopped = True
                except Exception as exc:
                    status['errors'].append(str(exc))
                try:
                    with (output / 'cleanup.log').open('w') as log:
                        result = run_script(['bash', str(ROOT / 'scripts/cleanup_chaos_state.sh'), '--yes'], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
                    status['cleanup_safe'] = result.returncode == 0
                    if result.returncode:
                        status['errors'].append('final chaos cleanup failed; see cleanup.log')
                except Exception as exc:
                    status['errors'].append(str(exc))
                if stopped and status['cleanup_safe']:
                    event(output, 'node_cleanup_started')
                    try:
                        nodes = uncordon_placement_nodes(output)
                        status['node_cleanup'] = nodes['status']
                        if nodes['returncode']:
                            status['cleanup_safe'] = False
                            status['errors'].append('final node uncordon failed; see node-cleanup.json')
                    except Exception as exc:
                        status['cleanup_safe'] = False
                        status['errors'].append(f'final node uncordon failed: {exc}')
                    event(output, 'node_cleanup_finished', cleanup_safe=status['cleanup_safe'])
                else:
                    status['cleanup_safe'] = False
                    status['node_cleanup'] = 'skipped'
                    write_json(output / 'node-cleanup.json', {
                        'status': 'skipped', 'reason': 'workers did not stop or chaos cleanup did not succeed',
                    })
                # Metadata precedes upload and is rewritten after post-run errors.
                progress('postrun')
                status['errors'].extend(lifecycle.hooks('postrun', continue_on_error=True))
                if stopped and status['cleanup_safe'] and not status['errors']:
                    try:
                        progress('releasing')
                        lifecycle.integration('release')
                    except Exception as exc:
                        status['errors'].append(str(exc))
            if status['errors']:
                code = code or 1
            status['status'] = 'interrupted' if code == 130 else 'failed' if code else 'completed'
            status['finished_at'] = timestamp()
            status['returncode'] = code
            progress(status['status'])
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    return code, status['cleanup_safe'] and not status['errors']


def run(args, execute):
    environment_documents = []
    env = environment(args.environment, documents=environment_documents)
    runs = []
    sources = []
    run_documents = []
    delay = 0
    if args.suite:
        suite_path = args.suite.resolve()
        suite = read_json(suite_path); validate(suite, 'suite')
        delay = suite['inter_run_seconds']
        for entry in suite['runs']:
            overrides = entry.get('overrides')
            # Partial overrides carry the same version, without forcing users to repeat it.
            if overrides is not None:
                overrides = {'schema_version':1, **overrides}
            source = (suite_path.parent / entry['scenario']).resolve()
            documents = list(environment_documents) + [('suite', suite_path, suite)]
            runs.append(resolve_scenario(source, overrides, documents=documents))
            run_documents.append(documents)
            sources.append(source)
    else:
        documents = list(environment_documents)
        runs.append(resolve_scenario(args.scenario, documents=documents))
        run_documents.append(documents)
        sources.append(args.scenario.resolve())
    for spec in runs:
        preflight(spec, env)
        if spec['integration'] == 'bundled' and not env.get('orchestrator_url'):
            raise ValueError('bundled integration requires orchestrator_url')
    if args.validate_only:
        print(f'Validated {len(runs)} run(s); no cluster operations executed.')
        return 0
    snapshots = [capture(ROOT, spec, documents) for spec, documents in zip(runs, run_documents)]
    if env.get('inventory'):
        os.environ['CHAOS_NODE_INVENTORY'] = env['inventory']
    # Prevent overlap even when no external integration is selected.
    with (ROOT / '.run.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('another evaluation is running from this Runner checkout') from None
        code = 0
        for index, spec in enumerate(runs):
            if args.output_dir and not args.suite:
                output = args.output_dir.resolve()
            else:
                base = args.output_dir.resolve() if args.output_dir else ROOT / 'results'
                output = base / (time.strftime('%Y%m%d-%H%M%S') + '-' + spec['name'] + '-' + uuid4().hex[:8])
            result, safe = run_one(spec, env, output, execute, snapshot=snapshots[index],
                                   invocation={'scenario': str(sources[index]), 'suite': str(args.suite.resolve()) if args.suite else None,
                                               'run_index': index + 1, 'run_count': len(runs), 'inter_run_seconds': delay})
            print(f'Run artifacts: {output}', flush=True)
            code = code or result
            if not safe or result == 130:
                break
            if index + 1 < len(runs):
                time.sleep(delay)
        return code
