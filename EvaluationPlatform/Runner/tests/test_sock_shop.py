import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def behavior():
    class RescheduleTask(Exception):
        pass

    stubs = {
        "locust": SimpleNamespace(
            FastHttpUser=object,
            TaskSet=object,
            between=lambda *_: None,
            task=lambda function: function,
        ),
        "locust.exception": SimpleNamespace(RescheduleTask=RescheduleTask),
        "testbed.loadgenerator.common": SimpleNamespace(request=None),
    }
    path = Path(__file__).parents[1] / "resources/applications" / "sock_shop.py"
    spec = importlib.util.spec_from_file_location("sock_shop_test_workload", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    instance = module.SockShopBehavior()
    instance.on_start()
    return module, instance


def test_journey_covers_catalogue_product_and_isolated_cart(behavior):
    module, instance = behavior
    calls = []

    class Response:
        status_code = 200

        def __init__(self, path):
            self.path = path

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def failure(self, message):
            raise AssertionError(message)

        def json(self):
            return [{"id": "sock-1"}] if self.path == "/catalogue" else {"id": "result-1"}

    def fake_request(_instance, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return Response(path)

    module.request = fake_request
    instance.shopping_session()
    assert [(method, path) for method, path, _ in calls] == [
        ("get", "/"),
        ("get", "/catalogue"),
        ("post", "/register"),
        ("get", "/login"),
        ("post", "/addresses"),
        ("post", "/cards"),
        ("get", "/category.html"),
        ("get", "/detail.html"),
        ("delete", "/cart"),
        ("post", "/cart"),
        ("get", "/basket.html"),
        ("post", "/orders"),
        ("delete", "/cart"),
    ]
    cart = next(kwargs for method, path, kwargs in calls if (method, path) == ("post", "/cart"))
    assert cart["json"] == {"id": "sock-1", "quantity": 1}
    calls.clear()
    instance.shopping_session()
    assert not any(path in {"/register", "/addresses", "/cards"} for _, path, _ in calls)
    assert any(path == "/orders" for _, path, _ in calls)


def test_unusable_catalogue_is_a_recorded_failure(behavior):
    module, instance = behavior
    failures = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def failure(self, message):
            failures.append(message)

        def json(self):
            return []

    module.request = lambda *_args, **_kwargs: Response()
    with pytest.raises(module.RescheduleTask):
        instance.shopping_session()
    assert failures == ["Sock Shop catalogue returned no usable products"]


def test_customer_setup_recovers_without_duplicate_registration(behavior):
    module, instance = behavior
    calls = []
    def checked(method, path, **kwargs):
        calls.append(path)
        if path == '/addresses' and calls.count(path) == 1:
            raise module.RescheduleTask()
    instance.checked_request = checked
    with pytest.raises(module.RescheduleTask):
        instance.prepare_customer()
    instance.prepare_customer()
    assert calls.count('/register') == 1
    assert calls.count('/addresses') == 2
    assert calls.count('/cards') == 1


def test_invalid_order_response_is_recorded_as_failure(behavior):
    module, instance = behavior
    failures = []
    class Response:
        status_code = 201
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def json(self): return {'error': 'payment failed'}
        def failure(self, message): failures.append(message)
    module.request = lambda *_args, **_kwargs: Response()
    with pytest.raises(module.RescheduleTask):
        instance.checked_request('post', '/orders', statuses=(201,), require_id=True)
    assert failures == ['Sock Shop invalid response: /orders (missing id)']


def test_sock_shop_full_suite_matches_boutique_fault_families_and_valid_targets():
    import json
    import yaml
    from testbed.applications import ApplicationCatalog
    from testbed.chaos.catalog import ChaosCatalog
    from testbed.command import CommandRunner
    from testbed.configuration import ROOT, resolve_scenario
    from testbed.placement import PlacementRenderer, validate_pod_chaos_selectors
    root = ROOT
    suite = json.loads((root / 'resources/suites/sock-shop.json').read_text())
    assert len(suite['runs']) == 23
    profile = ApplicationCatalog(root / 'resources/applications', root.parents[1]).resolve('sock-shop')
    renderer = PlacementRenderer(CommandRunner(), root, application_profile=profile)
    rendered = {name: renderer.render(name, root / 'resources/applications/sock-shop/kustomize/overlays' / name)
                for name in ('canonical-six-node', 'cpu-constrained-six-node')}
    catalogue = ChaosCatalog(root / 'resources/chaos')
    names = set()
    for index, entry in enumerate(suite['runs'], 1):
        scenario = resolve_scenario(root / 'resources/suites' / entry['scenario'])
        names.add(scenario['name'])
        assert scenario['application'] == 'sock-shop'
        assert scenario['timing']['baseline_seconds'] == 3600
        assert [step['duration'] for step in scenario['steps']] == [3600, 600]
        schedules = catalogue.resolve_many(scenario['steps'][0]['chaos'])
        validate_pod_chaos_selectors(rendered[scenario['placement']], schedules, 'app')
        assert scenario['placement'] == ('cpu-constrained-six-node' if index >= 21 else 'canonical-six-node')
    assert len(names) == 23
    docs = list(yaml.safe_load_all(rendered['cpu-constrained-six-node'].rendered_manifest))
    deployments = {doc['metadata']['name']: doc for doc in docs if doc['kind'] == 'Deployment'}
    for name in ('front-end', 'orders', 'catalogue'):
        resources = deployments[name]['spec']['template']['spec']['containers'][0]['resources']
        assert resources['requests']['cpu'] == resources['limits']['cpu'] == '100m'
    for name in ('carts-db', 'orders-db', 'user-db', 'catalogue-db', 'session-db', 'rabbitmq'):
        assert deployments[name]['spec']['replicas'] == 1
