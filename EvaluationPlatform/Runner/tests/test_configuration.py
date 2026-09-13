from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from testbed.configuration import ROOT, merge, resolve_scenario, validate
from testbed.platform import run
from testbed.cli import parse_args

SOURCE = ROOT/'resources/scenarios/online-boutique-scenario/01-node-delay-worker-3.json'


def test_recursive_merge_replaces_lists_without_changing_inputs():
    original={'timing':{'baseline_seconds':60,'grace_seconds':10},'prerun':['a','b']}
    assert merge(original,{'timing':{'baseline_seconds':120},'prerun':['c']}) == {'timing':{'baseline_seconds':120,'grace_seconds':10},'prerun':['c']}
    assert original['prerun'] == ['a','b']


def test_shape_defaults_are_explicit_in_resolved_archive():
    spec = resolve_scenario(SOURCE)
    assert spec['load']['parameters']['users'] == 50
    assert 'global_config' not in spec
    burst = resolve_scenario(SOURCE, {'schema_version':1,'load':{'type':'burst','parameters':{'peak_users':900}}})
    assert burst['load']['parameters']['baseline_users'] == 300
    assert burst['load']['parameters']['peak_users'] == 900


@pytest.mark.parametrize('override', [
    {'load':{'type':'unknown'}}, {'timing':{'baseline_seconds':0}},
    {'load':{'type':'burst','parameters':{'peak_users':1}}},
    {'load':{'type':'daily','parameters':{'stages':[{'duration':10,'spawn_rate':1,'percentage_users':100},{'duration':5,'spawn_rate':1,'percentage_users':100}]}}},
    {'deployments':[{'name':'agent-orchestrator','namespace':'agents','replicas':1}]},
    {'prerun':['../escape']}, {'prerun':['missing-hook']}, {'typo':True},
])
def test_invalid_config_fails_before_execution(override):
    with pytest.raises(ValueError):
        resolve_scenario(SOURCE, {'schema_version':1, **override})


def test_suite_validation_never_executes_run_or_cluster_commands(tmp_path):
    args = parse_args(['--suite',str(ROOT/'resources/suites/paired.json'),'--environment',str(ROOT/'config/environment.example.json'),'--validate-only'])
    with patch('testbed.platform.preflight') as preflight, patch('testbed.platform.run_one') as run_one:
        assert run(args, lambda _:None) == 0
    assert preflight.call_count > 1
    run_one.assert_not_called()


def test_all_committed_scenarios_resolve():
    paths = list((ROOT/'resources/scenarios').rglob('*.json'))
    assert len(paths) == 72
    for path in paths:
        resolve_scenario(path)


def test_partial_load_parameters_override_the_global_shape():
    spec=resolve_scenario(SOURCE,{'schema_version':1,'load':{'parameters':{'users':77}}})
    assert spec['load']['type']=='constant'
    assert spec['load']['parameters']['users']==77


def test_node_targets_are_resolved_only_for_selected_schedules(tmp_path):
    from testbed.chaos.catalog.chaos_catalog import ChaosCatalog
    from testbed.chaos.catalog.schedule_loader import ScheduleLoader
    catalog=ChaosCatalog(ROOT/'resources/chaos',ScheduleLoader(node_ips={'worker-node-3':'192.0.2.3'}))
    item=catalog.resolve('node-delay-peers-to-worker-3')
    assert item.manifest['spec']['physicalmachineChaos']['network-delay']['ip-address']=='192.0.2.3'
    with pytest.raises(ValueError,match='worker-node-4'):
        catalog.resolve('node-delay-peers-to-worker-4')
