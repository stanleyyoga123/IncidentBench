from __future__ import annotations

import asyncio
from typing import Any

import httpx

from collector.metrics.query import QueryBuilder


class PrometheusConfigurationError(RuntimeError):
    """Prometheus is reachable but required recording rules are not loaded."""


class PrometheusCollector:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: int = 10,
        max_concurrency: int = 4,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))
        self._client = client or httpx.AsyncClient(timeout=timeout_seconds)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def query_range(
        self,
        promql: str,
        start: int | float,
        end: int | float,
        step: int | float,
    ) -> dict[str, Any]:
        async with self._semaphore:
            payload = await self._get_json(
                "/api/v1/query_range",
                {
                    "query": promql,
                    "start": start,
                    "end": end,
                    "step": step,
                },
            )
        data = payload.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("result"), list):
            raise ValueError("malformed Prometheus range-query response")
        return payload

    async def collect_range(
        self,
        *,
        start: int | float,
        end: int | float,
        step: int | float,
        namespace_regex: str,
        deployment_regex: str = ".+",
        excluded_node_regex: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        queries = {
            name: QueryBuilder.build(
                name,
                namespace_regex=namespace_regex,
                deployment_regex=deployment_regex,
                excluded_node_regex=excluded_node_regex,
            )
            for name in QueryBuilder.names()
        }
        responses = await asyncio.gather(
            *(
                self.query_range(
                    promql=promql,
                    start=start,
                    end=end,
                    step=step,
                )
                for promql in queries.values()
            )
        )
        return {
            name: {"query": promql, "response": response}
            for (name, promql), response in zip(queries.items(), responses)
        }

    async def verify_recording_rules(self, required_names: set[str]) -> None:
        payload = await self._get_json("/api/v1/rules", {"type": "record"})
        data = payload.get("data")
        groups = data.get("groups") if isinstance(data, dict) else None
        if not isinstance(groups, list):
            raise ValueError("malformed Prometheus rules response")

        loaded_names = {
            rule.get("name")
            for group in groups
            if isinstance(group, dict)
            for rule in group.get("rules", [])
            if isinstance(rule, dict) and isinstance(rule.get("name"), str)
        }
        missing = sorted(required_names - loaded_names)
        if missing:
            raise PrometheusConfigurationError(
                "required Prometheus recording rules are missing: " + ", ".join(missing)
            )

    async def _get_json(
        self,
        path: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self._client.get(f"{self._base_url}{path}", params=params)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("status") != "success":
            error = payload.get("error") if isinstance(payload, dict) else None
            raise ValueError(f"Prometheus API returned an error: {error or payload!r}")
        return payload
