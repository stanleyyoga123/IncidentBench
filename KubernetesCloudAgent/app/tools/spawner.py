import uuid


class AgentSpawner:
    def __init__(self, model: str, base_url: str, knowledge: str, timeout_seconds: int):
        self._model = model
        self._base_url = base_url
        self._knowledge = knowledge
        self._timeout_seconds = timeout_seconds

    def _spawn(self, name: str, system_prompt: str, tools: list[str], max_rounds: int):
        # Avoiding circular import
        from agent import Agent
        from registry.tool import TOOL_REGISTRY

        prompt_parts = [
            system_prompt,
            TOOL_REGISTRY.usage_context(tools),
            self._knowledge,
        ]

        return Agent(
            name=f"{name}-{str(uuid.uuid4())}",
            model=self._model,
            base_url=self._base_url,
            system_prompt="\n\n".join(part for part in prompt_parts if part),
            tools=TOOL_REGISTRY.describe_openai_format(tools),
            max_rounds=max_rounds,
            timeout_seconds=self._timeout_seconds,
        )

    def run(
        self,
        name: str,
        system_prompt: str,
        user_prompt: str,
        tools: list[str],
        max_rounds: int = 10,
    ):
        safe_tools = [tool for tool in tools if tool != "agent_spawner"]
        if not safe_tools:
            return {
                "ok": False,
                "error": "agent_spawner requires at least one non-spawner tool.",
            }
        from registry.tool import TOOL_REGISTRY

        unknown_tools = [tool for tool in safe_tools if tool not in TOOL_REGISTRY.names()]
        if unknown_tools:
            return {
                "ok": False,
                "error": "agent_spawner received unknown tool names.",
                "unknown_tools": unknown_tools,
                "available_tools": sorted(TOOL_REGISTRY.names()),
                "hint": "Use exact registered tool names such as prometheus or loki; query_type is an argument, not a tool suffix.",
            }

        agent = self._spawn(
            name=name,
            system_prompt=system_prompt,
            tools=safe_tools,
            max_rounds=max(5, min(max_rounds, 20)),
        )
        answer = agent.run(user_prompt)
        return {
            "ok": True,
            "agent": name,
            "tools": safe_tools,
            "answer": answer,
        }
