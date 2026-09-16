import json
import re

from langfuse import propagate_attributes

from agent import Agent
from prompt import get_role_prompt
from prompt.agent import REMEDIATOR_EXECUTION_PROMPT
from registry.tool import TOOL_REGISTRY, audit_tool_calls
from schema import RemediationJobRequest, RemediationResult


TOOLS = [
    "remediator.write_file", "remediator.run_ansible", "kubectl", "prometheus",
    "loki", "jaeger.list_services", "jaeger.retrieve_slow_traces",
    "jaeger.investigate_trace", "jaeger.retrieve_bottleneck",
    "network.topology", "network.latency_matrix", "network.dns",
    "network.tcp_connect",
]


class RemediationEngine:
    def __init__(self, settings, audit_callback=None):
        self.output_callback = None
        self.settings = settings
        self.audit_callback = audit_callback

    def run(self, job_id, request: RemediationJobRequest):
        agent = Agent(
            name="remediator-agent",
            model=self.settings.client.model,
            base_url=self.settings.client.url,
            api_key=self.settings.client.token,
            system_prompt=get_role_prompt("remediator"),
            tools=TOOL_REGISTRY.describe_openai_format(TOOLS),
            timeout_seconds=self.settings.client.timeout_seconds,
            max_rounds=self.settings.manager.max_rounds,
            temperature=0.6,
            top_p=0.95,
        )
        prompt = self._prompt(job_id, request)
        def callback(name, args, result):
            if self.audit_callback:
                self.audit_callback(job_id, name, args, result)
        with audit_tool_calls(callback):
            with propagate_attributes(session_id=str(job_id), trace_name="remediator"):
                raw = agent.run(prompt)
        if not isinstance(raw, str) or not raw.strip():
            raise RuntimeError("remediation agent returned no final output")
        self.last_raw_output = raw
        if self.output_callback:
            self.output_callback(job_id, raw)
        result = self._parse(raw)
        self.last_result = result.model_dump(mode="json")
        if self.output_callback:
            self.output_callback(job_id, raw, result.model_dump(mode="json"))
        return result, raw

    @staticmethod
    def _prompt(job_id, request: RemediationJobRequest) -> str:
        workflow_context = {
            "workflow_id": str(request.workflow_id) if request.workflow_id else None,
            "rca_job_id": str(request.rca_job_id),
            "approval": request.approval.model_dump(mode="json"),
        }
        return REMEDIATOR_EXECUTION_PROMPT.format(
            session_id=job_id,
            prompt=json.dumps(workflow_context, sort_keys=True, indent=2),
            orchestration_output=json.dumps(
                request.rca_result,
                sort_keys=True,
                indent=2,
            ),
        )

    @classmethod
    def _parse(cls, raw: str) -> RemediationResult:
        return RemediationResult(
            summary=cls._section(raw, "Status") or raw[:4000],
            changes=cls._lines(cls._section(raw, "Changes")),
            verification=cls._lines(cls._section(raw, "Verification")),
        )

    @staticmethod
    def _section(raw: str, name: str) -> str:
        match = re.search(
            rf"(?ims)^\s*(?:#+\s*)?{re.escape(name)}\s*:?\s*(.*?)"
            rf"(?=^\s*(?:#+\s*)?(?:Status|Changes|Verification|"
            rf"Blocked Or Skipped|Next Steps)\s*:?\s*$|\Z)",
            raw,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _lines(value: str) -> list[str]:
        return [line.strip().lstrip("-* ") for line in value.splitlines() if line.strip()]
