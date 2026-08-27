import hashlib
from pathlib import Path

import yaml

from ..command.command_runner import CommandRunner
from ..domain.placement import (
    APPLICATION_DEPLOYMENTS,
    HOSTNAME_LABEL,
    MIN_ALLOWED_CPU,
    NODE_CPU_CAPACITY,
    SERVICES_LABEL,
    SERVICES_LABEL_VALUE,
    PlacementProfile,
)


def extract_deployment_placement(deployment: dict) -> tuple[tuple[str, ...], tuple[dict, ...]]:
    name = deployment.get("metadata", {}).get("name", "<unknown>")
    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    selector = pod_spec.get("nodeSelector", {})
    if pod_spec.get("nodeName"):
        raise ValueError(f"Deployment {name} must not set nodeName")
    unexpected_selectors = set(selector) - {SERVICES_LABEL}
    if unexpected_selectors:
        raise ValueError(
            f"Deployment {name} has conflicting node selectors: "
            f"{', '.join(sorted(unexpected_selectors))}"
        )
    if selector.get(SERVICES_LABEL) != SERVICES_LABEL_VALUE:
        raise ValueError(
            f"Deployment {name} must retain nodeSelector "
            f"{SERVICES_LABEL}={SERVICES_LABEL_VALUE}"
        )
    required_affinity = (
        pod_spec.get("affinity", {})
        .get("nodeAffinity", {})
        .get("requiredDuringSchedulingIgnoredDuringExecution")
    )
    if required_affinity:
        raise ValueError(
            f"Deployment {name} must not contain required node affinity"
        )
    constraints = pod_spec.get("topologySpreadConstraints")
    if not isinstance(constraints, list) or len(constraints) != 1:
        raise ValueError(
            f"Deployment {name} must contain exactly one topology spread constraint"
        )
    constraint = constraints[0]
    expected_selector = {"matchLabels": {"app": name}}
    if (
        constraint.get("maxSkew") != 1
        or constraint.get("topologyKey") != HOSTNAME_LABEL
        or constraint.get("whenUnsatisfiable") != "ScheduleAnyway"
        or constraint.get("labelSelector") != expected_selector
    ):
        raise ValueError(
            f"Deployment {name} must softly spread app={name} across {HOSTNAME_LABEL}"
        )
    nodes = tuple(sorted(NODE_CPU_CAPACITY))
    tolerations = pod_spec.get("tolerations", [])
    if not isinstance(tolerations, list) or any(
        not isinstance(toleration, dict) for toleration in tolerations
    ):
        raise ValueError(f"Deployment {name} has invalid tolerations")
    return nodes, tuple(tolerations)


class PlacementRenderer:
    def __init__(self, runner: CommandRunner, repo_root: Path) -> None:
        self.runner = runner
        self.repo_root = Path(repo_root)

    def render(self, reference: str, source_dir: Path) -> PlacementProfile:
        result = self.runner.run(
            ["kubectl", "kustomize", str(source_dir)],
            cwd=self.repo_root,
        )
        if not result.succeeded:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise ValueError(f"failed to render placement {reference}: {detail}")
        documents = [
            document
            for document in yaml.safe_load_all(result.stdout)
            if document is not None
        ]
        deployments = {
            document.get("metadata", {}).get("name"): document
            for document in documents
            if document.get("apiVersion") == "apps/v1"
            and document.get("kind") == "Deployment"
        }
        expected = set(APPLICATION_DEPLOYMENTS)
        actual = set(deployments)
        if actual != expected:
            missing = sorted(expected - actual)
            extra = sorted(actual - expected)
            raise ValueError(
                f"placement {reference} must render exactly the application Deployments; "
                f"missing={missing}, extra={extra}"
            )
        allowed_nodes = {}
        tolerations = {}
        for name in APPLICATION_DEPLOYMENTS:
            nodes, workload_tolerations = extract_deployment_placement(deployments[name])
            unknown_nodes = sorted(set(nodes) - set(NODE_CPU_CAPACITY))
            if unknown_nodes:
                raise ValueError(
                    f"Deployment {name} references nodes with unknown CPU capacity: "
                    f"{', '.join(unknown_nodes)}"
                )
            allowed_cpu = sum(NODE_CPU_CAPACITY[node] for node in nodes)
            if allowed_cpu < MIN_ALLOWED_CPU:
                raise ValueError(
                    f"Deployment {name} allowed nodes provide {allowed_cpu} CPU; "
                    f"at least {MIN_ALLOWED_CPU} CPU is required"
                )
            allowed_nodes[name] = nodes
            tolerations[name] = workload_tolerations
        rendered_sha256 = hashlib.sha256(result.stdout.encode()).hexdigest()
        return PlacementProfile(
            reference=reference,
            source_dir=Path(source_dir),
            rendered_manifest=result.stdout,
            rendered_sha256=rendered_sha256,
            allowed_nodes=allowed_nodes,
            tolerations=tolerations,
        )
