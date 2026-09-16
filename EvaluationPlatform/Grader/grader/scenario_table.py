"""One row per archived run, pairing latency and errors in one selected window."""
from __future__ import annotations

import csv
import json
from statistics import mean

from .paper_summary import finite


COLUMNS = (
    ('scenario', 'Scenario'),
    ('max_rca_score', 'Max RCA score across sessions'),
    ('max_remediation_score', 'Max Remediation Score across sessions'),
    ('baseline_p95_seconds', 'Mean Baseline p95 response time (s)'),
    ('baseline_5xx_rps', 'Mean Baseline 5xx rate (requests/s)'),
    ('best_p95_seconds', 'Best rolling window p95 response time (s)'),
    ('best_5xx_rps', 'Best rolling window 5xx rate (requests/s)'),
    ('window_location', 'Window location'),
    ('rca_sessions', 'Number of RCA sessions'),
    ('remediation_sessions', 'Number of Remediation sessions'),
    ('mean_rca_score', 'Avg whole RCA job score'),
    ('mean_remediation_score', 'Avg whole Remediation job score'),
    ('worst_p95_seconds', 'Worst rolling window p95 response time (s)'),
    ('worst_5xx_rps', 'Worst rolling window 5xx rate (requests/s)'),
    ('worst_window_location', 'Worst window location'),
    ('baseline_5xx_imputed_samples', 'Baseline 5xx imputed samples'),
    ('best_5xx_imputed_samples', 'Best window 5xx imputed samples'),
    ('worst_5xx_imputed_samples', 'Worst window 5xx imputed samples'),
)


def score_summary(jobs):
    scores = [(job.get('rubric') or {}).get('overall_score') for job in jobs
              if job.get('status') in ('succeeded', 'failed')
              and (job.get('alignment') or {}).get('verdict') in ('aligned', 'not_aligned')]
    scores = [value for value in scores if finite(value)]
    return {'count': len(jobs), 'scored': len(scores),
            'max': max(scores) if scores else None,
            'mean': mean(scores) if scores else None}


def table_row(grade):
    paired = grade.get('paired_window') or {}
    baseline = paired.get('baseline') or {}
    best = paired.get('best') or {}
    worst = paired.get('worst') or {}
    rca = score_summary(grade.get('rca_jobs') or [])
    remediation = score_summary(grade.get('remediation_jobs') or [])
    return {
        'scenario': grade.get('scenario') or grade['run'],
        'max_rca_score': rca['max'], 'max_remediation_score': remediation['max'],
        'baseline_p95_seconds': baseline.get('p95_seconds'),
        'baseline_5xx_rps': baseline.get('http_5xx_rps'),
        'best_p95_seconds': best.get('p95_seconds'), 'best_5xx_rps': best.get('http_5xx_rps'),
        'window_location': f"{best['start']} → {best['end']}" if best else None,
        'worst_p95_seconds': worst.get('p95_seconds'), 'worst_5xx_rps': worst.get('http_5xx_rps'),
        'worst_window_location': f"{worst['start']} → {worst['end']}" if worst else None,
        'baseline_5xx_imputed_samples': baseline.get('http_5xx_imputed_samples', 0),
        'best_5xx_imputed_samples': best.get('http_5xx_imputed_samples', 0),
        'worst_5xx_imputed_samples': worst.get('http_5xx_imputed_samples', 0),
        'rca_sessions': rca['count'], 'remediation_sessions': remediation['count'],
        'mean_rca_score': rca['mean'], 'mean_remediation_score': remediation['mean'],
    }


def write_scenario_table(output, grades, *, csv_only=False):
    """Write the original 12 columns plus paired worst-window values; keep denominators and provenance alongside."""
    output.mkdir(parents=True, exist_ok=True)
    rows = [table_row(grade) for grade in grades]
    with (output / 'scenario_table.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=[title for _, title in COLUMNS])
        writer.writeheader()
        writer.writerows({title: row[key] for key, title in COLUMNS} for row in rows)
    if csv_only:
        return
    notes = [
        'One row per archived run; repeated scenario names remain separate experimental runs.',
        'Scores range from 0 to 1. Maxima and means use scored succeeded and failed jobs; remediation scores include penalties. Missing scores are excluded, not replaced with zero.',
        'Session counts include every exported job, including running and result-less jobs. Scored counts are recorded in scenario_table.json.',
        'P95 is a time average of archived rolling P95 samples, not a pooled request percentile. HTTP 5xx is requests/second, not a percentage.',
        'Baseline excludes its initial five minutes by default, configurable with --baseline-ignore-minutes. Missing baseline values do not suppress covered chaos windows.',
        'Best minimizes mean P95 subject to the configured 5xx ceiling. Worst maximizes mean P95 over all covered windows, without that ceiling. Ties use earliest time.',
        'Each pair of best/worst-window metrics come from the same complete window within one recorded chaos interval, before cleanup. These descriptive measurements do not change recovery scoring.',
    ]
    def cell(value):
        if value is None:
            return 'unknown'
        if isinstance(value, float):
            return f'{value:.6g}'
        return str(value).replace('|', '\\|').replace('\n', ' ')
    lines = ['# Scenario table', '', *notes, '',
             '| ' + ' | '.join(title for _, title in COLUMNS) + ' |',
             '| ' + ' | '.join('---' for _ in COLUMNS) + ' |']
    lines.extend('| ' + ' | '.join(cell(row[key]) for key, _ in COLUMNS) + ' |' for row in rows)
    lines += ['', '## Measurement provenance', '']
    provenance = []
    for grade, row in zip(grades, rows):
        paired = grade.get('paired_window') or {}
        provenance.append({'run': grade['run'], 'row': row, 'paired_window': paired,
                           'rca': score_summary(grade.get('rca_jobs') or []),
                           'remediation': score_summary(grade.get('remediation_jobs') or [])})
        lines.append(f"- {cell(grade['run'])}: {cell(paired.get('description'))}; "
                     f"status={cell(paired.get('status'))}; {cell(paired.get('reason') or paired.get('baseline_reason') or 'measurements available')}.")
    (output / 'scenario_table.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    (output / 'scenario_table.json').write_text(json.dumps({'schema_version': 1, 'notes': notes, 'runs': provenance},
                                                         indent=2, sort_keys=True) + '\n', encoding='utf-8')
