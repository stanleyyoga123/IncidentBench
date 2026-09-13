"""Atomic current state and an append-only UTC timeline for a running experiment."""
from datetime import datetime, timezone
import json
from pathlib import Path


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def event(output, kind, **fields):
    record = {'timestamp': timestamp(), 'event': kind, **fields}
    with (Path(output) / 'events.jsonl').open('a') as stream:
        stream.write(json.dumps(record) + '\n')
