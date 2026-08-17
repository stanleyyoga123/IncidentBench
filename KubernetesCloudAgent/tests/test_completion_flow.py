from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import types
from unittest import TestCase
from unittest.mock import patch

if "langfuse" not in sys.modules:
    langfuse = types.ModuleType("langfuse")
    langfuse.get_client = lambda: None
    langfuse.propagate_attributes = lambda **_: None
    sys.modules["langfuse"] = langfuse
    langfuse_openai = types.ModuleType("langfuse.openai")
    langfuse_openai.OpenAI = object
    sys.modules["langfuse.openai"] = langfuse_openai

if "openai.types.chat" not in sys.modules:
    openai = types.ModuleType("openai")
    openai_types = types.ModuleType("openai.types")
    openai_types_chat = types.ModuleType("openai.types.chat")
    openai_types_chat.ChatCompletionMessage = object
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = openai_types
    sys.modules["openai.types.chat"] = openai_types_chat

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from main import PostgresAnomalyWorker
from manager.orchestrator import AgentManager, ManagerRunResult
from schema.anomaly import AnomalyBatch, AnomalyRow


def _row(row_id: int = 1) -> AnomalyRow:
    return AnomalyRow(
        id=row_id,
        timestamp=datetime(2026, 6, 26, 1, 2, 3, tzinfo=timezone.utc),
        resource="deployment",
        name="frontend",
        metrics="traffic_rps",
        method="ZScoreLogic",
        detail="severity = warning",
    )


class FakeManager:
    def __init__(self, result: ManagerRunResult):
        self.result = result

    def run_with_metadata(self, prompt: str) -> ManagerRunResult:
        self.prompt = prompt
        return self.result


class FakeStore:
    def record_remediation_session_and_complete(
        self,
        session_id: str,
        batch: AnomalyBatch,
        remediation_output: str,
        changes: dict,
    ) -> int:
        self.completed = {
            "session_id": session_id,
            "row_ids": batch.row_ids(),
            "remediation_output": remediation_output,
            "changes": changes,
        }
        return 99


class FakeAgent:
    outputs: list[str] = []
    constructions: list[dict] = []

    def __init__(self, **kwargs):
        self.name = kwargs["name"]
        self.system_prompt = kwargs["system_prompt"]
        self.__class__.constructions.append(kwargs)

    def run(self, prompt: str) -> str:
        return self.__class__.outputs.pop(0)


class CompletionFlowTest(TestCase):
    def setUp(self):
        FakeAgent.outputs = []
        FakeAgent.constructions = []

    def test_no_remediation_output_is_parsed_from_bullet_line(self):
        manager = AgentManager.__new__(AgentManager)

        self.assertFalse(
            manager._requires_remediation("- Remediation Required: no\nSummary: stable")
        )

    def test_markdown_formatted_remediation_values_are_parsed(self):
        manager = AgentManager.__new__(AgentManager)

        self.assertTrue(manager._requires_remediation("remediation required: **yes**"))
        self.assertTrue(manager._requires_remediation("remediation required: `yes`"))
        self.assertFalse(manager._requires_remediation("remediation required: **no**"))
        self.assertFalse(manager._requires_remediation("remediation required: `no`"))

    def test_no_remediation_batch_is_recorded_and_completed(self):
        result = ManagerRunResult(
            session_id="session-1",
            orchestration_output="Remediation Required: no",
            remediation_output="Remediation Required: no",
            remediation_required=False,
        )
        store = FakeStore()
        worker = PostgresAnomalyWorker(
            store=store,
            manager=FakeManager(result),
            poll_interval_seconds=1,
        )

        processed = worker._process_anomaly_batch(AnomalyBatch(anomalies=[_row(42)]))

        self.assertTrue(processed)
        self.assertEqual(store.completed["row_ids"], [42])
        self.assertFalse(store.completed["changes"]["remediation_required"])

    def test_manager_reloads_memory_for_orchestrator_only(self):
        with TemporaryDirectory() as directory:
            memory_path = Path(directory) / "MEMORY.md"
            FakeAgent.outputs = [
                "Remediation Required: no\nSummary: first historical RCA",
                "Remediation Required: yes\nSummary: current RCA",
                "Status\n- Automation: executed",
            ]
            manager = AgentManager(
                model="test-model",
                base_url="http://test.invalid/v1",
                memory_path=str(memory_path),
            )

            with (
                patch("manager.orchestrator.Agent", FakeAgent),
                patch(
                    "manager.orchestrator.propagate_attributes",
                    side_effect=lambda **_: nullcontext(),
                ),
            ):
                manager.run_with_metadata("first prompt")
                manager.run_with_metadata("second prompt")

            first_orchestrator = FakeAgent.constructions[0]
            second_orchestrator = FakeAgent.constructions[1]
            remediator = FakeAgent.constructions[2]
            self.assertNotIn(
                "# Historical Session Memory", first_orchestrator["system_prompt"]
            )
            self.assertIn(
                "# Historical Session Memory", second_orchestrator["system_prompt"]
            )
            self.assertIn("first historical RCA", second_orchestrator["system_prompt"])
            self.assertNotIn("# Historical Session Memory", remediator["system_prompt"])

    def test_memory_io_failure_does_not_change_successful_result(self):
        with TemporaryDirectory() as directory:
            FakeAgent.outputs = ["Remediation Required: no\nSummary: stable"]
            manager = AgentManager(
                model="test-model",
                base_url="http://test.invalid/v1",
                memory_path=directory,
            )

            with (
                patch("manager.orchestrator.Agent", FakeAgent),
                patch(
                    "manager.orchestrator.propagate_attributes",
                    side_effect=lambda **_: nullcontext(),
                ),
                self.assertLogs("AgentManager", level="ERROR") as memory_logs,
            ):
                result = manager.run_with_metadata("prompt")

            self.assertFalse(result.remediation_required)
            self.assertEqual(result.remediation_output, result.orchestration_output)
            self.assertTrue(
                any(
                    "Failed to append completed session" in log
                    for log in memory_logs.output
                )
            )
