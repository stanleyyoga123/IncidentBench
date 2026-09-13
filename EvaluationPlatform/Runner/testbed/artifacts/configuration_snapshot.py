"""Capture validated configuration provenance before any lifecycle mutation.

Credentials, process environment dumps and inventories are deliberately excluded.
This is an input record, not a hermetic copy of external application dependencies.
"""
import hashlib
import json
import os
import sys
from pathlib import Path

from .run_journal import timestamp, write_json


def capture(root, spec, documents):
    from ..applications import ApplicationCatalog
    root = Path(root)
    files = {}
    def add(path, label=None):
        path = Path(path)
        files[label or str(path.relative_to(root))] = (str(path.resolve()), path.read_bytes())
    for label, path, document in documents:
        # These documents have passed strict JSON validation. Do not archive arbitrary files.
        files['configuration/' + label + '.json'] = (
            str(Path(path).resolve()), (json.dumps(document, indent=2) + '\n').encode())
    add(root / 'config/load-shapes.json')
    add(root / 'testbed/loadgenerator/defaults.json')
    for path in (root / 'testbed/loadgenerator').glob('*.py'):
        add(path)
    add(root / 'scripts/cleanup_chaos_state.sh')
    for path in (root / 'testbed/schemas').glob('*.json'):
        add(path)
    for phase in ('prerun', 'postrun'):
        for name in spec[phase]:
            add(root / 'hooks' / phase / name / 'run.sh')
    add(root / 'hooks/integrations' / spec['integration'] / 'run.sh')
    for name in ('runtime.py', 'lifecycle.py'):
        add(root / 'hooks' / name)
    profile = ApplicationCatalog(root / 'resources/applications', root.parents[1]).resolve(spec['application'])
    add(profile.source_path)
    journey = root.joinpath(*profile.loadgenerator_module.split('.')).with_suffix('.py')
    if journey.is_file():
        add(journey)
    for reference in {ref for step in spec['steps'] for ref in step.get('chaos', [])}:
        matches = list((root / 'resources/chaos').glob(reference + '.yaml'))
        if len(matches) != 1:
            raise ValueError(f'cannot uniquely archive chaos source: {reference}')
        add(matches[0])
    return files


def archive(output, files, invocation):
    folder = Path(output) / 'inputs/source'
    folder.mkdir(parents=True)
    records = []
    for label, (source, data) in sorted(files.items()):
        target = folder / label
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        records.append({'source': source, 'archive': str(target.relative_to(output)),
                        'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)})
    write_json(Path(output) / 'inputs/manifest.json', {
        'schema_version': 1, 'captured_at': timestamp(), 'invocation': invocation,
        'files': records,
        'python_version': sys.version,
        'environment_overrides': {key: os.environ[key] for key in (
            'CONNECTION_RECYCLE_EVERY_REQUESTS', 'INFRASTRUCTURE_ROOT',
            'CHAOS_NODE_INVENTORY', 'CHAOS_NODE_SSH_USER', 'CHAOS_NODE_SSH_IDENTITY_FILE',
            'CHAOS_NODE_SSH_KNOWN_HOSTS_FILE', 'ONLINE_BOUTIQUE_ROOT', 'TEASTORE_ROOT', 'SOCK_SHOP_ROOT'
        ) if key in os.environ},
        'exclusions': ['credential values and process environment', 'inventory contents',
                       'external installer dependencies and container images',
                       'custom hook helper dependencies not listed in files'],
    })
