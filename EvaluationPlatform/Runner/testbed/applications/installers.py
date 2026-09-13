from __future__ import annotations

import json
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from ..command.command_runner import CommandRunner
from ..domain import CommandResult
from .application_profile import ApplicationProfile


@dataclass(frozen=True)
class InstallationResult:
    commands: tuple[dict, ...]
    source: str
    installer: str
    rendered_manifest: str
    rendered_sha256: str


class ApplicationInstaller:
    def __init__(
        self,
        runner: CommandRunner,
        repo_root: Path,
        workspace_root: Path,
    ) -> None:
        self.runner = runner
        self.repo_root = Path(repo_root).resolve()
        self.workspace_root = Path(workspace_root).resolve()

    def validate(self, profile: ApplicationProfile, placement: str) -> Path:
        source = self._installation_source(profile, placement)
        if not source.is_dir():
            environment = profile.installer.source_environment
            raise FileNotFoundError(
                f"{profile.id} source is missing: {source}; clone the application "
                f"or set {environment}"
            )
        binaries = {
            "kustomize": ("kubectl",),
            "helm": ("helm",),
            "script": ("bash", "helm", "kubectl"),
        }[profile.installer.type]
        for binary in binaries:
            if shutil.which(binary) is None:
                raise FileNotFoundError(
                    f"required installer command is unavailable: {binary}"
                )
        missing = [
            relative
            for relative in profile.installer.required_files
            if not (profile.installer.install_source(self.workspace_root) / relative).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"{profile.id} source is incomplete; missing: {', '.join(missing)}"
            )
        inspected = "\n".join(
            (profile.installer.install_source(self.workspace_root) / relative).read_text(
                errors="replace"
            )
            for relative in profile.installer.required_files
        )
        absent = [
            text for text in profile.installer.required_source_text if text not in inspected
        ]
        forbidden = [
            text for text in profile.installer.forbidden_source_text if text in inspected
        ]
        if absent or forbidden:
            details = []
            if absent:
                details.append(f"required safeguards absent: {', '.join(absent)}")
            if forbidden:
                details.append(f"unsafe behavior present: {', '.join(forbidden)}")
            raise ValueError(
                f"{profile.id} source is not evaluation-safe ({'; '.join(details)})"
            )
        self._prerequisite_manifests(profile)
        missing_values = [
            value for value in profile.installer.values if not (source / value).is_file()
        ]
        if missing_values:
            raise FileNotFoundError(
                f"{profile.id} Helm values are missing: {', '.join(missing_values)}"
            )
        if profile.installer.type == "script":
            driver = profile.source_path.parent / str(profile.installer.script)
            if not driver.is_file():
                raise FileNotFoundError(f"application installer script is missing: {driver}")
        if profile.placement.mode == "live":
            policy = profile.placement_root(self.workspace_root) / placement / "profile.yaml"
            if not policy.is_file():
                raise FileNotFoundError(f"placement policy is missing: {policy}")
        return source

    def install(
        self,
        profile: ApplicationProfile,
        placement: str,
        *,
        clear_namespaces: tuple[str, ...] = (),
    ) -> InstallationResult:
        source = self.validate(profile, placement)
        rendered = self._render(profile, source)
        commands = [self._command_summary(rendered)]
        for command in self._namespace_commands(profile, extra_namespaces=clear_namespaces):
            commands.append(self._command_summary(self._required(command)))
        for manifest in self._prerequisite_manifests(profile):
            commands.append(
                self._command_summary(
                    self._required(["kubectl", "apply", "-f", str(manifest)])
                )
            )
        if profile.installer.type == "kustomize":
            command = [
                "kubectl",
                "apply",
                "-k",
                str(source),
                "--namespace",
                profile.namespace,
            ]
        elif profile.installer.type == "helm":
            command = [
                "helm",
                "upgrade",
                "--install",
                profile.installer.release,
                str(source),
                "--namespace",
                profile.namespace,
                "--create-namespace",
                "--wait",
                "--wait-for-jobs",
                "--timeout",
                profile.installer.timeout,
            ]
            for values_file in profile.installer.values:
                command.extend(["--values", str(source / values_file)])
        else:
            command = [
                "bash",
                str(profile.source_path.parent / str(profile.installer.script)),
                str(source),
                profile.namespace,
            ]
        commands.append(
            self._command_summary(
                self._required(
                    command,
                    timeout=self._command_timeout_seconds(profile),
                    cwd=source if profile.installer.type == "script" else None,
                )
            )
        )
        if profile.placement.mode == "live":
            commands.extend(self._apply_live_placement(profile, placement))
        return InstallationResult(
            commands=tuple(commands),
            source=str(source),
            installer=profile.installer.type,
            rendered_manifest=rendered.stdout,
            rendered_sha256=hashlib.sha256(rendered.stdout.encode()).hexdigest(),
        )

    def _render(self, profile: ApplicationProfile, source: Path):
        if profile.installer.type == "kustomize":
            command = ["kubectl", "kustomize", str(source)]
        elif profile.installer.type == "helm":
            command = [
                "helm",
                "template",
                profile.installer.release,
                str(source),
                "--namespace",
                profile.namespace,
            ]
            for values_file in profile.installer.values:
                command.extend(["--values", str(source / values_file)])
            return self._required(command, timeout=300)
        else:
            driver = profile.source_path.parent / str(profile.installer.script)
            inputs = [driver] + [
                profile.installer.install_source(self.workspace_root) / relative
                for relative in profile.installer.required_files
            ]
            snapshot = [
                {
                    "path": (
                        str(path.relative_to(profile.source_path.parent))
                        if path == driver
                        else str(path.relative_to(
                            profile.installer.install_source(self.workspace_root)
                        ))
                    ),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
                for path in inputs
            ]
            return CommandResult(
                ("application-source-snapshot", str(source)),
                0,
                json.dumps(snapshot, sort_keys=True, indent=2),
                "",
            )
        return self._required(command, timeout=300)

    @staticmethod
    def _incluster_kubeconfig() -> Path | None:
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        token_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/token")
        ca_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        if not host or not token_path.is_file() or not ca_path.is_file():
            return None
        kubeconfig = Path("/tmp/evaluation-incluster.kubeconfig")
        if not kubeconfig.is_file():
            namespace_path = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
            namespace = (
                namespace_path.read_text().strip()
                if namespace_path.is_file()
                else "default"
            )
            kubeconfig.write_text(
                "apiVersion: v1\n"
                "kind: Config\n"
                "clusters:\n"
                "- cluster:\n"
                f"    certificate-authority: {ca_path}\n"
                f"    server: https://{host}:{port}\n"
                "  name: in-cluster\n"
                "contexts:\n"
                "- context:\n"
                "    cluster: in-cluster\n"
                f"    namespace: {namespace}\n"
                "    user: in-cluster\n"
                "  name: in-cluster\n"
                "current-context: in-cluster\n"
                "users:\n"
                "- name: in-cluster\n"
                "  user:\n"
                f"    token: {token_path.read_text().strip()}\n"
            )
            kubeconfig.chmod(0o600)
        return kubeconfig

    def _kubectl(self, *args: str, impersonate: bool = False) -> list[str]:
        command = ["kubectl", *args]
        if impersonate:
            kubeconfig = self._incluster_kubeconfig()
            if kubeconfig is not None:
                command = ["kubectl", "--kubeconfig", str(kubeconfig), *args]
        return command

    @staticmethod
    def _command_timeout_seconds(profile: ApplicationProfile) -> int:
        raw = profile.installer.timeout.strip()
        if raw.endswith("m") and raw[:-1].isdigit():
            return int(raw[:-1]) * 60 + 60
        if raw.endswith("s") and raw[:-1].isdigit():
            return int(raw[:-1]) + 60
        raise ValueError(f"unsupported installer.timeout: {profile.installer.timeout}")

    def _installation_source(
        self, profile: ApplicationProfile, placement: str
    ) -> Path:
        base = profile.installer.install_source(self.workspace_root)
        if profile.installer.type == "kustomize":
            return (base / "overlays" / placement).resolve()
        return base

    def _namespace_commands(
        self,
        profile: ApplicationProfile,
        extra_namespaces: tuple[str, ...] = (),
    ) -> tuple[list[str], ...]:
        deletes: list[list[str]] = []
        seen: set[str] = set()
        for namespace in (*extra_namespaces, profile.namespace):
            if not namespace or namespace in seen:
                continue
            seen.add(namespace)
            deletes.append(
                [
                    "kubectl",
                    "delete",
                    "namespace",
                    namespace,
                    "--ignore-not-found=true",
                    "--wait=true",
                    "--timeout=10m",
                ]
            )
        return (
            *deletes,
            ["kubectl", "create", "namespace", profile.namespace],
            [
                "kubectl",
                "label",
                "namespace",
                profile.namespace,
                "istio-injection=enabled",
                "--overwrite",
            ],
        )

    def _prerequisite_manifests(
        self, profile: ApplicationProfile
    ) -> tuple[Path, ...]:
        manifests = tuple(
            profile.installer.source_root(self.workspace_root) / relative
            for relative in profile.installer.prerequisite_manifests
        )
        missing = [str(path) for path in manifests if not path.is_file()]
        if missing:
            raise FileNotFoundError(
                f"required application manifests are missing: {', '.join(missing)}"
            )
        return manifests

    def _apply_live_placement(
        self, profile: ApplicationProfile, reference: str
    ) -> list[dict]:
        policy_path = profile.placement_root(self.workspace_root) / reference / "profile.yaml"
        if not policy_path.is_file():
            raise FileNotFoundError(f"placement policy is missing: {policy_path}")
        policy = yaml.safe_load(policy_path.read_text())
        topology_key = policy.get("topology_key", "kubernetes.io/hostname")
        max_skew = policy.get("max_skew", 1)
        when_unsatisfiable = policy.get("when_unsatisfiable", "ScheduleAnyway")
        listed = self._required(
            [
                "kubectl",
                "get",
                "deployments",
                "-n",
                profile.namespace,
                "-o",
                "json",
            ]
        )
        documents = json.loads(listed.stdout).get("items", [])
        names = sorted(
            item.get("metadata", {}).get("name")
            for item in documents
            if profile.placement.selects(item.get("metadata", {}).get("name", ""))
        )
        if not names:
            raise ValueError(f"{profile.id} installation exposed no selected Deployments")
        results = [self._command_summary(listed)]
        for name in names:
            patch = {
                "spec": {
                    "template": {
                        "spec": {
                            "nodeSelector": {
                                profile.placement.node_selector_key:
                                    profile.placement.node_selector_value
                            },
                            "topologySpreadConstraints": [
                                {
                                    "maxSkew": max_skew,
                                    "topologyKey": topology_key,
                                    "whenUnsatisfiable": when_unsatisfiable,
                                    "labelSelector": {
                                        "matchLabels": {profile.placement.label_key: name}
                                    },
                                }
                            ],
                        }
                    }
                }
            }
            result = self._required(
                [
                    "kubectl",
                    "patch",
                    "deployment",
                    name,
                    "-n",
                    profile.namespace,
                    "--type=merge",
                    "-p",
                    json.dumps(patch, separators=(",", ":")),
                ]
            )
            results.append(self._command_summary(result))
        return results

    @staticmethod
    def _command_summary(result) -> dict:
        return {
            "command": list(result.command),
            "returncode": result.returncode,
            "timed_out": result.timed_out,
        }

    def _required(
        self,
        command: list[str],
        timeout: int | None = None,
        cwd: Path | None = None,
    ):
        result = self.runner.run(command, cwd=cwd or self.repo_root, timeout=timeout)
        if not result.succeeded:
            detail = result.stderr.strip() or result.stdout.strip() or "unknown error"
            raise RuntimeError(f"application command failed: {' '.join(command)}: {detail}")
        return result
