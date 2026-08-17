import sys
import types
from unittest import TestCase


if "langfuse" not in sys.modules:
    langfuse = types.ModuleType("langfuse")
    langfuse.get_client = lambda: None
    langfuse.propagate_attributes = lambda **_: None
    sys.modules["langfuse"] = langfuse
    langfuse_openai = types.ModuleType("langfuse.openai")
    langfuse_openai.OpenAI = object
    sys.modules["langfuse.openai"] = langfuse_openai

if "openai.types.chat" not in sys.modules:
    openai = types.ModuleType("openai")
    openai_types = types.ModuleType("openai.types")
    openai_types_chat = types.ModuleType("openai.types.chat")
    openai_types_chat.ChatCompletionMessage = object
    sys.modules["openai"] = openai
    sys.modules["openai.types"] = openai_types
    sys.modules["openai.types.chat"] = openai_types_chat

if "ansible_runner" not in sys.modules:
    ansible_runner = types.ModuleType("ansible_runner")
    ansible_runner.run = lambda *_, **__: None
    sys.modules["ansible_runner"] = ansible_runner

from agent import Agent


class AgentContextTest(TestCase):
    def test_trims_tool_history_before_it_reaches_context_threshold(self):
        agent = Agent.__new__(Agent)
        agent._max_context = 100
        agent._context_threshold = 0.75
        agent._messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
            {"role": "tool", "content": " ".join(["result"] * 20)},
        ]

        self.assertTrue(agent._should_trim_context())

    def test_does_not_trim_original_system_and_user_prompts(self):
        agent = Agent.__new__(Agent)
        agent._max_context = 10
        agent._context_threshold = 0.75
        agent._messages = [
            {"role": "system", "content": "large system prompt"},
            {"role": "user", "content": "large user task"},
        ]

        self.assertFalse(agent._should_trim_context())

    def test_tool_output_can_trigger_trimming_immediately_after_append(self):
        agent = Agent.__new__(Agent)
        agent._max_context = 100
        agent._context_threshold = 0.75
        agent._messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
        ]

        agent._append_tool("call-1", " ".join(["result"] * 20))

        self.assertTrue(agent._should_trim_context())
