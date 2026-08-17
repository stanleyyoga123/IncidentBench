from unittest import TestCase
from unittest.mock import patch

from tools.kubectl import KubectlTool


class KubectlToolTest(TestCase):
    def test_redacts_chaos_mesh_lines_before_returning_stdout(self):
        stdout = "\n".join(
            [
                "LAST SEEN   TYPE      REASON      OBJECT          MESSAGE",
                "1m          Normal    Pulled      pod/frontend   Container image pulled",
                "30s         Warning   ChaosMesh   pod/frontend   chaos-mesh injected delay",
                "20s         Normal    Scheduled   pod/cart       Successfully assigned",
                "10s         Warning   PodChaos    pod/cart       podchaos applied",
            ]
        )

        with patch(
            "tools.kubectl.run_command",
            return_value={
                "ok": True,
                "command": "kubectl get events",
                "returncode": 0,
                "stdout": stdout,
                "stderr": "",
            },
        ):
            result = KubectlTool().run("get events -n online-boutique")

        self.assertTrue(result["ok"])
        self.assertIn("Container image pulled", result["stdout"])
        self.assertIn("Successfully assigned", result["stdout"])
        self.assertNotIn("ChaosMesh", result["stdout"])
        self.assertNotIn("chaos-mesh", result["stdout"])
        self.assertNotIn("PodChaos", result["stdout"])
        self.assertNotIn("redacted_line_count", result)
        self.assertNotIn("unredacted_line_count", result)

    def test_applies_grep_after_chaos_mesh_redaction(self):
        stdout = "\n".join(
            [
                "normal frontend healthy",
                "chaos-mesh frontend experiment started",
                "normal cart healthy",
            ]
        )

        with patch(
            "tools.kubectl.run_command",
            return_value={
                "ok": True,
                "command": "kubectl get events",
                "returncode": 0,
                "stdout": stdout,
                "stderr": "",
            },
        ):
            result = KubectlTool().run("get events", grep="frontend")

        self.assertEqual(result["stdout"], "normal frontend healthy")
        self.assertEqual(result["line_count"], 1)
        self.assertEqual(result["unfiltered_line_count"], 2)
        self.assertNotIn("redacted_line_count", result)
