import json
import re
import shlex
import subprocess
from collections.abc import Mapping, Sequence
from typing import Any

import httpx


def run_command(args: list[str], timeout_seconds: int) -> dict[str, Any]:
    try:
        process = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return {
            "ok": process.returncode == 0,
            "command": " ".join(shlex.quote(arg) for arg in args),
            "returncode": process.returncode,
            "stdout": process.stdout.strip(),
            "stderr": process.stderr.strip(),
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "command timed out",
            "command": " ".join(shlex.quote(arg) for arg in args),
            "timeout_seconds": timeout_seconds,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "command": " ".join(shlex.quote(arg) for arg in args),
        }


def http_get_json(
    base_url: str,
    path: str,
    params: dict[str, Any] | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/" + path.lstrip("/")
    response = None
    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.get(url, params=params or {})
        response.raise_for_status()
        try:
            data = response.json()
        except ValueError as exc:
            return {
                "ok": False,
                "error": "response was not valid JSON",
                "url": url,
                "params": params or {},
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body": response.text[:2000],
                "exception_type": type(exc).__name__,
            }
        return {
            "ok": True,
            "url": url,
            "params": params or {},
            "status_code": response.status_code,
            "data": data,
        }
    except httpx.HTTPStatusError as exc:
        return {
            "ok": False,
            "error": "http status error",
            "url": url,
            "params": params or {},
            "status_code": exc.response.status_code,
            "body": exc.response.text[:2000],
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "url": url,
            "params": params or {},
            "status_code": response.status_code if response is not None else None,
            "content_type": (
                response.headers.get("content-type") if response is not None else None
            ),
            "body": response.text[:2000] if response is not None else None,
            "exception_type": type(exc).__name__,
        }


def apply_grep(text: str, grep: str | None) -> dict[str, Any]:
    lines = text.splitlines()
    filtered = lines
    grep_error = None
    if grep:
        try:
            pattern = re.compile(grep)
            filtered = [line for line in lines if pattern.search(line)]
        except re.error as exc:
            grep_error = str(exc)
            filtered = [line for line in lines if grep in line]
    return {
        "stdout": "\n".join(filtered).strip(),
        "grep": grep,
        "grep_error": grep_error,
        "line_count": len(filtered),
        "unfiltered_line_count": len(lines),
    }


def apply_output_filter(data: Any, spec: dict[str, Any] | None) -> Any:
    if not spec:
        return data

    result = data
    include_paths = _string_list(spec.get("include_paths"))
    if include_paths:
        result = {path: _get_path(data, path) for path in include_paths}

    for path in _string_list(spec.get("exclude_paths")):
        result = _drop_path(result, path)

    return _compact(
        result,
        keys=set(_string_list(spec.get("keys"))),
        contains=spec.get("contains"),
        max_items=int(spec.get("max_items", 100)),
        max_depth=int(spec.get("max_depth", 6)),
        max_string_length=int(spec.get("max_string_length", 2000)),
    )


def _compact(
    value: Any,
    *,
    keys: set[str],
    contains: str | None,
    max_items: int,
    max_depth: int,
    max_string_length: int,
    depth: int = 0,
) -> Any:
    if depth >= max_depth:
        return _summarize_leaf(value)

    if isinstance(value, Mapping):
        items = list(value.items())
        limited = items[:max_items]
        out = {}
        for key, child in limited:
            child_keys = set() if str(key) in keys else keys
            compacted = _compact(
                child,
                keys=child_keys,
                contains=contains,
                max_items=max_items,
                max_depth=max_depth,
                max_string_length=max_string_length,
                depth=depth + 1,
            )
            if (
                not keys
                or str(key) in keys
                or (
                    isinstance(child, Mapping | list | tuple | set)
                    and _has_content(compacted)
                )
            ):
                out[key] = compacted
        if len(items) > max_items:
            out["_truncated_items"] = len(items) - max_items
        return out

    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        items = list(value)
        if contains:
            structured = [
                item for item in items if isinstance(item, Mapping | list | tuple | set)
            ]
            if structured:
                items = [
                    item for item in items if contains in json.dumps(item, default=str)
                ]
        return [
            _compact(
                item,
                keys=keys,
                contains=contains,
                max_items=max_items,
                max_depth=max_depth,
                max_string_length=max_string_length,
                depth=depth + 1,
            )
            for item in items[:max_items]
        ]

    if isinstance(value, str) and len(value) > max_string_length:
        return (
            value[:max_string_length]
            + f"...[truncated {len(value) - max_string_length} chars]"
        )
    return value


def _get_path(data: Any, path: str) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part)
        elif isinstance(current, Sequence) and not isinstance(
            current, str | bytes | bytearray
        ):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return current


def _drop_path(data: Any, path: str) -> Any:
    if not path:
        return data
    parts = path.split(".")
    if isinstance(data, Mapping):
        out = dict(data)
        if len(parts) == 1:
            out.pop(parts[0], None)
        elif parts[0] in out:
            out[parts[0]] = _drop_path(out[parts[0]], ".".join(parts[1:]))
        return out
    if isinstance(data, list):
        return [_drop_path(item, path) for item in data]
    return data


def _summarize_leaf(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            "_type": "object",
            "_keys": list(value.keys())[:20],
            "_key_count": len(value),
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return {"_type": "list", "_count": len(value)}
    return value


def _has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, Mapping | list | tuple | set):
        return bool(value)
    return True


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return [str(item) for item in value]
    return []
