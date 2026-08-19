import json
import re
from typing import Any, Protocol

from analyzer.log import progress


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
        timeout_seconds: float = 180,
    ):
        from openai import OpenAI

        self.model = model
        self.base_url = base_url.rstrip("/")
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=api_key or "EMPTY",
            timeout=timeout_seconds,
        )

    def complete(
        self, name: str, schema: dict[str, Any], messages: list[dict[str, str]]
    ) -> dict[str, Any]:
        progress(f"vLLM request: {name}")
        try:
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": name,
                        "strict": True,
                        "schema": schema,
                    },
                },
            )
        except Exception as exc:
            progress(
                f"vLLM json_schema failed for {name} ({type(exc).__name__}); retrying json_object"
            )
            response = self._client.chat.completions.create(
                model=self.model,
                temperature=0,
                messages=messages
                + [
                    {
                        "role": "system",
                        "content": "Reply with a single JSON object that matches the required schema.",
                    }
                ],
                response_format={"type": "json_object"},
            )
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
