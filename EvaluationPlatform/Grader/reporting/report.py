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
from reporting.report_metrics import ReportConfig, aggregate_report, build_report
from reporting.report_analysis import numeric_summaries
from reporting.report_activity import activity_display, activity_summary
from reporting.report_activity_chart import activity_chart

APPLICATIONS = {'sock-shop': 'front-end', 'online-boutique': 'frontend', 'teastore': 'teastore-webui'}


def display_source_path(path: Path) -> str:
    """Describe an input without publishing a local machine's directory tree."""
    try:
        return path.resolve().relative_to(GRADER_ROOT).as_posix()
    except ValueError:
        return f'external input ({path.name})'


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
             f'Archives: `{display_source_path(archives)}`. Grades: `{display_source_path(grades)}`.',
             '### Aggregate metrics (all selected runs)', table(totals, {'metric':'Metric','count':'Count','evaluable':'Evaluable denominator',
                                                   'percent_of_evaluable':'Percent of evaluable'})]
    for kind, title in [('rca', 'RCA'), ('remediation', 'Remediation')]:
        columns = {'scenario':'Scenario', f'{kind}_max_score':'Max score', f'{kind}_average_score':'Average score',
                   f'{kind}_sessions':'Sessions during chaos', f'{kind}_scored_sessions':'Scored sessions',
                   f'{kind}_time_to_first_highest_score_minutes':'Time to first highest score (min)',
                   f'{kind}_timing_status':'Timing status'}
        lines += [f'### {title} metrics per scenario', table(scenarios, columns)]
    lines += ['### Baseline reference', table(scenarios, {'scenario':'Scenario','baseline_p95_seconds':'P95 (s)',
                                                       'baseline_5xx_rps':'5xx (requests/s)'})]
    columns = {'scenario':'Scenario', 'best_p95_seconds':'P95 (s)',
               'best_p95_seconds_difference':'P95 difference (s)',
               'best_p95_seconds_change_percent':'P95 change (%)',
               'best_5xx_rps':'5xx (requests/s)', 'best_5xx_rps_difference':'5xx difference (requests/s)',
               'best_5xx_rps_change_percent':'5xx change (%)', 'best_holistic_pass':'Within tolerance'}
    lines += ['### Best rolling window versus baseline', table(scenarios, columns)]
    lines += ['### Window evidence and missing data', table(scenarios, {
        'scenario':'Scenario','window_status':'Window status','window_reason':'Reason',
        'best_window_start':'Best start (UTC)','best_window_end':'Best end (UTC)',
        'baseline_5xx_imputed_samples':'Baseline imputed 5xx samples',
        'best_5xx_imputed_samples':'Best imputed 5xx samples'}),
        '### Attempts and exclusions', table(all_runs, {
            'scenario':'Scenario','run':'Run','selected':'Selected','archive_status':'Run status',
            'grade_status':'Grade status','time_scope_status':'Chaos boundaries',
            'rca_exported_sessions':'Exported RCA','rca_excluded_sessions':'Excluded RCA',
            'remediation_exported_sessions':'Exported remediation','remediation_excluded_sessions':'Excluded remediation'})]
    return '\n\n'.join(lines), totals, all_runs, scenarios, jobs


def comparison_chart(summaries, path=None):
    """Plot application rates with their evaluable counts beside each bar."""
    import matplotlib.pyplot as plt

    metrics = summaries['semantic']
    apps = sorted(app for app in metrics.Application.drop_duplicates() if app != 'Pooled total')
    labels = [('Scenarios/runs with successful RCA', 'RCA scenario'),
              ('Scenarios/runs with successful REMEDIATION', 'Remediation scenario'),
              ('Holistic performance within tolerance (best window)', 'Best window')]
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    colors = ['#2878a8', '#c35b43', '#41966d']
    for ax, group in zip(axes, (labels[:2], labels[2:])):
        for index, app in enumerate(apps):
            for metric_index, (metric, short) in enumerate(group):
                matching = metrics[(metrics.Application == app) & (metrics.Metric == metric)]
                y = metric_index * (len(apps) + 1) + index
                if matching.empty or not matching.iloc[0].Evaluable:
                    ax.text(1, y, 'Unknown (n=0)', va='center', fontsize=9)
                    continue
                row = matching.iloc[0]
                ax.barh(y, row.Percent, color=colors[index % len(colors)])
                ax.text(min(row.Percent + 1, 83), y, f'{row.Success}/{row.Evaluable}',
                        va='center', fontsize=9)
        ax.set_yticks([m * (len(apps) + 1) + a for m in range(len(group)) for a in range(len(apps))],
                      [f'{short}: {app}' for _, short in group for app in apps])
        ax.set_xlim(0, 115)
        ax.set_xlabel('Successful / evaluable (%)')
        ax.grid(axis='x', alpha=.2)
    axes[0].set_title('Semantic scenario attainment')
    axes[1].set_title('Frontend window tolerance')
    fig.tight_layout()
    if path is not None:
        fig.savefig(path, dpi=160, bbox_inches='tight')
    return fig


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--results-dir', type=Path, default=GRADER_ROOT/'results')
    p.add_argument('--grades-dir', type=Path, default=GRADER_ROOT/'output'/'grades')
    p.add_argument('--output', type=Path, default=GRADER_ROOT/'output'/'report'/'report.md')
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
             '- Best minimizes P95 among windows satisfying the 5xx ceiling. P95 and 5xx share the selected window; a favorable window does not establish sustained recovery.\n'
             '- P95 is a time average of archived rolling percentiles. Missing 5xx samples may be imputed at recorded traffic timestamps; counts are disclosed.\n'
             '- Holistic totals include completed, evaluable runs only. Unknown values are never zero or success. Session and scenario totals have separate denominators.\n'
             '- This script reads existing grades and recomputes performance offline. Missing grades leave semantic scores unknown; no model calls occur.\n'
             '- Archives are discovered recursively, including preserved local campaigns. The attempts table records which runs were selected.']
    sections, aggregates = [], []
    analysis_runs, analysis_selected, analysis_jobs = [], [], []
    for name in dict.fromkeys(args.apps):
        archives, grades = args.results_dir/name, args.grades_dir/name
        if not list(archives.rglob('metadata.json')) and not list(grades.glob('runs/*/grade.json')):
            sections.append(f'## {name}\n\n_No archived runs or grades available yet._')
            continue
        section, totals, app_runs, app_selected, app_jobs = application_report(name, grades, archives,
                                             replace(config, workload=APPLICATIONS[name], namespace=name))
        sections.append(section); aggregates.append(totals)
        for frame in (app_runs, app_selected, app_jobs):
            frame.insert(0, 'application', name)
        analysis_runs.append(app_runs)
        analysis_selected.append(app_selected)
        analysis_jobs.append(app_jobs)
    if aggregates:
        totals = pd.concat(aggregates).groupby('metric', sort=False, as_index=False)[['count','evaluable']].sum()
        totals['percent_of_evaluable'] = totals['count']/totals['evaluable'].replace(0, float('nan'))*100
        lines += ['## Aggregate metrics across all selected runs',
                  'This all-selected-run aggregate includes selected technical runs that did not complete. The completed-run analysis below uses the primary cohort.',
                  table(totals)]
        summaries = numeric_summaries(pd.concat(analysis_runs, ignore_index=True),
            pd.concat(analysis_selected, ignore_index=True),
            pd.concat(analysis_jobs, ignore_index=True), config)
        chart_path = args.output.with_name(args.output.stem + '-applications.png')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        figure = comparison_chart(summaries, chart_path)
        import matplotlib.pyplot as plt
        plt.close(figure)
        lines += ['## Completed-run analysis',
                  'The tables below use selected completed runs only. Failed or incomplete selected runs remain in the exclusion audit. '
                  'Fractions count success over evaluable runs or sessions; unknown scores do not enter semantic denominators. '
                  'A run completes only when metadata or run-status reports completion, its execution return code is zero or absent, '
                  'and neither source reports failure or interruption.',
                  f'![Application comparison]({chart_path.name})']
        activity = activity_summary(pd.concat(analysis_selected, ignore_index=True))
        activity_path = args.output.with_name(args.output.stem + '-activity.png')
        activity_svg = activity_path.with_suffix('.svg')
        figure = activity_chart(activity)
        figure.savefig(activity_path, dpi=180, bbox_inches='tight')
        figure.savefig(activity_svg, bbox_inches='tight')
        plt.close(figure)
        lines += ['### Workflow activity by application, fault type, and resource type',
                  'Per-run mean ± sample SD for selected completed runs under the configured repeat policy, including measured zeros. '
                  'SD measures variation, not standard error; one evaluable run gives SD N/A. '
                  'Anomalies count all exported detection events by detected_at; RCA/remediation count succeeded and failed attempts '
                  'by completed_at, regardless of grading. Chaos starts are inclusive and ends exclusive, capped at duration or earlier cleanup. '
                  'Fault/resource types describe the injected scenario. Missing exports/boundaries or invalid eligible timestamps leave '
                  'counts unknown; additional evaluable-run columns disclose incomplete coverage. '
                  'Activity counts do not establish semantic quality or recovery.',
                  f'![Workflow activity comparison]({activity_path.name})',
                  f'[Download vector chart]({activity_svg.name})',
                  table(activity_display(activity))]
        for key, title in [('cohort', 'Cohort'), ('semantic', 'Semantic success and window tolerance'),
                           ('scores', 'Score means'), ('sessions', 'Sessions and time to maximum score'),
                           ('performance', 'Window performance'), ('joint', 'Semantic success versus best-window tolerance'),
                           ('families', 'Fault-family outcomes'), ('family_app', 'Fault families by application'),
                           ('exclusions', 'Selected technical exclusions')]:
            lines += [f'### {title}', table(summaries[key])]
        lines += ['Scenario means weight each evaluable run equally; pooled session means weight each scored output equally. '
                  'Time quartiles use runs with a scored maximum and available completion time. '
                  'Known sessions sum runs with a measured chaos-only count; “Session counts known / runs” exposes missing run counts. '
                  'Best-window P95 medians exclude runs with no admissible best window; those runs remain known tolerance failures. '
                  'Fault families are parsed from scenario names. These descriptive comparisons do not establish agent-caused recovery.']
    lines += sections
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n\n'.join(lines)+'\n', encoding='utf-8')
    print(f'Report written: {args.output.resolve()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
