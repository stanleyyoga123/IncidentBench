import re
import shlex
from typing import Any

from tools.utility import apply_grep, run_command


class KubectlTool:
    _CHAOS_MESH_PATTERN = re.compile(
        r"chaos[-\s]?mesh|chaos-mesh\.org|(?:pod|network|stress|io|time|dns|http|kernel|jvm)chaos",
        re.IGNORECASE,
    )
    _BLOCKED_TOKENS = {"|", "&&", "||", ";", ">", ">>", "<"}
    _BLOCKED_DELETE_KINDS = {
        "namespace",
        "namespaces",
        "node",
        "nodes",
        "pv",
        "persistentvolume",
        "persistentvolumes",
        "pvc",
        "persistentvolumeclaim",
        "persistentvolumeclaims",
        "crd",
        "customresourcedefinition",
        "customresourcedefinitions",
        "clusterrole",
        "clusterroles",
        "clusterrolebinding",
        "clusterrolebindings",
    }

    def __init__(self, path: str = "kubectl", timeout_seconds: int = 30) -> None:
        self.path = path
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        args: str | list[str],
        grep: str | None = None,
        timeout_seconds: int | None = None,
    ) -> dict[str, Any]:
        parsed = self._parse_args(args)
        blocked = self._blocked_reason(parsed)
        if blocked:
            return {"ok": False, "error": blocked, "args": parsed}

        result = run_command(
            [self.path, *parsed],
            timeout_seconds or self.timeout_seconds,
        )
        redacted_stdout = self._redact_chaos_mesh_lines(result.get("stdout", ""))
        return {
            **result,
            **apply_grep(redacted_stdout, grep),
        }

    def _parse_args(self, args: str | list[str]) -> list[str]:
        if isinstance(args, str):
            args = args.removeprefix("kubectl").strip()
            return shlex.split(args)
        if args and args[0] == "kubectl":
            return args[1:]
        return [str(arg) for arg in args]

    def _blocked_reason(self, args: list[str]) -> str | None:
        if any(token in self._BLOCKED_TOKENS for token in args):
            return "shell operators are blocked; use the grep parameter for filtering"
        if (
            len(args) >= 2
            and args[0] == "delete"
            and args[1].lower() in self._BLOCKED_DELETE_KINDS
        ):
            return f"deleting {args[1]} is blocked by local guardrails"
        if args and args[0] == "scale":
            if any(item == "--replicas=0" for item in args):
                return "scaling workloads to zero is blocked by local guardrails"
            for index, item in enumerate(args[:-1]):
                if item == "--replicas" and args[index + 1] == "0":
                    return "scaling workloads to zero is blocked by local guardrails"
        return None

    def _redact_chaos_mesh_lines(self, stdout: str) -> str:
        lines = stdout.splitlines()
        filtered = [
            line for line in lines if not self._CHAOS_MESH_PATTERN.search(line)
        ]
        return "\n".join(filtered).strip()
