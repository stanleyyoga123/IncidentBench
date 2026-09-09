from __future__ import annotations

import json
import logging
import re
from typing import Any, Protocol

from .penalty import (
    PenaltySet,
    build_penalty_policy,
    build_penalty_schema,
    parse_penalty_judgements,
)
from .rubric import (
    REASON_MAX_LENGTH,
    KindRubric,
    Rubric,
    build_policy,
    build_response_schema,
    parse_classifications,
)


LOGGER = logging.getLogger("grader.judge")


PROMPT_VERSION = "production-incident-grader-v3"
DEFAULT_JUDGE_URL = "http://localhost:8000/v1"
DEFAULT_JUDGE_MODEL = "Qwen/Qwen3.6-35B-A3B"
DEFAULT_TIMEOUT_SECONDS = 600.0
DEFAULT_MAX_TOKENS = 8192


class JudgeClient(Protocol):
    model: str

    def grade(self, kind: str, payload: dict[str, Any]) -> dict[str, dict[str, str]]:
        ...

    def grade_penalties(
        self, penalty_set: PenaltySet, payload: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        ...


class OpenAICompatibleJudge:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        rubric: Rubric,
        token: str = "EMPTY",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ) -> None:
        from openai import OpenAI

        self.model = model
        self.base_url = base_url.rstrip("/")
        self.rubric = rubric
        self.max_tokens = max_tokens
        self._client = OpenAI(
            base_url=self.base_url,
            api_key=token or "EMPTY",
            timeout=timeout_seconds,
            max_retries=0,
        )

    def grade(self, kind: str, payload: dict[str, Any]) -> dict[str, dict[str, str]]:
        kind_rubric = self.rubric.kind(kind)
        return self._structured(
            policy=build_policy(kind_rubric),
            schema_name=f"{kind}_rubric",
            schema=build_response_schema(kind_rubric),
            payload=payload,
            parse=lambda content: parse_judge_response(kind_rubric, content),
        )

    def grade_penalties(
        self, penalty_set: PenaltySet, payload: dict[str, Any]
    ) -> dict[str, dict[str, Any]]:
        return self._structured(
            policy=build_penalty_policy(penalty_set),
            schema_name="remediation_penalties",
            schema=build_penalty_schema(penalty_set),
            payload=payload,
            parse=lambda content: parse_penalty_judge_response(penalty_set, content),
        )

    def _structured(
        self,
        *,
        policy: str,
        schema_name: str,
        schema: dict[str, Any],
        payload: dict[str, Any],
        parse,
    ):
        messages = [
            {"role": "system", "content": policy},
            {"role": "user", "content": json.dumps(payload, sort_keys=True)},
        ]
        schema_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }
        first_error: Exception | None = None
        try:
            response = self._create(messages, schema_format)
            return parse(_content(response))
        except Exception as exc:
            first_error = exc
            LOGGER.debug(
                "strict json-schema judge request failed; retrying with json_object error_type=%s detail=%s",
                type(exc).__name__,
                str(exc) if isinstance(exc, ValueError) else "suppressed",
            )
        try:
            hinted = [dict(messages[0]), dict(messages[1])]
            hinted[0]["content"] += (
                "\n\nRequired JSON schema: "
                + json.dumps(schema, separators=(",", ":"))
                + f"\nEach reason must be at most {REASON_MAX_LENGTH} characters."
            )
            response = self._create(hinted, {"type": "json_object"})
            return parse(_content(response))
        except Exception as exc:
            raise exc from first_error

    def _create(self, messages: list[dict[str, str]], response_format: dict[str, Any]):
        return self._client.chat.completions.create(
            model=self.model,
            temperature=0,
            max_tokens=self.max_tokens,
            messages=messages,
            response_format=response_format,
        )


def build_payload(
    *,
    kind: str,
    scenario: str,
    ground_truth: dict[str, str],
    result: Any,
) -> dict[str, Any]:
    expected = ground_truth["rca" if kind == "rca" else "remediation"]
    return {
        "scenario": scenario,
        "ground_truth": expected,
        "agent_result": result,
    }


def build_penalty_payload(
    payload: dict[str, Any],
    penalty_set: PenaltySet,
    chaos_manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "scenario": payload["scenario"],
        "ground_truth": payload["ground_truth"],
        "chaos_manifests": chaos_manifests,
        "agent_result": payload["agent_result"],
        "penalties": penalty_set.judge_items(),
    }


def parse_judge_response(
    kind_rubric: KindRubric, content: str
) -> dict[str, dict[str, str]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("judge response is not JSON")
        payload = json.loads(match.group(0))
    return parse_classifications(kind_rubric, payload)


def parse_penalty_judge_response(
    penalty_set: PenaltySet, content: str
) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            raise ValueError("penalty judge response is not JSON")
        payload = json.loads(match.group(0))
    return parse_penalty_judgements(penalty_set, payload)


def _content(response: Any) -> str:
    choice = response.choices[0]
    content = (choice.message.content or "").strip()
    if not content:
        reasoning = getattr(choice.message, "reasoning", None) or getattr(
            choice.message, "reasoning_content", None
        )
        raise ValueError(
            "judge returned an empty response "
            f"(finish_reason={getattr(choice, 'finish_reason', None)!r}, "
            f"reasoning_chars={len(str(reasoning or ''))})"
        )
    return content
