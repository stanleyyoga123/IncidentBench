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
    path = Path(__file__).parents[1] / "applications" / "sock_shop.py"
    spec = importlib.util.spec_from_file_location("sock_shop_test_workload", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, stubs):
        spec.loader.exec_module(module)
    return module, module.SockShopBehavior()


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
            return [{"id": "sock-1"}]

    def fake_request(_instance, method, path, **kwargs):
        calls.append((method, path, kwargs))
        return Response(path)

    module.request = fake_request
    instance.shopping_session()
    assert [(method, path) for method, path, _ in calls] == [
        ("get", "/"),
        ("get", "/catalogue"),
        ("get", "/category.html"),
        ("get", "/detail.html"),
        ("post", "/cart"),
        ("get", "/basket.html"),
        ("delete", "/cart"),
    ]
    cart = calls[4][2]
    assert cart["json"] == {"id": "sock-1", "quantity": 1}


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
