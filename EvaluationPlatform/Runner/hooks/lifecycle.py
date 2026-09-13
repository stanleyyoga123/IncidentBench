"""Named shell hooks share a small, file-backed context contract."""
import json
import os
import signal
from pathlib import Path
import subprocess
from testbed.artifacts.run_journal import event, timestamp, write_json


def run_script(command, **kwargs):
    timeout = kwargs.pop("timeout", 1800)
    process = subprocess.Popen(command, start_new_session=True, **kwargs)
    try:
        process.wait(timeout=timeout)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass
        raise
    return process


class Lifecycle:
    def __init__(self, root, context_path, output, *, run=run_script):
        self.root, self.context_path, self.output = Path(root), Path(context_path), Path(output)
        self.context = json.loads(self.context_path.read_text())
        self.run = run
        self.records = []

    def invoke(self, phase, name, action=None):
        script = self.root / "hooks" / phase / name / 'run.sh'
        command = ['bash', str(script)]
        if action:
            command.append(action)
        command.extend([str(self.context_path), str(self.output)])
        folder = self.output / 'hooks'; folder.mkdir(exist_ok=True)
        label = f'{len(self.records):02}-{phase}-{name}' + (f'-{action}' if action else '')
        record = {'phase': phase, 'name': name, 'action': action, 'returncode': None}
        record.update(status='running', started_at=timestamp(), log=f'hooks/{label}.log')
        self.records.append(record)
        write_json(self.output / 'hooks.json', self.records)
        event(self.output, 'hook_started', phase=phase, name=name, action=action)
        try:
            with (folder / (label + '.log')).open('w') as log:
                result = self.run(command, cwd=self.root, stdout=log, stderr=subprocess.STDOUT, timeout=1800)
            record['returncode'] = result.returncode
            if result.returncode:
                raise RuntimeError(f'{phase}/{name} {action or ""} failed; see hooks/{label}.log')
        except BaseException as exc:
            record['error'] = type(exc).__name__
            raise
        finally:
            record.update(status='failed' if record.get('error') or record['returncode'] else 'completed', finished_at=timestamp())
            write_json(self.output / 'hooks.json', self.records)
            event(self.output, 'hook_finished', **record)

    def integration(self, action):
        self.invoke('integrations', self.context['scenario']['integration'], action)

    def hooks(self, phase, *, continue_on_error=False):
        failures = []
        for name in self.context['scenario'][phase]:
            try:
                self.invoke(phase, name)
            except Exception as exc:
                failures.append(str(exc))
                if not continue_on_error:
                    raise
        return failures


class IntegrationController:
    """Adapter for existing phase objects; names come only from configuration."""
    def __init__(self, lifecycle):
        self.lifecycle = lifecycle

    def scale(self, namespace, replicas, output_dir=None):
        try:
            self.lifecycle.integration('activate' if replicas else 'stop')
            return {'returncode': 0}
        except Exception as exc:
            return {'returncode': 1, 'error': str(exc)}

    def wait(self, namespace, replicas, output_dir=None, **kwargs):
        # The shell lifecycle operation includes readiness/termination checks.
        return {'returncode': 0}
