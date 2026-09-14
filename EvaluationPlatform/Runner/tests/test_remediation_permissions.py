import json
from types import SimpleNamespace

import pytest

from hooks.runtime import verify_remediation_permissions


def test_permission_reviews_use_service_account_and_application_namespace():
    reviews = []

    def run(command, **kwargs):
        assert command == ['kubectl', 'create', '-f', '-', '-o', 'json']
        reviews.append(json.loads(kwargs['input']))
        return SimpleNamespace(stdout='{"status":{"allowed":true}}')

    verify_remediation_permissions('sock-shop', run=run)
    assert len(reviews) == 2
    for review, (group, resource) in zip(reviews, [('apps', 'deployments'), ('autoscaling', 'horizontalpodautoscalers')]):
        assert review['spec']['user'] == 'system:serviceaccount:agents:mcp-tools-remediation'
        assert review['spec']['resourceAttributes'] == {
            'namespace': 'sock-shop', 'verb': 'patch', 'group': group, 'resource': resource,
        }


@pytest.mark.parametrize('status', [{'allowed': False}, {}, {'allowed': 'true'}])
def test_permission_review_fails_closed(status):
    def run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps({'status': status}))

    with pytest.raises(RuntimeError, match='cannot patch deployments.apps in sock-shop'):
        verify_remediation_permissions('sock-shop', run=run)
