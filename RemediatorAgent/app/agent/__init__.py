import uuid
import time
import json
from typing import Any
from dataclasses import dataclass

from langfuse.openai import OpenAI
from langfuse import get_client, propagate_attributes

from openai.types.chat import ChatCompletionMessage
from pydantic import BaseModel
from registry.tool import TOOL_REGISTRY

from prompt.agent import CONTEXT_TRIMMING_PROMPT, FORCED_FINAL_ANSWER_PROMPT

from common.decorator import retry
from common.logger.console import get_logger

LOGGER = get_logger("Agent")


@dataclass(frozen=True)
class RoundOutput:
    is_finished: bool
    usage: int
    exceed_context: bool
    message: ChatCompletionMessage


class Agent:
    def __init__(
        self,
        name: str,
        model: str,
        base_url: str,
        system_prompt: str,
        tools: list[dict[str, Any]],
        max_rounds: int = 5,
        timeout_seconds: int = 20,
        session_id: str = None,
        max_context: int = 131072,
        context_threshold: float = 0.75,
        temperature: float = 1.0,
        top_p: float = 0.95,
        top_k: int = 20,
        min_p: float = 0.0,
        presence_penalty: float = 1.5,
        repetition_penalty: float = 1.0,
        api_key: str = "EMPTY",
    ):
        self._model = model
        self._name = name
        self._tools = tools
        self._max_rounds = max_rounds
        self._max_context = max_context
        self._context_threshold = context_threshold
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._min_p = min_p
        self._presence_penalty = presence_penalty
        self._repetition_penalty = repetition_penalty

        self._openai_client = OpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout_seconds,
        )
        self._langfuse_client = get_client()
        self._session_id = session_id if session_id else str(uuid.uuid4())
        self._messages = [{"role": "system", "content": system_prompt}]

    @retry(retries=3, delay=1.0, backoff=2.0)
    def _exec_llm_tool_calls(self):
        response = self._openai_client.chat.completions.create(
            model=self._model,
            messages=self._messages,
            stream=False,
            tools=self._tools,
            tool_choice="auto",
            parallel_tool_calls=False,
            name=f"tool_selection",
            top_p=self._top_p,
            temperature=self._temperature,
            presence_penalty=self._presence_penalty,
            extra_body={
                "min_p": self._min_p,
                "top_k": self._top_k,
                "repetition_penalty": self._repetition_penalty,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        )
        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []
        self._append_assistant(assistant_message)

        usage = self._usage_total(response)
        exceed_context = self._is_context_near_limit(usage)

        if not tool_calls:
            return RoundOutput(
                is_finished=True,
                usage=usage,
                exceed_context=exceed_context,
                message=assistant_message,
            )
        return RoundOutput(
            is_finished=False,
            usage=usage,
            exceed_context=exceed_context,
            message=assistant_message,
        )

    def _exec_trim_context(self):
        LOGGER.info("Automatically compacting context...")
        self._append_context_trimming()
        response = self._openai_client.chat.completions.create(
            model=self._model,
            messages=self._messages,
            stream=False,
            name=f"context_trimming",
            top_p=self._top_p,
            temperature=self._temperature,
            presence_penalty=self._presence_penalty,
            extra_body={
                "min_p": self._min_p,
                "top_k": self._top_k,
                "repetition_penalty": self._repetition_penalty,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        )
        assistant_message = response.choices[0].message
        usage = self._usage_total(response)
        self._messages = [
            self._messages[0],  # Original system prompt
            self._messages[1],  # Original user task
            {"role": "assistant", "content": assistant_message.content},
        ]
        return RoundOutput(
            is_finished=False,
            usage=usage,
            exceed_context=False,
            message=assistant_message,
        )

    @retry(retries=3, delay=1.0, backoff=2.0)
    def _exec_forced_final_answer(self):
        response = self._openai_client.chat.completions.create(
            model=self._model,
            messages=self._messages,
            stream=False,
            name=f"forced_final_answer",
            top_p=self._top_p,
            temperature=self._temperature,
            presence_penalty=self._presence_penalty,
            extra_body={
                "min_p": self._min_p,
                "top_k": self._top_k,
                "repetition_penalty": self._repetition_penalty,
                "chat_template_kwargs": {"enable_thinking": True},
            },
        )
        assistant_message = response.choices[0].message
        self._append_assistant(assistant_message)
        usage = self._usage_total(response)
        return RoundOutput(
            is_finished=True,
            usage=usage,
            exceed_context=False,
            message=assistant_message,
        )

    @retry(retries=3, delay=1.0, backoff=2.0)
    def _exec_tool(self, name: str, arguments: str):
        return TOOL_REGISTRY.run(name, json.loads(arguments))

    def run(self, user_prompt: str) -> str:
        with propagate_attributes(
            trace_name=self._name,
            metadata={
                "name": self._name,
                "model": self._model,
                "max_rounds": str(self._max_rounds),
            },
        ):
            self._append_user(user_prompt)
            final_answer = None
            with self._langfuse_client.start_as_current_observation(
                as_type="span",
                name=self._name,
                input=self._messages,
            ) as execution_span:
                for turn in range(1, self._max_rounds + 1):
                    with self._langfuse_client.start_as_current_observation(
                        as_type="span", name=f"turn_{turn}", input=self._messages
                    ) as turn_span:
                        if self._should_trim_context():
                            with self._langfuse_client.start_as_current_observation(
                                as_type="span",
                                name=f"turn_{turn}.context_trimming",
                                input=self._messages,
                            ) as trimming_span:
                                context = self._exec_trim_context()
                                trimming_span.update(output=context)

                        start = time.time()
                        output = self._exec_llm_tool_calls()
                        stop = time.time()
                        LOGGER.info(f"Execution time: {stop-start}")

                        turn_span.update(
                            metadata={"reasoning": output.message.reasoning}
                        )
                        LOGGER.info(f"Token usage: {output.usage}")

                        if output.is_finished:
                            break

                        tool_calls = output.message.tool_calls
                        for index, tool_call in enumerate(tool_calls):
                            name = tool_call.function.name
                            args = tool_call.function.arguments

                            with self._langfuse_client.start_as_current_observation(
                                as_type="span",
                                name=f"tool.{name}.{tool_call.id}",
                                input={"arguments": args},
                            ) as tool_span:
                                tool_output = self._exec_tool(name, args)
                                tool_output = self._serialize_tool_output(tool_output)
                                tool_span.update(metadata={"tool": name, "args": args})
                                tool_span.update(output=tool_output)

                            self._append_tool(tool_call.id, tool_output)
                            if (
                                index == len(tool_calls) - 1
                                and self._should_trim_context()
                            ):
                                with self._langfuse_client.start_as_current_observation(
                                    as_type="span",
                                    name=f"turn_{turn}.context_trimming",
                                    input=self._messages,
                                ) as trimming_span:
                                    context = self._exec_trim_context()
                                    trimming_span.update(output=context)

                if output.is_finished:
                    final_answer = output.message.content
                else:
                    reason = "forced_final_turn"
                    LOGGER.info(f"Turn {turn} - {reason}")
                    with self._langfuse_client.start_as_current_observation(
                        as_type="span", name=reason
                    ):
                        self._append_force_summary()
                        output = self._exec_forced_final_answer()
                        final_answer = output.message.content
                execution_span.update(output=final_answer)

            return final_answer

    def _append_assistant(self, assistant_message: ChatCompletionMessage):
        self._messages.append(assistant_message.model_dump(exclude_none=True))

    def _append_user(self, prompt: str):
        self._messages.append({"role": "user", "content": prompt})

    def _append_tool(self, identifier: Any, output: Any):
        self._messages.append(
            {
                "role": "tool",
                "tool_call_id": identifier,
                "content": output,
            }
        )

    def _append_force_summary(self):
        self._messages.append({"role": "user", "content": FORCED_FINAL_ANSWER_PROMPT})

    def _append_context_trimming(self):
        self._messages.append({"role": "user", "content": CONTEXT_TRIMMING_PROMPT})

    def _serialize_tool_output(self, output: Any) -> str:
        if isinstance(output, str):
            return output
        if isinstance(output, BaseModel):
            return output.model_dump_json()
        return json.dumps(output, default=str)

    def _usage_total(self, response: Any) -> int:
        usage = getattr(response, "usage", None)
        total_tokens = getattr(usage, "total_tokens", None)
        if total_tokens is None:
            LOGGER.warning("LLM response did not include total token usage.")
            return 0
        return total_tokens

    def _is_context_near_limit(self, usage: int) -> bool:
        if usage <= 0:
            return False
        return usage > self._context_threshold * self._max_context

    def _should_trim_context(self) -> bool:
        if len(self._messages) <= 2:
            return False
        estimated_tokens = len(json.dumps(self._messages, default=str).split()) * 4
        LOGGER.info(f"Estimated context tokens: {estimated_tokens}")
        return estimated_tokens > self._context_threshold * self._max_context


if __name__ == "__main__":
    agent = Agent(
        name="testing-agent",
        model="Qwen/Qwen3.6-35B-A3B",
        base_url="http://localhost:8000/v1",
        system_prompt="You are a helpful agent",
        tools=TOOL_REGISTRY.describe_openai_format(
            [
                "kubectl",
                "prometheus",
                "loki",
                "jaeger.list_services",
                "jaeger.retrieve_slow_traces",
                "jaeger.investigate_trace",
                "jaeger.retrieve_bottleneck",
                "network.topology",
                "network.latency_matrix",
                "network.bandwidth",
                "network.path",
                "network.dns",
                "network.tcp_connect",
                "agent_spawner",
            ]
        ),
        max_rounds=20,
        timeout_seconds=60,
    )
    user_prompt = "Give me the current condition of the microservice system inside online-boutique namespace. I want you to retrieve the last 30 minutes states per deployments (like cpu metrics, memory, network, rps, any error, etc)"
    output = agent.run(user_prompt)

    print(output)
