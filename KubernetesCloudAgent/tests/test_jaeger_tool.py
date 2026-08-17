import sys
import types
from unittest import TestCase
from unittest.mock import patch

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from tools.jaeger import JaegerTool


class JaegerToolTest(TestCase):
    def test_lists_sorted_unique_services(self):
        tool = JaegerTool(base_url="http://jaeger/jaeger")

        with patch.object(
            tool,
            "_api_get",
            return_value={
                "ok": True,
                "data": {
                    "data": [
                        "frontend.online-boutique",
                        "cartservice.online-boutique",
                        "frontend.online-boutique",
                        "",
                        None,
                    ]
                },
            },
        ) as api_get:
            result = tool.list_services()

        api_get.assert_called_once_with("/jaeger/api/services", {})
        self.assertEqual(
            result,
            {
                "ok": True,
                "action": "list_services",
                "service_count": 2,
                "services": [
                    "cartservice.online-boutique",
                    "frontend.online-boutique",
                ],
            },
        )

    def test_returns_api_error(self):
        tool = JaegerTool(base_url="http://jaeger")
        error = {"ok": False, "error": "connection refused"}

        with patch.object(tool, "_api_get", return_value=error):
            result = tool.list_services()

        self.assertIs(result, error)

    def test_mounts_services_endpoint_for_root_base_url(self):
        tool = JaegerTool(base_url="http://jaeger")
        self.assertEqual(
            tool._mounted_path("/jaeger/api/services"),
            "/jaeger/api/services",
        )

    def test_avoids_duplicate_mount_for_mounted_base_url(self):
        tool = JaegerTool(base_url="http://jaeger/jaeger")
        self.assertEqual(
            tool._mounted_path("/jaeger/api/services"),
            "/api/services",
        )
