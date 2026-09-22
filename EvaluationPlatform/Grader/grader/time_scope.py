"""Recorded scheduled-chaos intervals shared by offline measurements."""
from __future__ import annotations

import math
from datetime import datetime

VERSION = 'scheduled-chaos-only-v1'


def epoch(value):
    if not isinstance(value, str):
        raise ValueError('missing recorded timestamp')
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timestamp requires a timezone')
    return parsed.timestamp()


def chaos_intervals(metadata):
    """Do not infer a completed interval from a planned duration alone."""
    intervals = []
    for fault in metadata.get('chaos_steps', []):
        if not fault.get('chaos') or fault.get('idle'):
            continue
        start = epoch(fault.get('active_started_at'))
        end = epoch(fault.get('cleanup_started_at'))
        duration = fault.get('duration')
        if duration is not None:
            if isinstance(duration, bool) or not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration <= 0:
                raise ValueError('invalid chaos duration')
            end = min(end, start + duration)
        if not start < end:
            raise ValueError('invalid recorded chaos interval')
        intervals.append((start, end))
    intervals.sort()
    if not intervals:
        raise ValueError('missing recorded chaos intervals')
    if any(b[0] < a[1] for a, b in zip(intervals, intervals[1:])):
        raise ValueError('overlapping recorded chaos intervals')
    return intervals


def contains(intervals, start, end=None):
    if end is None:
        return any(a <= start < b for a, b in intervals)
    return any(a <= start < end <= b for a, b in intervals)


def job_scope(job, intervals):
    """An output belongs to [chaos start, chaos end) by completion time."""
    if not intervals:
        return {'included': False, 'reason': 'missing or invalid recorded chaos boundaries'}
    try:
        completed = epoch(job.get('completed_at'))
    except (ValueError, TypeError):
        return {'included': False, 'reason': 'missing or invalid output completion timestamp'}
    included = contains(intervals, completed)
    return {'included': included, 'reason': None if included else 'output completed outside recorded chaos intervals'}
