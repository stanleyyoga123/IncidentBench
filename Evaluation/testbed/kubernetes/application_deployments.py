import hashlib
import json
import os
from pathlib import Path

from ..artifacts.artifact_layout import ArtifactLayout
from ..command.command_logger import CommandLogger
from ..command.command_runner import CommandRunner
from ..domain.placement import (
    APPLICATION_DEPLOYMENTS,
    HOSTNAME_LABEL,
    SERVICES_LABEL,
    SERVICES_LABEL_VALUE,
    PlacementProfile,
)
from ..placement.placement_renderer import extract_deployment_placement
from .kubectl_client import KubectlClient


class ApplicationDeploymentController:
    def __init__(
        self,
        runner: CommandRunner,
        kubectl: KubectlClient,
        artifacts: ArtifactLayout,
        command_logger: CommandLogger,
        repo_root: Path,
        *,
        infrastructure_root: Path | None = None,
    ) -> None:
        self.runner = runner
        self.kubectl = kubectl
        self.artifacts = artifacts
        self.command_logger = command_logger
        self.repo_root = repo_root
        self.infrastructure_root = infrastructure_root or Path(
            os.getenv(
                "INFRASTRUCTURE_ROOT",
                Path(repo_root).parent / "Infrastructure",
            )
        )

    def normalize_nodes(self, profile: PlacementProfile) -> dict:
        nodes = {}
        for node_name in profile.referenced_nodes:
            result = self.kubectl.run(["uncordon", node_name])
            nodes[node_name] = self.command_logger.write(
                result,
                self.artifacts.commands,
                f"placement-uncordon-{node_name}",
            )
        return {
            "action": "uncordon",
            "nodes": nodes,
            "returncode": next(
                (
                    result["returncode"]
                    for result in nodes.values()
                    if result["returncode"] != 0
                ),
                0,
            ),
        }

    def preflight(self, profile: PlacementProfile) -> dict:
        result = self.kubectl.run(["get", "nodes", "-o", "json"])
        logged = self.command_logger.write(
            result,
            self.artifacts.commands,
            "placement-node-preflight",
        )
        logged.update({"errors": [], "nodes": {}})
        if not result.succeeded:
            return logged
        try:
            items = json.loads(result.stdout).get("items", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            logged["returncode"] = 2
            logged["errors"] = [f"invalid node response: {exc}"]
            return logged
        by_name = {
            item.get("metadata", {}).get("name"): item
            for item in items
            if item.get("metadata", {}).get("name")
        }
        for node_name in profile.referenced_nodes:
            item = by_name.get(node_name)
            if item is None:
                logged["errors"].append(f"node does not exist: {node_name}")
                continue
            metadata = item.get("metadata", {})
            spec = item.get("spec", {})
            labels = metadata.get("labels", {})
            conditions = item.get("status", {}).get("conditions", [])
            ready = any(
                condition.get("type") == "Ready"
                and condition.get("status") == "True"
                for condition in conditions
            )
            schedulable = not spec.get("unschedulable", False)
            services_label = labels.get(SERVICES_LABEL)
            hostname = labels.get(HOSTNAME_LABEL)
            blocking_taints = []
            for taint in spec.get("taints", []):
                if taint.get("effect") not in {"NoSchedule", "NoExecute"}:
                    continue
                affected = [
                    deployment
                    for deployment, nodes in profile.allowed_nodes.items()
                    if node_name in nodes
                    and not any(
                        self._tolerates(taint, toleration)
                        for toleration in profile.tolerations[deployment]
                    )
                ]
                if affected:
                    blocking_taints.append(
                        {
                            "key": taint.get("key"),
                            "value": taint.get("value"),
                            "effect": taint.get("effect"),
                            "deployments": affected,
                        }
                    )
            logged["nodes"][node_name] = {
                "ready": ready,
                "schedulable": schedulable,
                "services_label": services_label,
                "hostname": hostname,
                "blocking_taints": blocking_taints,
            }
            if not ready:
                logged["errors"].append(f"node is not Ready: {node_name}")
            if not schedulable:
                logged["errors"].append(f"node is unschedulable: {node_name}")
            if services_label != SERVICES_LABEL_VALUE:
                logged["errors"].append(
                    f"node {node_name} must have {SERVICES_LABEL}={SERVICES_LABEL_VALUE}"
                )
            if hostname != node_name:
                logged["errors"].append(
                    f"node {node_name} must have {HOSTNAME_LABEL}={node_name}"
                )
            if blocking_taints:
                logged["errors"].append(
                    f"node has untolerated blocking taints: {node_name}"
                )
        if logged["errors"]:
            logged["returncode"] = 2
        return logged

    def verify_placement(self, profile: PlacementProfile, namespace: str) -> dict:
        deployment_result = self.kubectl.run(
            [
                "get",
                "deployments",
                *APPLICATION_DEPLOYMENTS,
                "-n",
                namespace,
                "-o",
                "json",
            ]
        )
        pod_result = self.kubectl.run(
            ["get", "pods", "-n", namespace, "-o", "json"]
        )
        commands = {
            "deployments": self.command_logger.write(
                deployment_result,
                self.artifacts.commands,
                "placement-live-deployments",
            ),
            "pods": self.command_logger.write(
                pod_result,
                self.artifacts.commands,
                "placement-live-pods",
            ),
        }
        verification = {
            "returncode": next(
                (
                    result.returncode
                    for result in (deployment_result, pod_result)
                    if not result.succeeded
                ),
                0,
            ),
            "commands": commands,
            "errors": [],
            "observed_placement": None,
            "observed_placement_fingerprint": None,
        }
        if verification["returncode"] != 0:
            return verification
        try:
            deployments = json.loads(deployment_result.stdout).get("items", [])
            pods = json.loads(pod_result.stdout).get("items", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            verification["returncode"] = 2
            verification["errors"] = [f"invalid placement response: {exc}"]
            return verification
        live_deployments = {
            item.get("metadata", {}).get("name"): item
            for item in deployments
            if item.get("metadata", {}).get("name")
        }
        if set(live_deployments) != set(APPLICATION_DEPLOYMENTS):
            verification["errors"].append(
                "live Deployment set does not match the placement profile"
            )
        for name in APPLICATION_DEPLOYMENTS:
            deployment = live_deployments.get(name)
            if deployment is None:
                continue
            try:
                nodes, _ = extract_deployment_placement(deployment)
            except ValueError as exc:
                verification["errors"].append(str(exc))
                continue
            if nodes != profile.allowed_nodes[name]:
                verification["errors"].append(
                    f"Deployment {name} placement differs from archived profile"
                )
        counts = {name: {} for name in APPLICATION_DEPLOYMENTS}
        pod_counts = {name: 0 for name in APPLICATION_DEPLOYMENTS}
        for pod in pods:
            metadata = pod.get("metadata", {})
            app = metadata.get("labels", {}).get("app")
            if app not in counts:
                continue
            pod_counts[app] += 1
            pod_name = metadata.get("name", "<unknown>")
            pod_spec = pod.get("spec", {})
            status = pod.get("status", {})
            node = pod_spec.get("nodeName")
            container_statuses = status.get("containerStatuses", [])
            ready = (
                metadata.get("deletionTimestamp") is None
                and status.get("phase") == "Running"
                and bool(container_statuses)
                and all(value.get("ready") is True for value in container_statuses)
            )
            if not ready:
                verification["errors"].append(f"application pod is not Ready: {pod_name}")
            if node not in profile.allowed_nodes[app]:
                verification["errors"].append(
                    f"pod {pod_name} is on disallowed node {node!r}"
                )
                continue
            counts[app][node] = counts[app].get(node, 0) + 1
        for name, count in pod_counts.items():
            if count == 0:
                verification["errors"].append(
                    f"no application pods found for Deployment {name}"
                )
        observed = {
            name: dict(sorted(node_counts.items()))
            for name, node_counts in sorted(counts.items())
        }
        canonical = json.dumps(observed, sort_keys=True, separators=(",", ":"))
        verification["observed_placement"] = observed
        verification["observed_placement_fingerprint"] = hashlib.sha256(
            canonical.encode()
        ).hexdigest()
        if verification["errors"]:
            verification["returncode"] = 2
        return verification

    @staticmethod
    def _tolerates(taint: dict, toleration: dict) -> bool:
        effect = toleration.get("effect")
        if effect and effect != taint.get("effect"):
            return False
        operator = toleration.get("operator", "Equal")
        if operator == "Exists":
            return not toleration.get("key") or toleration.get("key") == taint.get(
                "key"
            )
        return (
            operator == "Equal"
            and toleration.get("key") == taint.get("key")
            and toleration.get("value", "") == taint.get("value", "")
        )

    def wait_for_rollouts(self, namespace: str) -> dict:
        destination = self.artifacts.commands
        list_result = self.kubectl.run(
            ["get", "deployments", "-n", namespace, "-o", "name"]
        )
        stdout_parts = [f"$ {' '.join(list_result.command)}\n{list_result.stdout}"]
        stderr_parts = [f"$ {' '.join(list_result.command)}\n{list_result.stderr}"]
        returncode = list_result.returncode
        failed_command = list(list_result.command) if not list_result.succeeded else None
        if list_result.succeeded:
            for deployment in filter(None, map(str.strip, list_result.stdout.splitlines())):
                result = self.kubectl.rollout_status(deployment, namespace)
                stdout_parts.append(f"$ {' '.join(result.command)}\n{result.stdout}")
                stderr_parts.append(f"$ {' '.join(result.command)}\n{result.stderr}")
                if not result.succeeded:
                    returncode = result.returncode
                    failed_command = list(result.command)
                    break
        destination.mkdir(parents=True, exist_ok=True)
        stdout_file = destination / "rollout-status.stdout"
        stderr_file = destination / "rollout-status.stderr"
        stdout_file.write_text("\n".join(stdout_parts))
        stderr_file.write_text("\n".join(stderr_parts))
        return {
            "command": [
                "kubectl",
                "rollout",
                "status",
                "<deployments-from-namespace>",
                "-n",
                namespace,
                "--timeout=10m",
            ],
            "failed_command": failed_command,
            "returncode": returncode,
            "stdout_file": str(stdout_file),
            "stderr_file": str(stderr_file),
        }
