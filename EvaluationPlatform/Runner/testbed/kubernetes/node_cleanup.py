"""Return this experiment's placement nodes to a schedulable state."""
import json
from pathlib import Path
import re
import subprocess

from ..artifacts.run_journal import timestamp, write_json


def uncordon_placement_nodes(output, *, run=subprocess.run):
    output = Path(output)
    target_file = output / 'inputs/placement/nodes.json'
    report_file = output / 'node-cleanup.json'
    report = {'status': 'running', 'started_at': timestamp(), 'nodes': {}, 'returncode': 0}
    if not target_file.exists():
        report.update(status='skipped', reason='placement nodes were not resolved; no node normalization ran')
        write_json(report_file, report)
        return report
    try:
        nodes = json.loads(target_file.read_text())
        if not isinstance(nodes, list) or not nodes or any(
            not isinstance(node, str) or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', node)
            for node in nodes
        ):
            raise ValueError('invalid archived placement node list')
        write_json(report_file, report)
        for node in sorted(set(nodes)):
            entry = report['nodes'][node] = {}
            try:
                for operation, command in (
                    ('uncordon', ['kubectl', 'uncordon', node]),
                    ('verify', ['kubectl', 'get', 'node', node, '-o', 'json']),
                ):
                    result = run(command, capture_output=True, text=True, timeout=60, check=False)
                    entry[operation] = {'command': command, 'returncode': result.returncode,
                                        'stdout': result.stdout, 'stderr': result.stderr}
                    if result.returncode:
                        raise RuntimeError(f'{operation} failed for {node}')
                    if operation == 'verify' and json.loads(result.stdout).get('spec', {}).get('unschedulable', False):
                        raise RuntimeError(f'node remains unschedulable: {node}')
                entry['status'] = 'completed'
            except Exception as exc:
                entry.update(status='failed', error=str(exc))
                report['returncode'] = 1
            write_json(report_file, report)
        report['status'] = 'failed' if report['returncode'] else 'completed'
    except Exception as exc:
        report.update(status='failed', error=str(exc), returncode=1)
    report['finished_at'] = timestamp()
    write_json(report_file, report)
    return report
