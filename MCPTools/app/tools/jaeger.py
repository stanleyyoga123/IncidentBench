from typing import Any

from tools.utility import http_get_json


class JaegerTool:
    def __init__(self, base_url: str, timeout_seconds: int = 10) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

    def list_services(self) -> dict[str, Any]:
        result = self._api_get("/jaeger/api/services", {})
        if not result.get("ok"):
            return result

        data = (result.get("data") or {}).get("data") or []
        services = sorted(
            {service for service in data if isinstance(service, str) and service}
        )
        return {
            "ok": True,
            "action": "list_services",
            "service_count": len(services),
            "services": services,
        }

    def retrieve_slow_traces(
        self,
        service: str,
        lookback: str = "30m",
        limit: int = 5,
        min_duration: str | None = None,
        max_duration: str | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "service": service,
            "lookback": lookback,
            "limit": max(limit * 4, limit),
        }
        if min_duration:
            params["minDuration"] = min_duration
        if max_duration:
            params["maxDuration"] = max_duration

        result = self._api_get("/jaeger/api/traces", params)
        if not result.get("ok"):
            return result

        traces = (result.get("data") or {}).get("data") or []
        summaries = [self._trace_summary(trace) for trace in traces]
        summaries.sort(key=lambda item: item.get("duration_ms") or 0, reverse=True)
        return {
            "ok": True,
            "action": "slow_traces",
            "service": service,
            "lookback": lookback,
            "requested_samples": limit,
            "candidate_count": len(traces),
            "traces": summaries[:limit],
        }

    def investigate_trace(
        self,
        trace_id: str | None,
    ) -> dict[str, Any]:
        if not trace_id:
            return {"ok": False, "error": "trace_id is required for investigate_trace"}

        result = self._api_get(f"/jaeger/api/traces/{trace_id}", {})
        if not result.get("ok"):
            return result

        traces = (result.get("data") or {}).get("data") or []
        if not traces:
            return {"ok": False, "error": "trace not found", "trace_id": trace_id}

        trace = traces[0]
        spans = trace.get("spans") or []
        span_summaries = [self._span_summary(trace, span) for span in spans]
        span_summaries.sort(key=lambda item: item.get("duration_ms") or 0, reverse=True)
        return {
            "ok": True,
            "action": "investigate_trace",
            "trace": self._trace_summary(trace),
            "slowest_spans": span_summaries[:10],
            "service_breakdown": self._service_breakdown(trace),
        }

    def retrieve_bottleneck(
        self,
        trace_id: str | None,
    ) -> dict[str, Any]:
        investigation = self.investigate_trace(trace_id)
        if not investigation.get("ok"):
            return investigation

        slowest_spans = investigation.get("slowest_spans") or []
        service_breakdown = investigation.get("service_breakdown") or []
        slowest_span = slowest_spans[0] if slowest_spans else None
        slowest_service = service_breakdown[0] if service_breakdown else None
        return {
            "ok": True,
            "action": "bottleneck",
            "trace": investigation.get("trace"),
            "bottleneck": {
                "service": slowest_span.get("service") if slowest_span else None,
                "operation": slowest_span.get("operation") if slowest_span else None,
                "span_duration_ms": (
                    slowest_span.get("duration_ms") if slowest_span else None
                ),
                "service_total_duration_ms": (
                    slowest_service.get("total_duration_ms")
                    if slowest_service
                    else None
                ),
                "reason": "Selected from the slowest span and aggregate service duration in the trace.",
            },
            "slowest_span": slowest_span,
            "slowest_service": slowest_service,
        }

    def _mounted_path(self, path: str) -> str:
        base_path = self.base_url.rstrip("/").split("://", 1)[-1].split("/", 1)
        base_has_mount = len(base_path) == 2 and base_path[1].rstrip("/") == "jaeger"

        if base_has_mount and path.startswith("/jaeger/api/"):
            return path.removeprefix("/jaeger")
        if path.startswith("/jaeger/"):
            return path
        if path.startswith("/api/"):
            return f"/jaeger{path}"
        return path

    def _api_get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        mounted_path = self._mounted_path(path)
        result = http_get_json(
            self.base_url, mounted_path, params, self.timeout_seconds
        )
        if (
            not result.get("ok")
            and result.get("error") == "response was not valid JSON"
        ):
            result["hint"] = (
                "Jaeger returned a non-JSON response. Check that tools.jaeger.base_url points to the Jaeger query API host and that this cluster's mounted /jaeger API path is reachable."
            )
            result["requested_endpoint"] = mounted_path
        return result

    def _trace_summary(self, trace: dict[str, Any]) -> dict[str, Any]:
        spans = trace.get("spans") or []
        start_times = [span.get("startTime", 0) for span in spans]
        end_times = [
            span.get("startTime", 0) + span.get("duration", 0) for span in spans
        ]
        duration_us = max(end_times, default=0) - min(start_times, default=0)
        root_span = self._root_span(spans)
        return {
            "traceID": trace.get("traceID"),
            "span_count": len(spans),
            "duration_ms": round(duration_us / 1000, 2) if duration_us else None,
            "root_operation": root_span.get("operationName") if root_span else None,
            "services": sorted(self._trace_services(trace)),
        }

    def _span_summary(
        self, trace: dict[str, Any], span: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "spanID": span.get("spanID"),
            "operation": span.get("operationName"),
            "service": self._span_service(trace, span),
            "duration_ms": round((span.get("duration") or 0) / 1000, 2),
            "start_time": span.get("startTime"),
        }

    def _service_breakdown(self, trace: dict[str, Any]) -> list[dict[str, Any]]:
        totals: dict[str, dict[str, Any]] = {}
        for span in trace.get("spans") or []:
            service = self._span_service(trace, span) or "unknown"
            item = totals.setdefault(
                service,
                {
                    "service": service,
                    "span_count": 0,
                    "total_duration_ms": 0.0,
                    "max_span_duration_ms": 0.0,
                },
            )
            duration_ms = (span.get("duration") or 0) / 1000
            item["span_count"] += 1
            item["total_duration_ms"] += duration_ms
            item["max_span_duration_ms"] = max(
                item["max_span_duration_ms"], duration_ms
            )

        breakdown = list(totals.values())
        for item in breakdown:
            item["total_duration_ms"] = round(item["total_duration_ms"], 2)
            item["max_span_duration_ms"] = round(item["max_span_duration_ms"], 2)
        breakdown.sort(key=lambda item: item["total_duration_ms"], reverse=True)
        return breakdown

    def _root_span(self, spans: list[dict[str, Any]]) -> dict[str, Any] | None:
        for span in spans:
            if not any(
                ref.get("refType") == "CHILD_OF" for ref in span.get("references", [])
            ):
                return span
        return spans[0] if spans else None

    def _trace_services(self, trace: dict[str, Any]) -> set[str]:
        return {
            service
            for span in trace.get("spans") or []
            if (service := self._span_service(trace, span))
        }

    def _span_service(self, trace: dict[str, Any], span: dict[str, Any]) -> str | None:
        process = (trace.get("processes") or {}).get(span.get("processID"), {})
        return process.get("serviceName")
