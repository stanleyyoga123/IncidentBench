"""Compact research summaries, using runs as the aggregation unit."""
from collections import Counter
import csv
import json
import math
from statistics import mean, median

from .research_reports import archive_counts


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def semantic(jobs):
    # Penalty failures retain a rubric score but do not have a valid final total.
    valid = [j for j in jobs if j.get('status') in ('succeeded', 'failed')
             and (j.get('alignment') or {}).get('verdict') in ('aligned', 'not_aligned')
             and finite((j.get('rubric') or {}).get('overall_score'))]
    scores = [j['rubric']['overall_score'] for j in valid]
    criteria = {}
    for j in valid:
        for key, item in j['rubric'].get('criteria', {}).items():
            if finite(item.get('score')):
                criteria.setdefault(key, []).append(item['score'])
    return {'exported_jobs': len(jobs), 'evaluable_jobs': len(valid),
            'eligible_final_results': sum(j.get('status') in ('succeeded', 'failed') and isinstance(j.get('result'), dict) and bool(j['result']) for j in jobs),
            'job_statuses': dict(sorted(Counter(str(j.get('status', 'unknown')) for j in jobs).items())),
            'dispositions': dict(sorted(Counter(str((j.get('alignment') or {}).get('reason') or 'unavailable')
                                                for j in jobs if j not in valid).items())),
            'mean_score': mean(scores) if scores else None,
            'criteria': {k: mean(v) for k, v in sorted(criteria.items())},
            'penalized_jobs': sum((j['rubric'].get('penalty_total') or 0) > 0 for j in valid)}



def proxy_checks(op):
    """Explain the existing bin decisions; counts are diagnostics, not replicates."""
    if op.get('measurement_basis') != 'archive_service_recovery_proxy':
        return None
    qualified = [b for b in op.get('intervals', []) if b.get('qualified')]
    limits = op.get('limits') or {}
    counts = Counter()
    workloads = Counter()
    baseline = {(s['namespace'], s['workload']): s for s in op.get('services', [])}
    for b in qualified:
        if finite(b.get('failure_ratio')) and b['failure_ratio'] > limits.get('failure_ratio', math.inf):
            counts['client_failure_ratio'] += 1
        if finite(b.get('successful_rps')) and b['successful_rps'] < limits.get('successful_rps', 0):
            counts['client_throughput'] += 1
        for check in b.get('services', []):
            key = (check['namespace'], check['workload'])
            ref = baseline.get(key, {})
            for name, observed, reference, multiplier, direction in (
                ('service_latency', 'maximum_p95_seconds', 'baseline_p95_time_median_seconds', 'service_latency_multiplier', 1),
                ('service_traffic', 'minimum_rps', 'baseline_rps_time_median', 'service_traffic_fraction', -1)):
                value, base, factor = check.get(observed), ref.get(reference), limits.get(multiplier)
                if all(finite(v) for v in (value, base, factor)) and direction * (value - base * factor) > 0:
                    workloads['/'.join(key) + ':' + name] += 1
    # Per-workload counts can overlap; do not sum into a total failed-bin count.
    return {'qualified_bins': len(qualified),
            'unqualified_bins': len(op.get('intervals', [])) - len(qualified),
            'unhealthy_qualified_bins': sum(not b.get('healthy') for b in qualified),
            'client_checks_failed': dict(sorted(counts.items())),
            'workload_checks_failed': dict(sorted(workloads.items()))}


def build_summary(grades):
    rows = []
    for g in grades:
        r = g['research']; op = r['operational']; harm = op.get('harm') or {}
        base = op.get('baseline') or {}
        throughput = harm.get('successful_rps'); baseline_throughput = base.get('successful_rps')
        retention = throughput / baseline_throughput if finite(throughput) and finite(baseline_throughput) and baseline_throughput > 0 else None
        rows.append({'run': g['run'], 'scenario': g.get('scenario'), 'semantic_status': g['status'],
                     'semantic_reason': g.get('reason'), 'application': r.get('application'),
                     'policy_hash': r['policy_hash'], 'measurement_basis': op.get('measurement_basis'),
                     'operational_status': op['status'], 'operational_reason': op.get('reason'),
                     'proxy_checks': proxy_checks(op),
                     'proxy_recovery_seconds': op.get('proxy_recovery_seconds'),
                     'recovery_schedule_phase': op.get('recovery_schedule_phase'),
                     'client_failure_ratio': harm.get('failure_ratio'),
                     'successful_client_rps': throughput, 'baseline_successful_client_rps': baseline_throughput,
                     'successful_throughput_fraction_of_baseline': retention,
                     'baseline_client_failure_ratio': base.get('failure_ratio'), 'baseline_counter_coverage': base.get('coverage'),
                     'measured_failed_requests': harm.get('failed'), 'measured_seconds': harm.get('measured_seconds'),
                     'counter_coverage': harm.get('coverage'), 'recovery_coverage': op.get('coverage'),
                     'safety': r['safety']['status'], 'execution': r['execution']['status'],
                     **{kind: semantic(g.get(kind + '_jobs', [])) for kind in ('rca', 'remediation')}})
    strata = []
    identities = sorted({(r['policy_hash'], r['measurement_basis'] or 'unknown') for r in rows})
    for policy_hash, basis in identities:
        selected = [r for r in rows if r['policy_hash'] == policy_hash and (r['measurement_basis'] or 'unknown') == basis]
        researches = [g['research'] for g in grades if g['research']['policy_hash'] == policy_hash
                      and (g['research']['operational'].get('measurement_basis') or 'unknown') == basis]
        stats = {}
        for kind in ('rca', 'remediation'):
            values = [r[kind]['mean_score'] for r in selected if r[kind]['mean_score'] is not None]
            criteria = {}
            for r in selected:
                for key, value in r[kind]['criteria'].items():
                    criteria.setdefault(key, []).append(value)
            stats[kind] = {'exported_jobs': sum(r[kind]['exported_jobs'] for r in selected),
                           'evaluable_jobs': sum(r[kind]['evaluable_jobs'] for r in selected),
                           'eligible_final_results': sum(r[kind]['eligible_final_results'] for r in selected),
                           'runs_with_final_results': sum(r[kind]['eligible_final_results'] > 0 for r in selected),
                           'runs_with_scores': len(values), 'run_balanced_mean': mean(values) if values else None,
                           'criteria': {k: {'run_balanced_mean': mean(v), 'runs': len(v)} for k, v in sorted(criteria.items())},
                           'penalized_jobs': sum(r[kind]['penalized_jobs'] for r in selected)}
        times = [r['proxy_recovery_seconds'] for r in selected
                 if r['operational_status'] == 'proxy_recovered' and finite(r['proxy_recovery_seconds'])]
        strata.append({'policy_hash': policy_hash, 'measurement_basis': basis, 'runs': len(selected),
                       'archive_counts': archive_counts(researches), 'semantic': stats,
                       'recovered_only_median_seconds': median(times) if times else None})
    keys = ('model', 'model_revision', 'prompt_version', 'rubric_hash')
    provenance = sorted({tuple(str(g.get('configuration', {}).get(k) or 'unknown') for k in keys) for g in grades})
    return {'schema_version': 1, 'runs': rows, 'strata': strata,
            'judge_provenance': [dict(zip(keys, values)) for values in provenance]}


def number(value, digits=3):
    return 'unknown' if not finite(value) else f'{value:.{digits}f}'


def percent(value):
    return 'unknown' if not finite(value) else '<0.1%' if 0 < value < .001 else f'{100 * value:.1f}%'


def cell(value):
    return str(value if value is not None else 'unknown').replace('|', '\\|').replace('\n', ' ')


def markdown(data):
    lines = ['# Research summary', '',
             f"Available sample: **{len(data['runs'])} archived runs**. Catalogue coverage and representativeness are not established.", '',
             '## At a glance', '',
             'Read service recovery, final-output availability, and semantic quality together. '
             'There is no combined pass score: a good explanation does not establish successful intervention.', '']
    for s in data['strata']:
        a = s['archive_counts']
        lines += [f"### {s['measurement_basis']} ({s['runs']} runs)", '',
                  f"Policy SHA-256: `{s['policy_hash']}`.", '',
                  '| Measure | Result | Interpretation |', '| --- | --- | --- |']
        if s['measurement_basis'] == 'archive_service_recovery_proxy':
            n = a['proxy_recovered'] + a['proxy_unresolved']
            lines += [f"| Service recovery proxy | {a['proxy_recovered']}/{n} ({percent(a['evaluable_recovery_rate'])}) | Assessable degraded runs; descriptive recovery |",
                      f"| Missing-outcome bounds | {percent(a['lower_bound'])}–{percent(a['upper_bound'])} | Denominator {a['recovery_denominator']}; identification bounds, not confidence intervals |",
                      f"| Other outcomes | {a['insufficient_evidence']} insufficient; {a['no_observed_degradation']} no degradation; {a['invalid']} invalid | No-degradation and invalid runs excluded from recovery denominator |",
                      f"| Recovery time | {number(s['recovered_only_median_seconds'], 1)} s | Median among recovered runs only; not overall MTTR |"]
        else:
            lines += ['| Operational assessment | See per-run outcomes below | Separate from archive proxy |']
        for kind, title in [('rca', 'RCA'), ('remediation', 'Remediation')]:
            m = s['semantic'][kind]
            lines += [f"| {title} final results | {m['eligible_final_results']}/{m['exported_jobs']} exported jobs; {m['runs_with_final_results']}/{s['runs']} runs | Succeeded or failed jobs with nonempty final result; independent of judging |",
                      f"| {title} judging coverage | {m['evaluable_jobs']}/{m['exported_jobs']} exported jobs scored; {m['runs_with_scores']}/{s['runs']} runs with scores | Unfinished, missing, skipped and judge-failed outputs unscored |",
                      f"| {title} semantic quality | {number(m['run_balanced_mean'])}/1 | Mean within each scored run, then equal weight per run; {m['runs_with_scores']} runs |"]
        m = s['semantic']['remediation']
        lines += [f"| Remediation penalties | {m['penalized_jobs']}/{m['evaluable_jobs']} scored outputs penalized | Claimed performed actions; not independent execution verification |", '',
                  '**Assessment:** ' + (f"The service proxy recovered in {a['proxy_recovered']} assessable runs and remained unresolved in {a['proxy_unresolved']}. "
                      if s['measurement_basis'] == 'archive_service_recovery_proxy' else '') +
                  f"Remediation quality is observed in {m['runs_with_scores']} of {s['runs']} runs. "
                  'This sample does not establish reliable autonomous remediation or causal benefit.', '']
    lines += ['## Per-run evidence', '',
              'Scores are within-run means. Parentheses show scored/exported jobs. Client measurements include cleanup/recovery when recorded.', '',
              '| Scenario | Operational outcome | RCA score (jobs) | Remediation score (jobs) | Client failures | Successful req/s (% baseline) | Measured seconds | Recovery coverage |',
              '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in data['runs']:
        def score(k):
            return f"{number(r[k]['mean_score'])} ({r[k]['evaluable_jobs']}/{r[k]['exported_jobs']})"
        lines.append('| ' + ' | '.join(map(cell, [r['scenario'], r['operational_status'], score('rca'), score('remediation'),
                                                   percent(r['client_failure_ratio']), number(r['successful_client_rps']) + ' (' + percent(r['successful_throughput_fraction_of_baseline']) + ')',
                                                   number(r['measured_seconds'], 1), percent(r['recovery_coverage'])])) + ' |')
    lines += ['', '## Why the recovery proxy did not qualify', '',
              'Counts below describe existing qualified 30-second bins, not independent experimental repeats. '
              'Checks can overlap. A run needs a sustained healthy streak; whole-incident averages can conceal service-level failures.', '',
              '| Scenario | Unhealthy / qualified bins | Most frequent failed checks (up to three) |',
              '| --- | --- | --- |']
    for r in data['runs']:
        checks = r['proxy_checks']
        if r['operational_status'] != 'proxy_unresolved' or not checks:
            continue
        counts = {**checks['client_checks_failed'], **checks['workload_checks_failed']}
        top = sorted(counts.items(), key=lambda x: (-x[1], x[0]))[:3]
        lines.append('| ' + cell(r['scenario']) + f" | {checks['unhealthy_qualified_bins']}/{checks['qualified_bins']} | "
                     + cell('; '.join(f'{key}: {value}' for key, value in top) or 'See per-bin evidence') + ' |')
    lines += ['', '## Reading and reporting these results', '',
              '- Primary descriptive outcome: service recovery proxy with all outcome counts and denominators.',
              '- Report client failure ratio and successful throughput per run with measured duration and coverage. Unequal-duration counts are not comparable effectiveness scores.',
              '- Secondary outcome: run-balanced LLM scores, alongside scored/exported jobs and runs with scores. Criterion means and run counts are in `research_summary.json`.',
              '- Recovery can reflect native Kubernetes behavior, autoscaling or fault cleanup. Schedule-phase labels do not verify physical fault activity.',
              '- Safety and applied actions require separate evidence. Semantic scores and service recovery alone do not prove safe execution.',
              '- LLM scores are uncalibrated unless independently reviewed. Record model revision, prompt and rubric hashes. Jobs and scrape samples are not independent experimental repeats.',
              '- No causal effect or universal success threshold is assigned. Report scenario coverage before generalizing to the approach.', '',
              '## Missing evidence and provenance', '']
    for r in data['runs']:
        lines.append(f"- `{r['run']}`: safety={r['safety']}; execution={r['execution']}; phase={r['recovery_schedule_phase'] or 'unknown'}. "
                     + cell(r['semantic_reason'] or r['operational_reason'] or ''))
        for kind in ('rca', 'remediation'):
            for reason, count in r[kind]['dispositions'].items():
                lines.append(f"  - {kind}: {count} unscored — {cell(reason)}")
    lines += ['', 'Judge configuration:', '']
    for p in data['judge_provenance']:
        lines.append('- ' + '; '.join(f'{k}=`{v}`' for k, v in p.items()))
    lines += ['', 'Files: `paper_metrics.csv` (one row per run), `research_summary.json` (counts and criterion means), '
              '`incidents.csv/json` (operational results), and `runs/<run>/report.md` (detailed explanations).', '']
    return '\n'.join(lines)


def write_paper_summary(output, grades):
    data = build_summary(grades)
    (output / 'research_summary.json').write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + '\n')
    (output / 'research_summary.md').write_text(markdown(data))
    rows = []
    for r in data['runs']:
        flat = {k: v for k, v in r.items() if k not in ('rca', 'remediation', 'proxy_checks')}
        for kind in ('rca', 'remediation'):
            flat.update({kind + '_' + k: r[kind][k] for k in ('mean_score', 'exported_jobs', 'eligible_final_results', 'evaluable_jobs', 'penalized_jobs')})
        rows.append(flat)
    with (output / 'paper_metrics.csv').open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]) if rows else ['run', 'scenario'])
        writer.writeheader()
        writer.writerows(rows)
    report = output / 'report.md'
    prefix = '[Read the concise research summary](research_summary.md) · [Per-run paper metrics](paper_metrics.csv)\n\n'
    old = report.read_text()
    while old.startswith(prefix):
        old = old[len(prefix):]
    report.write_text(prefix + old)
