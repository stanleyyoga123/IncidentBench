"""Helpers used explicitly by trusted, researcher-owned shell hooks."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def api(context, action):
    config = context['environment']
    token = os.environ.get(config['control_token_env'])
    if not token or token == '++++++++':
        raise ValueError('Orchestrator control token is required')
    base = config.get('orchestrator_url')
    if not base:
        raise ValueError('orchestrator_url is required')
    path = '/api/v1/evaluation/' + action
    data = json.dumps({'run_id': context['run_id']}).encode()
    if action == 'export':
        path += '?' + urlencode({'run_id': context['run_id']})
        data = None
    request = Request(base.rstrip('/') + path, data=data,
                      headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    for attempt in range(3):
        try:
            with urlopen(request, timeout=120) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f'Orchestrator {action} returned HTTP {exc.code}') from None
        except (URLError, TimeoutError):
            if attempt == 2:
                raise RuntimeError(f'Orchestrator {action} is unreachable') from None
            time.sleep(2)


def scale(context, enabled, *, run=subprocess.run, sleep=time.sleep, monotonic=time.monotonic):
    for item in context['scenario']['deployments']:
        count = item['replicas'] if enabled else 0
        name, namespace = item['name'], item['namespace']
        run(['kubectl', '-n', namespace, 'scale', 'deployment', name, f'--replicas={count}'], check=True)
        if enabled:
            run(['kubectl', '-n', namespace, 'rollout', 'status', f'deployment/{name}', '--timeout=10m'], check=True)
            continue
        deadline = monotonic() + 300
        while monotonic() < deadline:
            result = run(['kubectl', '-n', namespace, 'get', 'deployment', name, '-o', 'json'], check=True, capture_output=True, text=True)
            deployment = json.loads(result.stdout)
            selector = deployment['spec']['selector']
            labels = [f'{k}={v}' for k, v in selector.get('matchLabels', {}).items()]
            for expression in selector.get('matchExpressions', []):
                key, op, values = expression['key'], expression['operator'], expression.get('values', [])
                labels.append({'In': f'{key} in ({",".join(values)})', 'NotIn': f'{key} notin ({",".join(values)})', 'Exists': key, 'DoesNotExist': '!' + key}[op])
            if not labels:
                raise RuntimeError('deployment selector must not be empty')
            pods = run(['kubectl', '-n', namespace, 'get', 'pods', '-l', ','.join(labels), '-o', 'json'], check=True, capture_output=True, text=True)
            # Ready=0 alone is insufficient: terminating workers may still write.
            if deployment['spec']['replicas'] == 0 and not json.loads(pods.stdout)['items']:
                break
            sleep(2)
        else:
            raise RuntimeError(f'deployment {namespace}/{name} did not stop')


def verify_remediation_permissions(namespace, *, run=subprocess.run):
    # SubjectAccessReview uses the caller's normal in-cluster authentication.
    # kubectl --as can disable in-cluster credential fallback in Runner pods.
    for group, resource in (('apps', 'deployments'), ('autoscaling', 'horizontalpodautoscalers')):
        review = {
            'apiVersion': 'authorization.k8s.io/v1', 'kind': 'SubjectAccessReview',
            'spec': {
                'user': 'system:serviceaccount:agents:mcp-tools-remediation',
                'groups': ['system:serviceaccounts', 'system:serviceaccounts:agents', 'system:authenticated'],
                'resourceAttributes': {'namespace': namespace, 'verb': 'patch', 'group': group, 'resource': resource},
            },
        }
        result = run(['kubectl', 'create', '-f', '-', '-o', 'json'],
                     input=json.dumps(review), capture_output=True, text=True, check=True)
        if json.loads(result.stdout).get('status', {}).get('allowed') is not True:
            raise RuntimeError(f'MCP remediation cannot patch {resource}.{group} in {namespace}')


def main():
    operation, context_path, output = sys.argv[1:4]
    context = json.loads(Path(context_path).read_text())
    destination = Path(output)
    if operation.startswith('api-'):
        action = operation[4:]
        result = api(context, action)
        if action == 'export':
            if result.get('schema_version') != 1 or result.get('run_id') != context['run_id']:
                raise ValueError('invalid export envelope')
            expected = {'anomaly','rca_session','remediation_run','remediation_session','learning_session','workflow'}
            if set(result.get('sessions', {})) != expected or any(not isinstance(v, list) for v in result['sessions'].values()):
                raise ValueError('invalid session export')
            folder = destination / 'sessions'; folder.mkdir(exist_ok=True)
            for name, rows in result['sessions'].items():
                temporary = folder / (name + '.tmp')
                temporary.write_text(json.dumps(rows, indent=2) + '\n')
                temporary.replace(folder / (name + '.json'))
        else:
            (destination / 'evaluation-state.json').write_text(json.dumps(result, indent=2) + '\n')
    elif operation in ('scale-down', 'scale-up'):
        scale(context, operation == 'scale-up')
    elif operation == 'install':
        from testbed.applications.prerun import main as install
        os.environ['OUTPUT_DIR'] = str(destination)
        install(['--scenario', context['scenario_path']])
    elif operation == 'grant-remediation':
        from testbed.applications import ApplicationCatalog
        root = Path(__file__).resolve().parents[1]
        profile = ApplicationCatalog(root / 'resources/applications', root.parents[1]).resolve(context['scenario']['application'])
        binding = root.parents[1] / 'Agents/MCPTools/kubernetes/application-role-binding.yaml'
        subprocess.run(['kubectl', '-n', profile.namespace, 'apply', '-f', str(binding)], check=True)
        verify_remediation_permissions(profile.namespace)
    elif operation == 'upload':
        uri = context['environment'].get('s3_results_uri')
        if not uri:
            print('S3 sync skipped: s3_results_uri is not configured.')
            return
        subprocess.run(['aws', 's3', 'sync', str(destination) + '/', uri.rstrip('/') + '/' + destination.name + '/', '--only-show-errors'], check=True)
        print('Run results synced to S3.')
    else:
        raise ValueError('unknown hook operation')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
