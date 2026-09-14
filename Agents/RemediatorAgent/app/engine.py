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
        self.settings = settings
        self.audit_callback = audit_callback
        self._live_ansible_succeeded = False
        self._live_ansible_failed = False
        self._post_action_checks = set()

    def run(self, job_id, request: RemediationJobRequest):
        self._live_ansible_succeeded = False
        self._live_ansible_failed = False
        self._post_action_checks = set()
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
            self.note_tool_result(name, result)
            if self.audit_callback:
                self.audit_callback(job_id, name, args, result)
        with audit_tool_calls(callback):
            with propagate_attributes(session_id=str(job_id), trace_name="remediator"):
                raw = agent.run(prompt)
        self.require_verified_recovery(raw)
        return self._parse(raw), raw

    def note_tool_result(self, name: str, result) -> None:
        if name == "remediator.run_ansible":
            # Invalidate earlier observations on every subsequent execution attempt,
            # including ambiguous responses. A later success cannot erase failure.
            self._post_action_checks.clear()
            if not isinstance(result, dict):
                self._live_ansible_failed = True
            elif result.get("check") is not True and result.get("ok") is not True:
                self._live_ansible_failed = True
        if (
            name == "remediator.run_ansible"
            and isinstance(result, dict)
            and result.get("ok") is True
            and result.get("check") is False
        ):
            self._live_ansible_succeeded = True
        if name in {"kubectl", "prometheus"}:
            self._post_action_checks.discard(name)
        if not self._live_ansible_succeeded or not isinstance(result, dict):
            return
        if name == "kubectl" and result.get("ok") is True and result.get("stdout"):
            self._post_action_checks.add("kubectl")
        if name == "prometheus" and result.get("ok") is True:
            payload = result.get("data")
            if isinstance(payload, dict) and payload.get("status") == "success":
                data = payload.get("data")
                if isinstance(data, dict) and data.get("result"):
                    self._post_action_checks.add("prometheus")

    def require_verified_recovery(self, raw: str) -> None:
        self.require_live_ansible()
        if self._live_ansible_failed:
            raise RuntimeError("live remediation failure requires review")
        status = self._lines(self._section(raw, "Status"))
        if (
            status.count("Automation: executed") != 1
            or status.count("Recovery: verified") != 1
            or sum(line.startswith("Automation:") for line in status) != 1
            or sum(line.startswith("Recovery:") for line in status) != 1
            or not self._lines(self._section(raw, "Verification"))
        ):
            raise RuntimeError("remediation recovery is not explicitly verified")
        if not {"kubectl", "prometheus"}.issubset(self._post_action_checks):
            raise RuntimeError(
                "recovery requires post-action Kubernetes and non-empty Prometheus evidence"
            )

    def require_live_ansible(self) -> None:
        if not self._live_ansible_succeeded:
            raise RuntimeError(
                "remediation did not complete a successful live Ansible run"
            )

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
