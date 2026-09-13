from pathlib import Path
from testbed.configuration import read_json, resolve_scenario, validate

ROOT = Path(__file__).resolve().parents[1]


def test_all_suite_preserves_constant_and_daily_choices():
    path = ROOT/'resources/suites/all.json'
    suite = read_json(path); validate(suite,'suite')
    specs=[resolve_scenario(path.parent / item['scenario']) for item in suite['runs']]
    assert specs[-1]['load']['type']=='daily'
    assert all(spec['load']['type']=='constant' for spec in specs[:-1])


def test_paired_suite_differs_only_in_agent_mode():
    path = ROOT/'resources/suites/paired.json'
    suite = read_json(path); validate(suite,'suite')
    for enabled, disabled in zip(suite['runs'][::2],suite['runs'][1::2]):
        assert enabled['scenario']==disabled['scenario']
        assert enabled['overrides']=={'agents_enabled':True}
        assert disabled['overrides']=={'agents_enabled':False}
