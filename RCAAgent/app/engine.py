import re

from langfuse import propagate_attributes

from agent import Agent
from common.memory import SessionMemoryEntry, SessionMemoryStore
from prompt import get_role_prompt
from prompt.knowledge import CLUSTER_KNOWLEDGE
from registry.tool import TOOL_REGISTRY, audit_tool_calls
from schema import RCAJobRequest, RCAResult, RemediationPlan


RCA_TOOL_NAMES = ["cluster.profile_baseline", "agent_spawner"]


class RCAEngine:
    def __init__(self, settings, audit_callback=None):
        self.settings = settings
        self.audit_callback = audit_callback
        self.memory = SessionMemoryStore(
            settings.manager.memory_path,
            settings.manager.memory_max_prompt_chars,
        )

    def run(self, job_id, request: RCAJobRequest) -> tuple[RCAResult, str]:
        system = "\n\n".join(
            [get_role_prompt("agent_orchestrator"), CLUSTER_KNOWLEDGE]
        )
        try:
            memory = self.memory.load_prompt_context()
            if memory:
                system = f"{system}\n\n{memory}"
        except Exception:
            pass
        agent = Agent(
            name="rca-agent",
            model=self.settings.client.model,
            base_url=self.settings.client.url,
            api_key=self.settings.client.token,
            system_prompt=system,
            tools=TOOL_REGISTRY.describe_openai_format(RCA_TOOL_NAMES),
            max_rounds=self.settings.manager.max_rounds,
            timeout_seconds=self.settings.client.timeout_seconds,
            temperature=0.6,
            top_p=0.95,
        )
        prompt = self._prompt(request)
        callback = (
            lambda name, args, result: self.audit_callback(job_id, name, args, result)
            if self.audit_callback
            else None
        )
        with audit_tool_calls(callback):
            with propagate_attributes(session_id=str(job_id), trace_name="rca"):
                raw = agent.run(prompt)
        result = self._parse(raw)
        try:
            self.memory.append(
                SessionMemoryEntry(
                    session_id=str(job_id),
                    prompt=prompt,
                    orchestration_output=raw,
                    remediation_required=result.remediation_required,
                )
            )
        except Exception:
            pass
        return result, raw

    @staticmethod
    def _prompt(request: RCAJobRequest) -> str:
        sections = []
        for item in request.anomalies:
            sections.append(
                "\n".join(
                    [
                        f"Event ID: {item.get('event_id', 'unknown')}",
                        f"Detected at: {item.get('detected_at', 'unknown')}",
                        f"Resource: {item.get('resource', 'unknown')}",
                        f"Name: {item.get('name', 'unknown')}",
                        f"Metric: {item.get('metric', 'unknown')}",
                        f"Method: {item.get('method', 'unknown')}",
                        "Detail:",
                        str(item.get("detail", "")),
                    ]
                )
            )
        context = f"\n\nCaller context:\n{request.caller_context}" if request.caller_context else ""
        return (
            "# Detector Anomaly Investigation\n\n"
            "Treat these events as leads, not proof. Preserve event IDs.\n\n"
            + "\n\n---\n\n".join(sections)
            + context
        )

    @classmethod
    def _parse(cls, raw: str) -> RCAResult:
        remediation = cls._bool_field(raw, "Remediation Required", default=False)
        incident = cls._field(raw, "Incident State").lower()
        allowed = {"active", "recovered", "intermittent", "preventive risk", "unconfirmed"}
        if incident not in allowed:
            incident = "unconfirmed"
        return RCAResult(
            remediation_required=remediation,
            incident_state=incident,
            summary=cls._section(raw, "Summary") or raw[:4000],
            failed_investigations=cls._lines(cls._section(raw, "Failed Investigation")),
            evidence=cls._lines(cls._section(raw, "Evidence")),
            impact_scope=cls._lines(cls._section(raw, "Impact Scope")),
            uncertainty=cls._lines(cls._section(raw, "Missing Or Uncertain")),
            remediation_plan=RemediationPlan(
                action=cls._section(raw, "Remediation Plan"),
                targets=cls._lines(cls._section(raw, "Remediation Targets")),
                expected_benefit=cls._section(raw, "Expected Benefit"),
                verification=cls._lines(cls._section(raw, "Verification")),
                rollback=cls._lines(cls._section(raw, "Rollback")),
                guardrails=cls._lines(cls._section(raw, "Guardrails")),
            ),
        )

    @staticmethod
    def _field(raw: str, name: str) -> str:
        match = re.search(rf"(?im)^\s*(?:[-*]\s*)?{re.escape(name)}\s*:\s*(.+)$", raw)
        return match.group(1).strip(" *`") if match else ""

    @classmethod
    def _bool_field(cls, raw: str, name: str, default: bool) -> bool:
        value = re.sub(r"[^a-z0-9]+", " ", cls._field(raw, name).lower()).split()
        if any(item in value for item in ("yes", "true", "1")):
            return True
        if any(item in value for item in ("no", "false", "0", "none")):
            return False
        return default

    @staticmethod
    def _section(raw: str, name: str) -> str:
        match = re.search(
            rf"(?ims)^\s*(?:#+\s*|[-*]\s*)?{re.escape(name)}\s*:\s*(.*?)(?=^\s*(?:#+\s*|[-*]\s*)?[A-Z][A-Za-z ]+\s*:|\Z)",
            raw,
        )
        return match.group(1).strip() if match else ""

    @staticmethod
    def _lines(value: str) -> list[str]:
        return [line.strip().lstrip("-* ") for line in value.splitlines() if line.strip()]
