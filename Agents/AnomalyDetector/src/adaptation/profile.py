from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


DetectorMethod = Literal["z_score", "threshold"]


class ProfileNotFoundError(KeyError):
    pass


class ProfileConflictError(ValueError):
    pass


class ProfileValidationError(ValueError):
    pass


class DetectorProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    version: int = Field(ge=1)
    method: DetectorMethod
    namespace: str
    resource: str
    name: str
    metric: str
    parameters: dict[str, Any]
    mutable_parameters: tuple[str, ...]
    source: Literal["default", "operator", "reset"]
    reason: str
    active: bool = True
    created_at: datetime

    @property
    def scope_key(self) -> tuple[str, str, str, str, str]:
        return self.method, self.namespace, self.resource, self.name, self.metric

    def provenance_lines(self) -> list[str]:
        return [
            f"detector_profile_id = {self.id}",
            f"detector_profile_version = {self.version}",
            f"detector_profile_source = {self.source}",
            f"detector_profile_namespace = {self.namespace}",
            *(
                f"detector_parameter_{key} = {value}"
                for key, value in sorted(self.parameters.items())
            ),
        ]


def _z_score_defaults() -> dict[str, dict[str, Any]]:
    common = {
        "threshold": 4.0,
        "lookback": 60,
        "min_history": 30,
        "n_tail": 3,
        "epsilon": 1e-8,
        "min_normalized_std_threshold": 0.05,
        "min_constant_fraction": 0.9,
        "consecutive_anomalies_required": 3,
    }
    cpu_percent = common | {"direction": "high", "min_absolute_delta": 5.0}
    response_time = common | {
        "threshold": 3.0,
        "direction": "high",
        "min_absolute_delta": 0.10,
        "min_relative_delta": 0.50,
    }
    error_rate = common | {"direction": "high", "min_absolute_delta": 0.01}
    instance_count = common | {"direction": "both", "min_absolute_delta": 1.0}
    relative_change = common | {
        "direction": "both",
        "min_relative_delta": 0.10,
    }
    cpu_usage = common | {"direction": "high", "min_relative_delta": 0.10}
    return {
        "deployment_cpu_request_utilization_percent": cpu_percent,
        "deployment_disk_io_bytes_per_second": relative_change,
        "deployment_network_io_bytes_per_second": relative_change,
        "deployment_cpu_usage": cpu_usage,
        "app_instance_count": instance_count,
        "traffic_rps": relative_change,
        "response_time_p95_seconds": response_time,
        "http_5xx_rate": error_rate,
        "node_cpu_utilization_percent": cpu_percent,
        "node_network_io_bytes_per_second": relative_change,
    }


def _threshold_defaults() -> dict[str, dict[str, Any]]:
    common = {"consecutive_anomalies_required": 3}
    return {
        "deployment_cpu_request_utilization_percent": common
        | {"threshold": 90.0, "direction": "high"},
        "deployment_memory_request_utilization_percent": common
        | {"threshold": 90.0, "direction": "high"},
        "response_time_p95_seconds": common
        | {"threshold": 1.0, "direction": "high"},
        "http_5xx_rate": common | {"threshold": 0.05, "direction": "high"},
        "app_instance_count": common | {"threshold": 1.0, "direction": "low"},
        "node_cpu_utilization_percent": common
        | {"threshold": 90.0, "direction": "high"},
        "node_memory_utilization_percent": common
        | {"threshold": 90.0, "direction": "high"},
    }


DEFAULT_PARAMETERS: dict[DetectorMethod, dict[str, dict[str, Any]]] = {
    "z_score": _z_score_defaults(),
    "threshold": _threshold_defaults(),
}

MUTABLE_PARAMETERS: dict[DetectorMethod, tuple[str, ...]] = {
    "z_score": (
        "threshold",
        "lookback",
        "min_history",
        "n_tail",
        "min_absolute_delta",
        "min_relative_delta",
        "consecutive_anomalies_required",
    ),
    "threshold": (
        "threshold",
        "n_tail",
        "consecutive_anomalies_required",
    ),
}


def mutable_parameters(
    method: DetectorMethod,
    metric: str,
) -> tuple[str, ...]:
    parameters = MUTABLE_PARAMETERS[method]
    if method == "threshold" and metric == "app_instance_count":
        return tuple(parameter for parameter in parameters if parameter != "threshold")
    return parameters

THRESHOLD_BOUNDS: dict[str, tuple[float, float] | None] = {
    "deployment_cpu_request_utilization_percent": (70.0, 100.0),
    "deployment_memory_request_utilization_percent": (70.0, 100.0),
    "response_time_p95_seconds": (0.1, 10.0),
    "http_5xx_rate": (0.001, 0.50),
    "app_instance_count": None,
    "node_cpu_utilization_percent": (70.0, 100.0),
    "node_memory_utilization_percent": (70.0, 100.0),
}


class DetectorProfileRegistry:
    """Thread-safe, versioned runtime detector profiles.

    Revisions are intentionally in-memory in this first control-plane version.
    The public API exposes that limitation so callers do not mistake a runtime
    change for durable configuration.
    """

    persistence = "in_memory"

    def __init__(self) -> None:
        self._lock = RLock()
        self._profiles: dict[str, DetectorProfile] = {}
        self._history: dict[str, list[DetectorProfile]] = {}
        self._active_by_scope: dict[tuple[str, str, str, str, str], str] = {}
        self._default_parameters: dict[str, dict[str, Any]] = {}
        self._install_defaults()

    def list_active(self) -> list[DetectorProfile]:
        with self._lock:
            return sorted(
                (
                    profile.model_copy(deep=True)
                    for profile in self._profiles.values()
                    if profile.active
                ),
                key=lambda profile: profile.scope_key,
            )

    def get(self, profile_id: str) -> DetectorProfile:
        with self._lock:
            profile = self._profiles.get(profile_id)
            if profile is None:
                raise ProfileNotFoundError(profile_id)
            return profile.model_copy(deep=True)

    def history(self, profile_id: str) -> list[DetectorProfile]:
        with self._lock:
            revisions = self._history.get(profile_id)
            if revisions is None:
                raise ProfileNotFoundError(profile_id)
            return [revision.model_copy(deep=True) for revision in revisions]

    def resolve(
        self,
        method: DetectorMethod,
        resource: str,
        name: str,
        metric: str,
        namespace: str = "*",
    ) -> DetectorProfile | None:
        candidates = (
            (method, namespace, resource, name, metric),
            (method, namespace, resource, "*", metric),
            (method, "*", resource, name, metric),
            (method, "*", resource, "*", metric),
            (method, "*", "*", "*", metric),
        )
        with self._lock:
            for scope in candidates:
                profile_id = self._active_by_scope.get(scope)
                if profile_id is not None:
                    return self._profiles[profile_id].model_copy(deep=True)
        return None

    def create_override(
        self,
        *,
        method: DetectorMethod,
        resource: str,
        name: str,
        metric: str,
        changes: dict[str, Any],
        reason: str,
        namespace: str = "*",
    ) -> DetectorProfile:
        namespace = self._scope_value(namespace, "namespace")
        resource = self._scope_value(resource, "resource")
        name = self._scope_value(name, "name")
        scope = (method, namespace, resource, name, metric)
        with self._lock:
            if scope in self._active_by_scope:
                raise ProfileConflictError("an active profile already exists for this scope")
            base = self.resolve(method, resource, name, metric, namespace)
            if base is None:
                raise ProfileValidationError(
                    f"method {method!r} does not support metric {metric!r}"
                )
            parameters = self._merge_and_validate(method, metric, base.parameters, changes)
            profile = DetectorProfile(
                id=str(uuid4()),
                version=1,
                method=method,
                namespace=namespace,
                resource=resource,
                name=name,
                metric=metric,
                parameters=parameters,
                mutable_parameters=mutable_parameters(method, metric),
                source="operator",
                reason=self._reason(reason),
                created_at=datetime.now(timezone.utc),
            )
            self._store(profile)
            return profile.model_copy(deep=True)

    def update(
        self,
        profile_id: str,
        *,
        changes: dict[str, Any],
        reason: str,
        expected_version: int | None = None,
    ) -> DetectorProfile:
        with self._lock:
            current = self._require_active(profile_id)
            self._check_version(current, expected_version)
            parameters = self._merge_and_validate(
                current.method,
                current.metric,
                current.parameters,
                changes,
            )
            profile = current.model_copy(
                update={
                    "version": current.version + 1,
                    "parameters": parameters,
                    "source": "operator",
                    "reason": self._reason(reason),
                    "created_at": datetime.now(timezone.utc),
                },
                deep=True,
            )
            self._store(profile)
            return profile.model_copy(deep=True)

    def reset(
        self,
        profile_id: str,
        *,
        reason: str,
        expected_version: int | None = None,
    ) -> DetectorProfile:
        with self._lock:
            current = self._require_active(profile_id)
            self._check_version(current, expected_version)
            if current.resource == "*" and current.name == "*":
                parameters = self._default_parameters[current.id].copy()
                profile = current.model_copy(
                    update={
                        "version": current.version + 1,
                        "parameters": parameters,
                        "source": "reset",
                        "reason": self._reason(reason),
                        "created_at": datetime.now(timezone.utc),
                    },
                    deep=True,
                )
            else:
                profile = current.model_copy(
                    update={
                        "version": current.version + 1,
                        "source": "reset",
                        "reason": self._reason(reason),
                        "active": False,
                        "created_at": datetime.now(timezone.utc),
                    },
                    deep=True,
                )
            self._store(profile)
            return profile.model_copy(deep=True)

    def _install_defaults(self) -> None:
        now = datetime.now(timezone.utc)
        for method, metrics in DEFAULT_PARAMETERS.items():
            for metric, parameters in metrics.items():
                profile_id = f"default-{method.replace('_', '-')}-{metric.replace('_', '-')}"
                validated = self._validate_parameters(method, metric, parameters.copy())
                profile = DetectorProfile(
                    id=profile_id,
                    version=1,
                    method=method,
                    namespace="*",
                    resource="*",
                    name="*",
                    metric=metric,
                    parameters=validated,
                    mutable_parameters=mutable_parameters(method, metric),
                    source="default",
                    reason="built-in detector defaults",
                    created_at=now,
                )
                self._default_parameters[profile_id] = validated.copy()
                self._store(profile)

    def _store(self, profile: DetectorProfile) -> None:
        previous = self._profiles.get(profile.id)
        if previous is not None and previous.scope_key != profile.scope_key:
            raise ProfileConflictError("profile scope cannot change")
        self._profiles[profile.id] = profile
        self._history.setdefault(profile.id, []).append(profile)
        if profile.active:
            self._active_by_scope[profile.scope_key] = profile.id
        else:
            self._active_by_scope.pop(profile.scope_key, None)

    def _require_active(self, profile_id: str) -> DetectorProfile:
        profile = self._profiles.get(profile_id)
        if profile is None or not profile.active:
            raise ProfileNotFoundError(profile_id)
        return profile

    def _merge_and_validate(
        self,
        method: DetectorMethod,
        metric: str,
        current: dict[str, Any],
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        if not changes:
            raise ProfileValidationError("at least one parameter change is required")
        immutable = sorted(set(changes) - set(mutable_parameters(method, metric)))
        if immutable:
            raise ProfileValidationError(
                f"parameters are unknown or immutable: {', '.join(immutable)}"
            )
        return self._validate_parameters(method, metric, current | changes)

    def _validate_parameters(
        self,
        method: DetectorMethod,
        metric: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if method == "z_score":
            self._bounded_number(parameters, "threshold", 2.5, 8.0)
            self._bounded_integer(parameters, "lookback", 30, 120)
            self._bounded_integer(parameters, "min_history", 30, parameters["lookback"])
            self._bounded_integer(parameters, "n_tail", 1, 10)
            self._bounded_integer(parameters, "consecutive_anomalies_required", 1, 10)
            if parameters["consecutive_anomalies_required"] > parameters["n_tail"]:
                raise ProfileValidationError(
                    "consecutive_anomalies_required cannot exceed n_tail"
                )
            self._optional_nonnegative(parameters, "min_absolute_delta")
            self._optional_bounded(parameters, "min_relative_delta", 0.0, 5.0)
            return parameters

        bounds = THRESHOLD_BOUNDS.get(metric)
        if bounds is None:
            if metric != "app_instance_count":
                raise ProfileValidationError(f"unsupported threshold metric: {metric}")
        else:
            self._bounded_number(parameters, "threshold", *bounds)
        self._bounded_integer(parameters, "consecutive_anomalies_required", 1, 10)
        if "n_tail" in parameters:
            self._bounded_integer(parameters, "n_tail", 1, 10)
            if parameters["consecutive_anomalies_required"] > parameters["n_tail"]:
                raise ProfileValidationError(
                    "consecutive_anomalies_required cannot exceed n_tail"
                )
        return parameters

    @staticmethod
    def _bounded_number(
        parameters: dict[str, Any], key: str, minimum: float, maximum: float
    ) -> None:
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ProfileValidationError(f"{key} must be numeric")
        if not isfinite(float(value)):
            raise ProfileValidationError(f"{key} must be finite")
        if not minimum <= float(value) <= maximum:
            raise ProfileValidationError(f"{key} must be between {minimum} and {maximum}")

    @staticmethod
    def _bounded_integer(
        parameters: dict[str, Any], key: str, minimum: int, maximum: int
    ) -> None:
        value = parameters.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ProfileValidationError(f"{key} must be an integer")
        if not minimum <= value <= maximum:
            raise ProfileValidationError(f"{key} must be between {minimum} and {maximum}")

    @classmethod
    def _optional_nonnegative(cls, parameters: dict[str, Any], key: str) -> None:
        value = parameters.get(key)
        if value is not None:
            cls._bounded_number(parameters, key, 0.0, float("inf"))

    @classmethod
    def _optional_bounded(
        cls, parameters: dict[str, Any], key: str, minimum: float, maximum: float
    ) -> None:
        value = parameters.get(key)
        if value is not None:
            cls._bounded_number(parameters, key, minimum, maximum)

    @staticmethod
    def _scope_value(value: str, field: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ProfileValidationError(f"{field} cannot be empty")
        return normalized

    @staticmethod
    def _reason(reason: str) -> str:
        normalized = reason.strip()
        if len(normalized) < 3:
            raise ProfileValidationError("reason must contain at least 3 characters")
        return normalized

    @staticmethod
    def _check_version(profile: DetectorProfile, expected_version: int | None) -> None:
        if expected_version is not None and profile.version != expected_version:
            raise ProfileConflictError(
                f"expected version {expected_version}, active version is {profile.version}"
            )
