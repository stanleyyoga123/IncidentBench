"""Incident denominators and paired comparisons; job scores are secondary."""
import csv
import json
import random
from collections import defaultdict
from statistics import mean


def bounds(items):
    incidents = [x for x in items if x.get('experiment_type', 'incident') == 'incident']
    eligible = [x for x in incidents if x['operational']['status'] != 'invalid']
    yes = sum(x['safe_recovery'] is True for x in eligible)
    unknown = sum(x['safe_recovery'] is None for x in eligible)
    n = len(eligible)
    return {'runs': len(items), 'non_incident_controls': len(items) - len(incidents), 'invalid': len(incidents) - n, 'eligible': n,
            'safe_recovered': yes, 'known_unsuccessful': n - yes - unknown, 'unknown': unknown,
            'lower_bound': yes / n if n else None, 'upper_bound': (yes + unknown) / n if n else None}


def archive_counts(items):
    rows = [r for r in items if r['operational'].get('measurement_basis') == 'archive_service_recovery_proxy'
            and r.get('experiment_type', 'incident') == 'incident']
    statuses = [r['operational']['status'] for r in rows]
    recovered = statuses.count('proxy_recovered')
    unresolved = statuses.count('proxy_unresolved')
    unknown = statuses.count('not_evaluable')
    maintained = statuses.count('no_observed_degradation')
    n = recovered + unresolved + unknown
    return {'runs': len(rows), 'proxy_recovered': recovered, 'proxy_unresolved': unresolved,
            'no_observed_degradation': maintained, 'insufficient_evidence': unknown,
            'invalid': statuses.count('invalid'), 'recovery_denominator': n,
            'evaluable_recovery_rate': recovered/(recovered+unresolved) if recovered+unresolved else None,
            'lower_bound': recovered/n if n else None, 'upper_bound': (recovered+unknown)/n if n else None,
            'interpretation': 'descriptive service recovery proxy; no-degradation cases excluded from recovery denominator; not verified safe recovery or causal benefit'}


def bootstrap(values, samples, seed):
    if len(values) < 2:
        return None
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(values, k=len(values))) for _ in range(samples))
    return [means[int(.025 * (len(means) - 1))], means[int(.975 * (len(means) - 1))]]


def paired(grades):
    groups = defaultdict(list)
    for g in grades:
        r = g['research']; e = r.get('experiment', {})
        if e.get('pair_id'):
            groups[e['pair_id']].append((g, r, e))
    pairs, excluded = [], []
    for pair_id, rows in sorted(groups.items()):
        if len(rows) != 2 or {e.get('agents_enabled') for _, _, e in rows} != {True, False}:
            excluded.append({'pair_id': pair_id, 'reason': 'requires exactly one treatment and control'})
            continue
        rows.sort(key=lambda x: not x[2]['agents_enabled'])
        (ga, a, ea), (gb, b, eb) = rows
        required = ('match_hash', 'deadline_seconds', 'lesson_state', 'application_revision')
        if (any(ea.get(k) is None or ea.get(k) != eb.get(k) for k in required) or
                a['policy_hash'] != b['policy_hash'] or a.get('application') != b.get('application') or
                ga.get('scenario') != gb.get('scenario') or
                any(x['operational']['status'] in ('invalid', 'not_evaluable') for x in (a, b))):
            excluded.append({'pair_id': pair_id, 'reason': 'mismatched configuration, policy, or incomplete observation'})
            continue
        def difference(fn):
            av, bv = fn(a), fn(b)
            return av - bv if av is not None and bv is not None else None
        pairs.append({'pair_id': pair_id, 'application': a.get('application'), 'scenario': ga.get('scenario'),
                      'safe_recovery_difference': difference(lambda x: int(x['safe_recovery']) if x['safe_recovery'] is not None else None),
                      'measured_failed_requests_difference': difference(lambda x: x['operational']['harm']['failed'] if x['operational']['harm']['coverage_adequate'] and abs(a['operational']['harm']['measured_seconds'] - b['operational']['harm']['measured_seconds']) < .01 else None),
                      # Censor at the common deadline instead of averaging recovered cases only.
                      'restricted_recovery_seconds_difference': difference(lambda x: x['operational'].get('recovery_seconds') if x['operational'].get('recovered') else x['operational'].get('observation_seconds'))})
    grouped = defaultdict(list)
    for pair in pairs:
        grouped[pair['application'], pair['scenario']].append(pair)
    effects = []
    p = grades[0]['research']['policy'] if grades else {'bootstrap_samples': 2000, 'bootstrap_seed': 20260915}
    for (app, scenario), rows in sorted(grouped.items()):
        for metric in ('safe_recovery_difference', 'measured_failed_requests_difference', 'restricted_recovery_seconds_difference'):
            values = [r[metric] for r in rows if r[metric] is not None]
            effects.append({'application': app, 'scenario': scenario, 'metric': metric, 'pairs': len(values),
                            'mean': mean(values) if values else None,
                            'ci95': bootstrap(values, p['bootstrap_samples'], p['bootstrap_seed'])})
    macro = {}
    for metric in {e['metric'] for e in effects}:
        apps = defaultdict(list)
        for e in effects:
            if e['metric'] == metric and e['mean'] is not None:
                apps[e['application']].append(e['mean'])
        macro[metric] = mean(mean(v) for v in apps.values()) if apps else None
    return {'pairs': pairs, 'excluded': excluded, 'effects': effects, 'macro_effects': macro,
            'sign': 'treatment minus control; positive favors treatment only for recovery probability'}


def aggregate(grades):
    hashes = {g['research']['policy_hash'] for g in grades}
    if len(hashes) > 1:
        counts = bounds([g['research'] for g in grades])
        counts['lower_bound'] = counts['upper_bound'] = None
        archive = archive_counts([g['research'] for g in grades])
        archive['lower_bound'] = archive['upper_bound'] = archive['evaluable_recovery_rate'] = None
        return {'schema_version': 2, 'methodology_version': grades[0]['research']['methodology_version'] if grades else 'archive-recovery-v3', 'policy_hash': None, 'counts': counts, 'archive_counts': archive, 'applications': {},
                'macro_lower_bound': None, 'macro_upper_bound': None,
                'paired': {'pairs': [], 'excluded': [{'reason': 'multiple policies; inspect per-policy strata'}]},
                'policy_strata': {h: aggregate([g for g in grades if g['research']['policy_hash'] == h]) for h in sorted(hashes)}}
    applications = defaultdict(list)
    for g in grades:
        applications[g['research'].get('application', 'unknown')].append(g)
    by_app = {}
    for app, rows in sorted(applications.items()):
        scenarios = defaultdict(list)
        for g in rows:
            scenarios[g.get('scenario')].append(g['research'])
        scores = {str(s): bounds(v) for s, v in scenarios.items()}
        archive_scenarios = {str(s): archive_counts(v) for s, v in scenarios.items()}
        eligible = [v for v in scores.values() if v['eligible']]
        by_app[app] = {'scenarios': scores, 'archive_scenarios': archive_scenarios, 'archive_counts': archive_counts([g['research'] for g in rows]),
                       'lower_bound': mean(v['lower_bound'] for v in eligible) if eligible else None,
                       'upper_bound': mean(v['upper_bound'] for v in eligible) if eligible else None}
    eligible = [v for v in by_app.values() if v['lower_bound'] is not None]
    return {'schema_version': 2, 'methodology_version': grades[0]['research']['methodology_version'] if grades else 'archive-recovery-v3', 'policy_hash': next(iter(hashes), None), 'counts': bounds([g['research'] for g in grades]), 'applications': by_app, 'archive_counts': archive_counts([g['research'] for g in grades]),
            'macro_lower_bound': mean(v['lower_bound'] for v in eligible) if eligible else None,
            'macro_upper_bound': mean(v['upper_bound'] for v in eligible) if eligible else None,
            'paired': paired(grades)}


def run_section(r):
    op = r['operational']
    return '\n'.join(['## Incident outcomes', '',
        f"Methodology: `{r['methodology_version']}`; policy SHA-256: `{r['policy_hash']}`.", '',
        f"- Operational outcome: **{op['status']}** ({op.get('reason') or 'observed client outcomes'}).",
        f"- Safe recovery: `{r['safe_recovery']}`; safety: `{r['safety']['status']}`; execution: `{r['execution']['status']}`.",
        f"- Measurement basis: `{op.get('measurement_basis')}`.",
        f"- Archive proxy recovery time from schedule application: `{op.get('proxy_recovery_seconds')}` seconds; phase: `{op.get('recovery_schedule_phase')}`.",
        f"- Client failure ratio: `{(op.get('harm') or {}).get('failure_ratio')}`; successful requests/s: `{(op.get('harm') or {}).get('successful_rps')}`; measured failed requests: `{(op.get('harm') or {}).get('failed')}`.",
        f"- Time to recovery: `{op.get('recovery_seconds')}` seconds; censored: `{op.get('censored')}`.",
        f"- Recovery during active fault: `{op.get('active_fault_recovery')}`.",
        f"- Evidence assessment: `{r['evidence_quality']}`.",
        '', 'Null means unknown, not zero or failure. Operational outcomes are independent of semantic scores.', '',
        *['- ' + x for x in r['limitations']], ''])


def write_research_reports(output, grades):
    data = aggregate(grades)
    (output / 'incidents.json').write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    rows = []
    for g in grades:
        r = g['research']; op = r['operational']
        rows.append({'run': g['run'], 'scenario': g.get('scenario'), 'application': r.get('application'),
                     'methodology_version': r['methodology_version'], 'policy_hash': r['policy_hash'],
                     'operational_status': op['status'], 'measurement_basis': op.get('measurement_basis'),
                     'proxy_recovery_seconds': op.get('proxy_recovery_seconds'),
                     'recovery_schedule_phase': op.get('recovery_schedule_phase'),
                     'client_failure_ratio': (op.get('harm') or {}).get('failure_ratio'),
                     'successful_client_rps': (op.get('harm') or {}).get('successful_rps'), 'safe_recovery': r['safe_recovery'],
                     'safety': r['safety']['status'], 'execution': r['execution']['status'],
                     'recovery_seconds': op.get('recovery_seconds'), 'censored': op.get('censored'),
                     'active_fault_recovery': op.get('active_fault_recovery'),
                     'measured_failed_requests': (op.get('harm') or {}).get('failed'),
                     'measured_seconds': (op.get('harm') or {}).get('measured_seconds'),
                     'coverage': op.get('coverage'), 'experiment_type': r.get('experiment_type')})
        report = output / 'runs' / g['run'] / 'report.md'
        old = report.read_text()
        report.write_text(run_section(r) + '\n' + old)
    if rows:
        with (output / 'incidents.csv').open('w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    c = data['counts']
    a = data['archive_counts']
    text = '\n'.join(['# Research benchmark report', '',
        f"Methodology: `{data['methodology_version']}`; policy SHA-256: `{data['policy_hash'] or 'see per-policy strata'}`.", '',
        f"Archive recovery proxy: **{a['proxy_recovered']} recovered**, **{a['proxy_unresolved']} unresolved**, {a['no_observed_degradation']} without observed degradation, {a['insufficient_evidence']} insufficient evidence, {a['invalid']} invalid.", '',
        f"Assessable proxy recovery fraction: {a['evaluable_recovery_rate']}; conservative missing-outcome bounds: {a['lower_bound']} to {a['upper_bound']}. This is descriptive recovery, not verified safety or causal agent benefit.", '',
        f"Runs: {c['runs']}; non-incident controls: {c['non_incident_controls']}; invalid: {c['invalid']}; eligible: {c['eligible']}; confirmed safe recovery: {c['safe_recovered']}; unknown: {c['unknown']}.", '',
        f"Conservative safe recovery bounds: {c['lower_bound']} to {c['upper_bound']}.",
        f"Application/scenario macro bounds: {data['macro_lower_bound']} to {data['macro_upper_bound']}.", '',
        'See `incidents.csv` for one row per run and `incidents.json` for denominators. Paired effects are optional and unavailable without matched evidence; no additional runs are required.',
        'Job-level rubric means below describe evaluable outputs only; they are not incident success rates.', '',
        '## Semantic output diagnostics', ''])
    report = output / 'report.md'
    report.write_text(text + report.read_text())
