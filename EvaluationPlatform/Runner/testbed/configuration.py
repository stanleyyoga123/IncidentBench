"""Resolve experiment configuration without executing cluster operations."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / 'testbed/schemas'


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key}')
            result[key] = value
        return result
    return json.loads(Path(path).read_text(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f'invalid number: {value}')))


def validate(value, schema):
    errors = sorted(Draft202012Validator(read_json(SCHEMAS / f'{schema}.schema.json')).iter_errors(value),
                    key=lambda error: str(list(error.path)))
    if errors:
        error = errors[0]
        # Do not echo supplied values: environment files can be misconfigured.
        raise ValueError(f'{schema}: invalid configuration at {".".join(map(str, error.path)) or "root"} ({error.validator})')


def merge(base, override):
    result = deepcopy(base)
    for key, value in override.items():
        result[key] = merge(result[key], value) if isinstance(value, dict) and isinstance(result.get(key), dict) else deepcopy(value)
    return result


def resolve_scenario(path, overrides=None, *, documents=None):
    path = Path(path).resolve()
    raw = read_json(path)
    validate(raw, 'scenario')
    if documents is not None:
        documents.append(('scenario', path, deepcopy(raw)))
    base = {}
    if raw.get('global_config'):
        base = read_json(path.parent / raw['global_config'])
        validate(base, 'global')
        if documents is not None:
            documents.append(('global', path.parent / raw['global_config'], deepcopy(base)))
    result = merge(base, {k: v for k, v in raw.items() if k != 'global_config'})
    if overrides:
        validate(overrides, 'global')
        result = merge(result, overrides)
    validate(result, 'resolved')
    load = result['load']
    load['parameters'] = merge(read_json(ROOT / 'testbed/loadgenerator/defaults.json')[load['type']], load.get('parameters', {}))
    validate(result, 'resolved')
    p = load['parameters']
    if load['type'] == 'sinus' and p['min_users'] > p['max_users']:
        raise ValueError('sinus min_users must not exceed max_users')
    if load['type'] == 'burst' and p['baseline_users'] > p['peak_users']:
        raise ValueError('burst baseline_users must not exceed peak_users')
    if load['type'] == 'daily':
        ends = [stage['duration'] for stage in p['stages']]
        if ends != sorted(set(ends)):
            raise ValueError('daily stage durations must be strictly increasing cumulative seconds')
    seen = set()
    for deployment in result['deployments']:
        key = deployment['namespace'], deployment['name']
        if key in seen:
            raise ValueError('duplicate deployment')
        seen.add(key)
        if result['integration'] == 'bundled' and deployment['name'] == 'agent-orchestrator':
            raise ValueError('Orchestrator must remain running')
    for phase in ('prerun', 'postrun'):
        for name in result[phase]:
            if not (ROOT / 'hooks' / phase / name / 'run.sh').is_file():
                raise ValueError(f'unknown {phase} hook: {name}')
    if not (ROOT / 'hooks/integrations' / result['integration'] / 'run.sh').is_file():
        raise ValueError('unknown integration')
    return result


def environment(path, *, documents=None):
    path = Path(path).resolve()
    value = read_json(path)
    validate(value, 'environment')
    if documents is not None:
        documents.append(('environment', path, deepcopy(value)))
    value.setdefault('port_forward', False)
    value.setdefault('port_forward_port', 8888)
    value.setdefault('control_token_env', 'ORCHESTRATOR_CONTROL_TOKEN')
    if value.get('inventory'):
        value['inventory'] = str((path.parent / value['inventory']).resolve())
    for key in ('host', 'prometheus_url', 'orchestrator_url', 's3_results_uri'):
        if value.get(key):
            url = urlsplit(value[key])
            if url.username or url.password or url.query or url.fragment:
                raise ValueError(f'{key} cannot contain credentials, query parameters, or fragments')
            schemes = ('s3',) if key == 's3_results_uri' else ('http', 'https')
            if url.scheme not in schemes or not url.netloc:
                raise ValueError(f'invalid {key} URL')
    return value
