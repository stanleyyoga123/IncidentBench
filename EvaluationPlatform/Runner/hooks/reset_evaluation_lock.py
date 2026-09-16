"""Explicit operator recovery of interrupted evaluation ownership."""
import argparse
import json
from pathlib import Path
import re
import sys

from hooks.runtime import api


def reset_lock(environment, run_id=None):
    if run_id is not None and not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', run_id):
        raise ValueError('Invalid run ID')
    context = {'environment': environment, 'run_id': run_id or ''}
    state = api(context, 'state')
    owner = state['run_id']
    if owner is None:
        print('Evaluation lock is already clear.')
        return
    if run_id is not None and owner != run_id:
        raise ValueError(f"Evaluation is owned by {owner}; supplied run ID does not match")
    if not isinstance(owner, str) or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', owner):
        raise ValueError('Invalid evaluation owner returned by Orchestrator')
    run_id = owner
    context['run_id'] = owner
    # Each transition checks ownership transactionally, including after this GET.
    api(context, 'pause')
    state = api(context, 'release')
    if state['run_id'] is not None or state['maintenance'] is not True:
        raise RuntimeError('Unexpected release response; inspect evaluation state')
    print(f'Released evaluation lock for {run_id}. Orchestrator remains in maintenance.')


def main():
    parser = argparse.ArgumentParser(
        description='Release an interrupted evaluation lock after stopping the runner and completing recovery cleanup. Preserves stored results; leaves maintenance enabled.')
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument('--run-id', help='Interrupted owner from run-context.json')
    owner.add_argument('--current-owner', action='store_true', help='Discover and release the current evaluation owner')
    parser.add_argument('--environment', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'config/environment.json',
                        help='Environment JSON (default: Runner/config/environment.json)')
    args = parser.parse_args()
    reset_lock(json.loads(args.environment.read_text()), args.run_id)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, RuntimeError) as exc:
        print(f'Cannot reset evaluation lock: {exc}', file=sys.stderr)
        raise SystemExit(1)
