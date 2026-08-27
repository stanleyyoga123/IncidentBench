import json
import re
from typing import Any, Protocol

from analyzer.log import progress

JSON_OBJECT_HINT = "Reply with a single JSON object that matches this JSON schema:"
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_TOKENS = 8192


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
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        from openai import OpenAI

        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
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
        schema_format = {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": True,
                "schema": schema,
            },
        }
        object_error: Exception | None = None
        try:
            response = self._create(
                with_json_object_hint(messages, schema),
                {"type": "json_object"},
            )
            return _response_payload(name, response, schema)
        except Exception as exc:
            object_error = exc
            if _is_timeout(exc):
                raise
            progress(
                f"vLLM json_object failed for {name} "
                f"({type(exc).__name__}); retrying json_schema"
            )
        try:
            response = self._create(messages, schema_format)
            return _response_payload(name, response, schema)
        except Exception as schema_error:
            raise schema_error from object_error

    def _create(self, messages: list[dict[str, str]], response_format: dict[str, Any]):
        return self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=self.max_tokens,
            messages=messages,
            response_format=response_format,
        )


def with_json_object_hint(
    messages: list[dict[str, str]], schema: dict[str, Any] | None = None
) -> list[dict[str, str]]:
    """Keep the system prompt first; vLLM rejects a later system message."""
    copied = [dict(item) for item in messages]
    hint = JSON_OBJECT_HINT
    if schema:
        hint += "\n" + json.dumps(schema, separators=(",", ":"))
    if copied and copied[0].get("role") == "system":
        copied[0]["content"] = (
            str(copied[0].get("content") or "").rstrip() + "\n\n" + hint
        )
        return copied
    return [{"role": "system", "content": hint}, *copied]


def _is_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    return "timeout" in name


def _response_payload(
    name: str,
    response: Any,
    schema: dict[str, Any],
) -> dict[str, Any]:
    choice = response.choices[0]
    content = (choice.message.content or "").strip()
    if not content:
        reasoning = getattr(choice.message, "reasoning", None) or getattr(
            choice.message, "reasoning_content", None
        )
        raise ValueError(
            "empty judge response "
            f"(finish_reason={getattr(choice, 'finish_reason', None)!r}, "
            f"reasoning_chars={len(str(reasoning or ''))})"
        )
    progress(f"vLLM response: {name} ({len(content)} chars)")
    payload = _parse_json_object(content)
    _validate_schema(payload, schema, path=name)
    return payload


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


def _validate_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected = schema.get("type")
    if expected == "object":
        if not isinstance(value, dict):
            raise ValueError(f"{path} must be an object")
        missing = [key for key in schema.get("required", []) if key not in value]
        if missing:
            raise ValueError(f"{path} missing required fields: {', '.join(missing)}")
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            extras = sorted(set(value) - set(properties))
            if extras:
                raise ValueError(f"{path} has unexpected fields: {', '.join(extras)}")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], path=f"{path}.{key}")
    elif expected == "array":
        if not isinstance(value, list):
            raise ValueError(f"{path} must be an array")
        item_schema = schema.get("items") or {}
        for index, item in enumerate(value):
            _validate_schema(item, item_schema, path=f"{path}[{index}]")
    elif expected == "string" and not isinstance(value, str):
        raise ValueError(f"{path} must be a string")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} has invalid value {value!r}")


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
