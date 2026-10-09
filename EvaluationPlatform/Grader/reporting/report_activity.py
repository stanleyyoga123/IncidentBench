"""Chaos-only workflow activity counts and per-run descriptive summaries."""
from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
from pydantic import BaseModel, TypeAdapter, ValidationError

from grader.time_scope import contains, epoch


class ActivityRecord(BaseModel):
    """Fields needed from an archived detection or job record."""

    status: str | None = None
    detected_at: str | None = None
    completed_at: str | None = None


ACTIVITY_LABELS = {
    'anomaly': 'Anomalies raised',
    'rca': 'RCA attempts completed',
    'remediation': 'Remediation attempts completed',
}


def activity_counts(archive: Path, intervals: list[tuple[float, float]]) -> dict[str, int | None]:
    """Count raw records; missing evidence or unplaceable records stay unknown."""
    counts = {}
    adapter = TypeAdapter(list[ActivityRecord])
    for kind, filename in (('anomaly', 'anomaly.json'), ('rca', 'rca_session.json'),
                           ('remediation', 'remediation_run.json')):
        key = f'{kind}_activity_count'
        counts[key] = None
        if not intervals:
            continue
        try:
            records = adapter.validate_json((archive / 'sessions' / filename).read_text(encoding='utf-8'))
        except (OSError, UnicodeDecodeError, ValidationError):
            continue
        count = 0
        for record in records:
            if kind != 'anomaly':
                if record.status is None:
                    break
                if record.status not in ('succeeded', 'failed'):
                    continue
            try:
                timestamp = epoch(record.detected_at if kind == 'anomaly' else record.completed_at)
            except (ValueError, TypeError):
                break
            count += contains(intervals, timestamp)
        else:
            counts[key] = count
    return counts


def scenario_resource_fault(scenario: str, application: str) -> tuple[str, str]:
    """Extract the injected resource/fault from current archived scenario names."""
    name = scenario.removeprefix(application + '-')
    node = re.match(r'^node-(cpu|memory|delay|loss)(?:-|$)', name)
    if node:
        return 'node', node.group(1)
    pod = re.match(r'^pod-.+?-(cpu-headroom|capacity-loss|bandwidth|memory|cpu)(?:-|$)', name)
    if pod:
        return 'pod', pod.group(1)
    return 'Unknown', 'Unclassified'


def activity_summary(selected: pd.DataFrame) -> pd.DataFrame:
    """Group selected completed runs; retain numeric mean, sample SD, and n."""
    completed = selected.loc[selected.run_completed].copy()
    groups = ['application', 'fault_type', 'resource_type']
    columns = [*groups, 'runs', *[f'{kind}_{stat}' for kind in ACTIVITY_LABELS
                                for stat in ('mean', 'std', 'n')]]
    if completed.empty:
        return pd.DataFrame(columns=columns)
    details = [scenario_resource_fault(row.scenario, row.application)
               for row in completed.itertuples()]
    completed['resource_type'] = [resource for resource, _ in details]
    completed['fault_type'] = [fault for _, fault in details]
    aggregations = {'runs': ('run', 'size')}
    for kind in ACTIVITY_LABELS:
        for stat, operation in (('mean', 'mean'), ('std', 'std'), ('n', 'count')):
            aggregations[f'{kind}_{stat}'] = (f'{kind}_activity_count', operation)
    return completed.groupby(groups, as_index=False, sort=True).agg(**aggregations)[columns]


def activity_display(summary: pd.DataFrame) -> pd.DataFrame:
    """Use readable labels and show per-metric coverage only when incomplete."""
    display = summary[['application', 'fault_type', 'resource_type', 'runs']].rename(columns={
        'application': 'Application', 'fault_type': 'Fault type',
        'resource_type': 'Resource type', 'runs': 'Runs',
    }).copy()
    for kind, label in ACTIVITY_LABELS.items():
        display[label] = [
            'Unknown' if pd.isna(mean) else
            f'{mean:.2f} ± {std:.2f}' if pd.notna(std) else f'{mean:.2f} ± N/A'
            for mean, std in zip(summary[f'{kind}_mean'], summary[f'{kind}_std'])
        ]
    for kind, label in ACTIVITY_LABELS.items():
        if (summary[f'{kind}_n'] != summary.runs).any():
            display[f'{label}: evaluable runs'] = [
                f'{known}/{total}' for known, total in zip(summary[f'{kind}_n'], summary.runs)
            ]
    return display
