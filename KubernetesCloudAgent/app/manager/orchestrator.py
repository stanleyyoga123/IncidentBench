import re
import uuid
from dataclasses import dataclass

from langfuse import propagate_attributes
from agent import Agent
from common.logger.console import get_logger
from common.memory import SessionMemoryEntry, SessionMemoryStore
from common.session import session
from prompt import get_role_prompt
from prompt.agent import REMEDIATOR_EXECUTION_PROMPT
from prompt.knowledge import CLUSTER_KNOWLEDGE
from registry.tool import TOOL_REGISTRY


LOGGER = get_logger("AgentManager")


ORCHESTRATOR_TOOL_NAMES = [
    "cluster.profile_baseline",
    "agent_spawner",
]

REMEDIATOR_TOOL_NAMES = [
    "remediator.write_file",
    "remediator.run_ansible",
    "kubectl",
    "prometheus",
    "loki",
    "jaeger.list_services",
    "jaeger.retrieve_slow_traces",
    "jaeger.investigate_trace",
    "jaeger.retrieve_bottleneck",
    "network.topology",
    "network.latency_matrix",
    "network.dns",
    "network.tcp_connect",
]


@dataclass(frozen=True)
class ManagerRunResult:
    session_id: str
    orchestration_output: str
    remediation_output: str
    remediation_required: bool


class AgentManager:
    def __init__(
        self,
        model: str,
        base_url: str,
        max_orchestration_rounds: int = 10,
        memory_path: str = "/app/MEMORY.md",
        memory_max_prompt_chars: int = 32_000,
    ):
        self._model = model
        self._base_url = base_url
        self._max_orchestration_rounds = max_orchestration_rounds
        self._orchestrator_system_prompt = "\n\n".join(
            [get_role_prompt("agent_orchestrator"), CLUSTER_KNOWLEDGE]
        )
        self._remediator_system_prompt = get_role_prompt("remediator")
        self._memory = SessionMemoryStore(
            path=memory_path,
            max_prompt_chars=memory_max_prompt_chars,
        )

    def run(self, prompt: str) -> str:
        return self.run_with_metadata(prompt).remediation_output

    def run_with_metadata(self, prompt: str) -> ManagerRunResult:
        session_id = str(uuid.uuid4())
        orchestrator_system_prompt = self._orchestrator_system_prompt
        try:
            memory_context = self._memory.load_prompt_context()
        except Exception:
            LOGGER.exception("Failed to load session memory from %s", self._memory.path)
            memory_context = ""
        if memory_context:
            orchestrator_system_prompt = "\n\n".join(
                [orchestrator_system_prompt, memory_context]
            )

        orchestrator = Agent(
            name="agent-orchestrator",
            model=self._model,
            base_url=self._base_url,
            system_prompt=orchestrator_system_prompt,
            tools=TOOL_REGISTRY.describe_openai_format(ORCHESTRATOR_TOOL_NAMES),
            max_rounds=self._max_orchestration_rounds,
            timeout_seconds=120,
            # Precise parameter
            temperature=0.6,
            top_p=0.95,
            top_k=20,
            min_p=0.0,
            presence_penalty=0.0,
            repetition_penalty=1.0,
        )
        with propagate_attributes(session_id=session_id):
            orchestration_output = orchestrator.run(prompt)

        remediation_required = self._requires_remediation(orchestration_output)
        if not remediation_required:
            result = ManagerRunResult(
                session_id=session_id,
                orchestration_output=orchestration_output,
                remediation_output=orchestration_output,
                remediation_required=False,
            )
            self._record_memory(prompt, result)
            return result

        remediator = Agent(
            name="remediator",
            model=self._model,
            base_url=self._base_url,
            system_prompt=self._remediator_system_prompt,
            tools=TOOL_REGISTRY.describe_openai_format(REMEDIATOR_TOOL_NAMES),
            timeout_seconds=300,
            max_rounds=50,
            # Precise parameter
            temperature=0.6,
            top_p=0.95,
            top_k=20,
            min_p=0.0,
            presence_penalty=0.0,
            repetition_penalty=1.0,
        )
        remediator_prompt = REMEDIATOR_EXECUTION_PROMPT.format(
            session_id=session_id,
            prompt=prompt,
            orchestration_output=orchestration_output,
        )
        with session(session_id):
            with propagate_attributes(session_id=session_id, trace_name="remediator"):
                remediation_output = remediator.run(remediator_prompt)

        result = ManagerRunResult(
            session_id=session_id,
            orchestration_output=orchestration_output,
            remediation_output=remediation_output,
            remediation_required=True,
        )
        self._record_memory(prompt, result)
        return result

    def _record_memory(self, prompt: str, result: ManagerRunResult) -> None:
        try:
            self._memory.append(
                SessionMemoryEntry(
                    session_id=result.session_id,
                    prompt=prompt,
                    orchestration_output=result.orchestration_output,
                    remediation_required=result.remediation_required,
                    remediation_output=result.remediation_output,
                )
            )
        except Exception:
            LOGGER.exception(
                "Failed to append completed session %s to memory at %s",
                result.session_id,
                self._memory.path,
            )

    def _requires_remediation(self, orchestration_output: str) -> bool:
        lines = orchestration_output.splitlines()
        for index, line in enumerate(lines):
            key, separator, value = line.partition(":")
            normalized_key = key.strip().lstrip("-*").strip().lower()
            if separator and "remediation required" in normalized_key:
                if not value.strip():
                    for next_line in lines[index + 1 :]:
                        if next_line.strip():
                            value = next_line
                            break
                tokens = re.sub(r"[^a-z0-9]+", " ", value.lower()).split()
                if any(keyword in tokens for keyword in ["yes", "true", "1"]):
                    return True
                if any(keyword in tokens for keyword in ["no", "false", "none", "0"]):
                    return False
        return True


if __name__ == "__main__":
    manager = AgentManager(
        model="Qwen/Qwen3.6-35B-A3B", base_url="http://localhost:8000/v1"
    )
    prompt = "I've seen several times that the rps of several deployments (like frontend) takes ~1 second to finish, can you investigate what's the main cause of that event?"
    # prompt = "The balance in nodes is not looking good right now (especially the tools-node), can you help to rebalance the nodes"
    print(manager.run(prompt))
