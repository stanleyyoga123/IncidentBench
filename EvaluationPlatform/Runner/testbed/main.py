"""CLI entrypoint for collection-driven multi-application evaluation runs."""

import signal
import subprocess
import time
from datetime import datetime, timezone

from testbed.bootstrap import build_and_run
from testbed.cli import (
    default_output_dir,
    non_negative_int,
    parse_args,
    positive_float,
    positive_int,
)
from testbed.evaluator.evaluator import Evaluator
from testbed.loadgenerator.runner import start_locust


def wait_until(target_elapsed: int, started_at: float) -> None:
    while True:
        remaining = target_elapsed - (time.monotonic() - started_at)
        if remaining <= 0:
            return
        time.sleep(min(remaining, 5))


def log_phase(message: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"[{timestamp}] {message}", flush=True)


def _interrupt_on_termination(_signum, _frame) -> None:
    raise KeyboardInterrupt


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    def execute(resolved):
        from testbed.artifacts.run_journal import event, timestamp
        def archived_log(message):
            log_phase(message)
            with (resolved.output_dir / 'runner.log').open('a') as stream:
                stream.write(f'[{timestamp()}] {message}\n')
            event(resolved.output_dir, 'engine_message', message=message)
        return build_and_run(
            resolved, evaluator_factory=Evaluator, load_launcher=start_locust,
            wait_until=wait_until, log=archived_log, run_function=subprocess.run,
            popen=subprocess.Popen, sleep=time.sleep)

    previous_sigterm = signal.signal(signal.SIGTERM, _interrupt_on_termination)
    try:
        from testbed.platform import run
        return run(args, execute)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)


if __name__ == "__main__":
    raise SystemExit(main())
