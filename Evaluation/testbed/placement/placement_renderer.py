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


def extract_deployment_placement(
    deployment: dict,
    settings=None,
) -> tuple[tuple[str, ...], tuple[dict, ...]]:
    name = deployment.get("metadata", {}).get("name", "<unknown>")
    pod_spec = deployment.get("spec", {}).get("template", {}).get("spec", {})
    selector = pod_spec.get("nodeSelector", {})
    selector_key = settings.node_selector_key if settings else SERVICES_LABEL
    selector_value = settings.node_selector_value if settings else SERVICES_LABEL_VALUE
    label_key = settings.label_key if settings else "app"
    if pod_spec.get("nodeName"):
        raise ValueError(f"Deployment {name} must not set nodeName")
    unexpected_selectors = set(selector) - {selector_key}
    if unexpected_selectors:
        raise ValueError(
            f"Deployment {name} has conflicting node selectors: "
            f"{', '.join(sorted(unexpected_selectors))}"
        )
    if selector.get(selector_key) != selector_value:
        raise ValueError(
            f"Deployment {name} must retain nodeSelector "
            f"{selector_key}={selector_value}"
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
    expected_selector = {"matchLabels": {label_key: name}}
    if (
        constraint.get("maxSkew") != 1
        or constraint.get("topologyKey") != HOSTNAME_LABEL
        or constraint.get("whenUnsatisfiable") != "ScheduleAnyway"
        or constraint.get("labelSelector") != expected_selector
    ):
        raise ValueError(
            f"Deployment {name} must softly spread {label_key}={name} across {HOSTNAME_LABEL}"
        )
    nodes = tuple(sorted(NODE_CPU_CAPACITY))
    tolerations = pod_spec.get("tolerations", [])
    if not isinstance(tolerations, list) or any(
        not isinstance(toleration, dict) for toleration in tolerations
    ):
        raise ValueError(f"Deployment {name} has invalid tolerations")
    return nodes, tuple(tolerations)


class PlacementRenderer:
    def __init__(
        self,
        runner: CommandRunner,
        repo_root: Path,
        *,
        application_profile=None,
    ) -> None:
        self.runner = runner
        self.repo_root = Path(repo_root)
        self.application_profile = application_profile

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
        expected_workloads = (
            self.application_profile.placement.workload_names
            if self.application_profile is not None
            else APPLICATION_DEPLOYMENTS
        )
        expected = set(expected_workloads)
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
        for name in expected_workloads:
            nodes, workload_tolerations = extract_deployment_placement(
                deployments[name],
                self.application_profile.placement
                if self.application_profile is not None
                else None,
            )
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

    def render_live(
        self,
        reference: str,
        source_dir: Path,
        namespace: str,
    ) -> PlacementProfile:
        if self.application_profile is None:
            raise ValueError("live placement rendering requires an application profile")
        result = self.runner.run(
            ["kubectl", "get", "deployments", "-n", namespace, "-o", "json"],
            cwd=self.repo_root,
        )
        if not result.succeeded:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise ValueError(f"failed to read live placement {reference}: {detail}")
        import json

        try:
            items = json.loads(result.stdout).get("items", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            raise ValueError(f"invalid live placement response: {exc}") from exc
        deployments = {
            item.get("metadata", {}).get("name"): item
            for item in items
            if self.application_profile.placement.selects(
                item.get("metadata", {}).get("name", "")
            )
        }
        if not deployments:
            raise ValueError(
                f"live placement {reference} contains no selected application Deployments"
            )
        policy = yaml.safe_load((Path(source_dir) / "profile.yaml").read_text())
        nodes = tuple(policy.get("allowed_nodes", ()))
        if not nodes or any(node not in NODE_CPU_CAPACITY for node in nodes):
            raise ValueError(f"placement {reference} has invalid allowed_nodes")
        tolerations = {}
        for name, deployment in sorted(deployments.items()):
            _, workload_tolerations = extract_deployment_placement(
                deployment,
                self.application_profile.placement,
            )
            tolerations[name] = workload_tolerations
        rendered = yaml.safe_dump_all(
            [deployments[name] for name in sorted(deployments)],
            sort_keys=True,
        )
        return PlacementProfile(
            reference=reference,
            source_dir=Path(source_dir),
            rendered_manifest=rendered,
            rendered_sha256=hashlib.sha256(rendered.encode()).hexdigest(),
            allowed_nodes={name: nodes for name in sorted(deployments)},
            tolerations=tolerations,
        )
