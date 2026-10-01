"""Descriptive summaries for the selected, completed experiment cohort."""
from __future__ import annotations

import pandas as pd

from reporting.report_metrics import ReportConfig, aggregate_report

FAMILIES = ("Node CPU", "Node delay", "Node packet loss", "Node memory",
            "Pod CPU headroom", "Pod bandwidth", "Pod capacity loss", "Pod CPU", "Pod memory")


def fault_family(scenario: str) -> str:
    if '-node-' in scenario:
        for key, label in (('-cpu-', 'Node CPU'), ('-delay-', 'Node delay'),
                           ('-loss-', 'Node packet loss'), ('-memory-', 'Node memory')):
            if key in scenario:
                return label
    if '-pod-' in scenario:
        for key, label in (('-cpu-headroom-', 'Pod CPU headroom'),
                           ('-bandwidth-', 'Pod bandwidth'), ('-capacity-loss-', 'Pod capacity loss'),
                           ('-cpu-', 'Pod CPU'), ('-memory-', 'Pod memory')):
            if key in scenario:
                return label
    return "Other / unclassified"


def ratio(flags: pd.Series) -> str:
    known = flags.dropna()
    return f"{int(known.astype(bool).sum())}/{len(known)}" if len(known) else "—"


def median_or_nan(values: pd.Series) -> float:
    return values.median() if values.notna().any() else float('nan')


def numeric_summaries(all_runs: pd.DataFrame, selected: pd.DataFrame,
                      jobs: pd.DataFrame, config: ReportConfig) -> dict[str, pd.DataFrame]:
    """Calculate analysis.md-style numbers from current selected completed runs."""
    completed = selected.loc[selected.run_completed].copy()
    completed_keys = pd.MultiIndex.from_frame(completed[['application', 'run']])
    job_keys = pd.MultiIndex.from_frame(jobs[['application', 'run']])
    included_jobs = jobs.loc[job_keys.isin(completed_keys) & jobs.included_in_chaos].copy()
    cohort_rows, semantic_rows, score_rows, session_rows, performance_rows = [], [], [], [], []
    for application in selected.application.drop_duplicates():
        attempts = all_runs.loc[all_runs.application == application]
        chosen = selected.loc[selected.application == application]
        runs = completed.loc[completed.application == application]
        app_jobs = included_jobs.loc[included_jobs.application == application]
        cohort_rows.append({"Application": application, "Attempts": len(attempts),
                            "Selected scenarios/runs": len(chosen), "Completed analyzed": len(runs),
                            "Selected technical exclusions": len(chosen) - len(runs)})
        aggregate_jobs = app_jobs.copy()
        aggregate_jobs['selected'] = True
        counts = aggregate_report(runs, aggregate_jobs, config)
        for row in counts.itertuples(index=False):
            semantic_rows.append({"Application": application, "Metric": row.metric,
                                  "Success": int(row.count), "Evaluable": int(row.evaluable),
                                  "Percent": row.percent_of_evaluable})
        for kind in ("rca", "remediation"):
            scoped = app_jobs.loc[app_jobs.kind == kind]
            scored = scoped.score.dropna()
            maxima = runs[f"{kind}_max_score"].dropna()
            means = runs[f"{kind}_average_score"].dropna()
            score_rows.append({"Application": application, "Output": kind,
                               "Mean scenario maximum": maxima.mean(),
                               "Mean scenario mean": means.mean(),
                               "Pooled session mean": scored.mean()})
            sessions = runs[f"{kind}_sessions"].dropna()
            times = runs[f"{kind}_time_to_first_highest_score_minutes"].dropna()
            session_rows.append({"Application": application, "Output": kind,
                                 "Known sessions": sessions.sum(min_count=1),
                                 "Session counts known / runs": f'{len(sessions)}/{len(runs)}',
                                 "Scored": len(scored),
                                 "Sessions median": median_or_nan(sessions), "Sessions min": sessions.min(),
                                 "Sessions max": sessions.max(), "Time n": len(times),
                                 "Time median (min)": median_or_nan(times), "Time Q1": times.quantile(.25),
                                 "Time Q3": times.quantile(.75), "Time min": times.min(),
                                 "Time max": times.max()})
        performance_rows.append({"Application": application,
                                 "Best tolerance": ratio(runs.best_holistic_pass),
                                 "Median best P95 change (%)": median_or_nan(runs.best_p95_seconds_change_percent),
                                 "Best P95 n": runs.best_p95_seconds_change_percent.count()})
    completed['Family'] = completed.scenario.map(fault_family)
    outcomes = {'RCA success': 'rca_has_successful_output',
                'Remediation success': 'remediation_has_successful_output',
                'Best tolerance': 'best_holistic_pass'}
    family_rows = []
    for keys, frame in completed.groupby(['Family', 'application'], sort=False):
        family, application = keys
        family_rows.append({"Family": family, "Application": application, "Runs": len(frame),
                            **{label: ratio(frame[column]) for label, column in outcomes.items()}})
    observed_families = set(completed.Family)
    present_pairs = {(row['Family'], row['Application']) for row in family_rows}
    for family in observed_families:
        for application in selected.application.drop_duplicates():
            if (family, application) not in present_pairs:
                family_rows.append({"Family": family, "Application": application, "Runs": 0,
                                    **{label: '—' for label in outcomes}})
    family_columns = ['Family', 'Application', 'Runs', *outcomes]
    family_app = pd.DataFrame(family_rows, columns=family_columns)
    family_order = [*FAMILIES, 'Other / unclassified']
    if not family_app.empty:
        family_app['Family'] = pd.Categorical(family_app.Family, categories=family_order, ordered=True)
        family_app = family_app.sort_values(['Family', 'Application']).reset_index(drop=True)
        family_app['Family'] = family_app.Family.astype(str)
    family_total_rows = []
    for family, frame in completed.groupby('Family', sort=False):
        family_total_rows.append({"Family": family, "Runs": len(frame),
                                  **{label: ratio(frame[column]) for label, column in outcomes.items()}})
    family_totals = pd.DataFrame(family_total_rows, columns=['Family', 'Runs', *outcomes])
    if not family_totals.empty:
        family_totals['Family'] = pd.Categorical(family_totals.Family, categories=family_order, ordered=True)
        family_totals = family_totals.sort_values('Family').reset_index(drop=True)
        family_totals['Family'] = family_totals.Family.astype(str)
    joint_rows = []
    for kind in ('rca', 'remediation'):
        flag = f'{kind}_has_successful_output'
        for success in (True, False):
            group = completed.loc[completed[flag].notna() & (completed[flag] == success)]
            joint_rows.append({"Output": kind, "Semantic success": success,
                               "Best passes": int(group.best_holistic_pass.eq(True).sum()),
                               "Best fails": int(group.best_holistic_pass.eq(False).sum()),
                               "Best unknown": int(group.best_holistic_pass.isna().sum()),
                               "Total": len(group)})
    exclusions = selected.loc[~selected.run_completed,
                              ['application', 'scenario', 'run', 'archive_status', 'grade_status']].copy()
    cohort = pd.DataFrame(cohort_rows)
    if not cohort.empty:
        cohort.loc[len(cohort)] = ['Total', *cohort.iloc[:, 1:].sum().tolist()]
    semantic = pd.DataFrame(semantic_rows)
    if not semantic.empty:
        pooled = semantic.groupby('Metric', sort=False, as_index=False)[['Success', 'Evaluable']].sum()
        pooled.insert(0, 'Application', 'Pooled total')
        pooled['Percent'] = 100 * pooled.Success / pooled.Evaluable.replace(0, float('nan'))
        semantic = pd.concat([semantic, pooled], ignore_index=True)
    performance = pd.DataFrame(performance_rows)
    if not performance.empty:
        performance.loc[len(performance)] = {
            'Application': 'Pooled total',
            'Best tolerance': ratio(completed.best_holistic_pass),
            'Median best P95 change (%)': median_or_nan(completed.best_p95_seconds_change_percent),
            'Best P95 n': completed.best_p95_seconds_change_percent.count(),
        }
    return {"cohort": cohort, "semantic": semantic,
            "scores": pd.DataFrame(score_rows), "sessions": pd.DataFrame(session_rows),
            "performance": performance, "joint": pd.DataFrame(joint_rows),
            "families": family_totals, "family_app": family_app, "exclusions": exclusions}
