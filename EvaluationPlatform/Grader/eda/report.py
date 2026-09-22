#!/usr/bin/env python3
"""Generate an offline Markdown report from application archives and grades."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import sys

GRADER_ROOT = Path(__file__).resolve().parents[1]
if str(GRADER_ROOT) not in sys.path:
    sys.path.insert(0, str(GRADER_ROOT))

import pandas as pd
from eda.report_metrics import ReportConfig, aggregate_report, build_report

APPLICATIONS = {'sock-shop': 'front-end', 'online-boutique': 'frontend', 'teastore': 'teastore-webui'}


def cell(value):
    if pd.isna(value):
        return 'Unknown'
    if isinstance(value, bool):
        return 'Yes' if value else 'No'
    if isinstance(value, float):
        return f'{value:.4f}'
    return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\\', '\\\\').replace('|', '\\|').replace('\n', '<br>')


def table(frame, columns=None):
    if columns:
        frame = frame[list(columns)].rename(columns=columns)
    if frame.empty:
        return '_No rows available._'
    lines = ['| ' + ' | '.join(map(cell, frame.columns)) + ' |',
             '| ' + ' | '.join(['---'] * len(frame.columns)) + ' |']
    lines.extend('| ' + ' | '.join(map(cell, row)) + ' |' for row in frame.itertuples(index=False, name=None))
    return '\n'.join(lines)


def application_report(name, grades, archives, config):
    all_runs, scenarios, jobs = build_report(grades, archives, config, include_ungraded=True)
    totals = aggregate_report(scenarios, jobs, config)
    lines = [f'## {name}', f'Workload: `{config.workload}`; namespace: `{config.namespace}`. '
             f'{len(all_runs)} attempts; {len(scenarios)} selected scenario/run rows; '
             f'{int(scenarios.run_completed.sum())} completed selected runs.',
             f'Archives: `{archives}`. Grades: `{grades}`.',
             '### Aggregate metrics', table(totals, {'metric':'Metric','count':'Count','evaluable':'Evaluable denominator',
                                                   'percent_of_evaluable':'Percent of evaluable'})]
    for kind, title in [('rca', 'RCA'), ('remediation', 'Remediation')]:
        columns = {'scenario':'Scenario', f'{kind}_max_score':'Max score', f'{kind}_average_score':'Average score',
                   f'{kind}_sessions':'Sessions during chaos', f'{kind}_scored_sessions':'Scored sessions',
                   f'{kind}_time_to_first_highest_score_minutes':'Time to first highest score (min)',
                   f'{kind}_timing_status':'Timing status'}
        lines += [f'### {title} metrics per scenario', table(scenarios, columns)]
    lines += ['### Baseline reference', table(scenarios, {'scenario':'Scenario','baseline_p95_seconds':'P95 (s)',
                                                       'baseline_5xx_rps':'5xx (requests/s)'})]
    for kind in ('best', 'worst'):
        columns = {'scenario':'Scenario', f'{kind}_p95_seconds':'P95 (s)',
                   f'{kind}_p95_seconds_difference':'P95 difference (s)',
                   f'{kind}_p95_seconds_change_percent':'P95 change (%)',
                   f'{kind}_5xx_rps':'5xx (requests/s)', f'{kind}_5xx_rps_difference':'5xx difference (requests/s)',
                   f'{kind}_5xx_rps_change_percent':'5xx change (%)', f'{kind}_holistic_pass':'Within tolerance'}
        lines += [f'### {kind.title()} rolling window versus baseline', table(scenarios, columns)]
    lines += ['### Window evidence and missing data', table(scenarios, {
        'scenario':'Scenario','window_status':'Window status','window_reason':'Reason',
        'best_window_start':'Best start (UTC)','best_window_end':'Best end (UTC)',
        'worst_window_start':'Worst start (UTC)','worst_window_end':'Worst end (UTC)',
        'baseline_5xx_imputed_samples':'Baseline imputed 5xx samples',
        'best_5xx_imputed_samples':'Best imputed 5xx samples','worst_5xx_imputed_samples':'Worst imputed 5xx samples'}),
        '### Attempts and exclusions', table(all_runs, {
            'scenario':'Scenario','run':'Run','selected':'Selected','archive_status':'Run status',
            'grade_status':'Grade status','time_scope_status':'Chaos boundaries',
            'rca_exported_sessions':'Exported RCA','rca_excluded_sessions':'Excluded RCA',
            'remediation_exported_sessions':'Exported remediation','remediation_excluded_sessions':'Excluded remediation'})]
    return '\n\n'.join(lines), totals


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results-dir', type=Path, default=GRADER_ROOT/'results')
    p.add_argument('--grades-dir', type=Path, default=GRADER_ROOT/'grades')
    p.add_argument('--output', type=Path, default=Path(__file__).resolve().with_suffix('.md'))
    p.add_argument('--apps', nargs='+', choices=APPLICATIONS, default=list(APPLICATIONS))
    p.add_argument('--window-minutes', type=float, default=5)
    p.add_argument('--score-threshold', type=float, default=.8)
    p.add_argument('--p95-change-limit', type=float, default=.2, help='Fraction, e.g. 0.20 for 20%%')
    p.add_argument('--max-5xx-rps', type=float, default=.5)
    p.add_argument('--baseline-ignore-minutes', type=float, default=5)
    p.add_argument('--repeat-policy', choices=['latest_completed_else_latest','all_runs'], default='latest_completed_else_latest')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    config = ReportConfig(score_threshold=args.score_threshold, p95_change_limit=args.p95_change_limit,
                          max_5xx_rps=args.max_5xx_rps, window_minutes=args.window_minutes,
                          baseline_ignore_minutes=args.baseline_ignore_minutes, repeat_policy=args.repeat_policy)
    lines = ['# Experiment metrics report', f'Generated {datetime.now(timezone.utc).isoformat()}.',
             '## Definitions and configuration',
             f'- Rolling window: **{config.window_minutes:g} minutes**; initial baseline exclusion: **{config.baseline_ignore_minutes:g} minutes**.\n'
             f'- Successful output: score **> {config.score_threshold:g}**.\n'
             f'- Holistic tolerance: P95 increase **< {config.p95_change_limit*100:g}%**, with 5xx **≤ {config.max_5xx_rps:g} requests/s**.\n'
             f'- Repeat selection: `{config.repeat_policy}`. Latest completed attempt per scenario is the default; otherwise the latest attempt.\n'
             '- Only outputs completed within recorded chaos intervals contribute to scores, counts and timing. Missing boundaries/timestamps are excluded.\n'
             '- Time to first good output means earliest completion among the highest-scoring outputs, measured from recorded chaos start.\n'
             '- Differences are window minus baseline; negative means a decrease. Percentage changes are unknown for zero baselines.\n'
             '- Best minimizes P95 among windows satisfying the 5xx ceiling; worst maximizes P95 without that ceiling. P95 and 5xx share the selected window.\n'
             '- P95 is a time average of archived rolling percentiles. Missing 5xx samples may be imputed at recorded traffic timestamps; counts are disclosed.\n'
             '- Holistic totals include completed, evaluable runs only. Unknown values are never zero or success. Session and scenario totals have separate denominators.\n'
             '- This script reads existing grades and recomputes performance offline. Missing grades leave semantic scores unknown; no model calls occur.\n'
             '- Archives are discovered recursively, including preserved local campaigns. The attempts table records which runs were selected.']
    sections, aggregates = [], []
    for name in dict.fromkeys(args.apps):
        archives, grades = args.results_dir/name, args.grades_dir/name
        if not list(archives.rglob('metadata.json')) and not list(grades.glob('runs/*/grade.json')):
            sections.append(f'## {name}\n\n_No archived runs or grades available yet._')
            continue
        section, totals = application_report(name, grades, archives,
                                             replace(config, workload=APPLICATIONS[name], namespace=name))
        sections.append(section); aggregates.append(totals)
    if aggregates:
        totals = pd.concat(aggregates).groupby('metric', sort=False, as_index=False)[['count','evaluable']].sum()
        totals['percent_of_evaluable'] = totals['count']/totals['evaluable'].replace(0, float('nan'))*100
        lines += ['## Aggregate metrics across all applications', table(totals)]
    lines += sections
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n\n'.join(lines)+'\n', encoding='utf-8')
    print(f'Report written: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
