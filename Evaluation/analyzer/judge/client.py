import json
import re
from typing import Any, Protocol

from analyzer.log import progress

JSON_OBJECT_HINT = "Reply with a single JSON object that matches the required schema."
SCHEMA_ATTEMPTS = 3


class JudgeClient(Protocol):
    def complete(
        self, name: str, schema: dict[str, Any], messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        ...


class VLLMJudge:
    """OpenAI-compatible client aimed at a vLLM server."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: str = "EMPTY",
        timeout_seconds: float = 240,
    ):
        from openai import OpenAI

        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout_seconds,
            max_retries=0,
        )

    def complete(
        self, name: str, schema: dict[str, Any], messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        progress(f"vLLM request: {name}")
        last_error: Exception | None = None
        schema_format = {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        }
        for attempt in range(1, SCHEMA_ATTEMPTS + 1):
            try:
                response = self._create(messages, schema_format)
                return _response_payload(name, response)
            except Exception as exc:
                last_error = exc
                if not _is_timeout(exc) or attempt == SCHEMA_ATTEMPTS:
                    break
                progress(
                    f"vLLM json_schema timeout for {name} "
                    f"({attempt}/{SCHEMA_ATTEMPTS}); retrying"
                )
        progress(
            f"vLLM json_schema failed for {name} "
            f"({type(last_error).__name__}); retrying json_object"
        )
        try:
            response = self._create(
                with_json_object_hint(messages),
                {"type": "json_object"},
            )
            return _response_payload(name, response)
        except Exception:
            if last_error is not None:
                raise last_error
            raise

    def _create(self, messages: list[dict[str, str]], response_format: dict[str, Any]):
        return self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            messages=messages,
            response_format=response_format,
        )


def with_json_object_hint(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the system prompt first; vLLM rejects a later system message."""
    copied = [dict(item) for item in messages]
    if copied and copied[0].get("role") == "system":
        copied[0]["content"] = (
            str(copied[0].get("content") or "").rstrip() + "\n\n" + JSON_OBJECT_HINT
        )
        return copied
    return [{"role": "system", "content": JSON_OBJECT_HINT}, *copied]


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name


def _response_payload(name: str, response: Any) -> dict[str, Any]:
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise ValueError("empty judge response")
    progress(f"vLLM response: {name} ({len(content)} chars)")
    return _parse_json_object(content)


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise
        payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("judge response is not a JSON object")
    return payload


OpenAIJudge = VLLMJudge


class StaticJudge:
    def __init__(self, answers: list[dict[str, Any]] | None = None):
        self.answers = list(answers or [])

    def complete(
        self, name: str, schema: dict[str, Any], messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        if not self.answers:
            raise AssertionError(f"no canned judge answer for {name}")
        return self.answers.pop(0)
