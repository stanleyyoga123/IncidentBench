from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from ..command.command_runner import CommandRunner
from ..scenarios.scenario_loader import ScenarioLoader
from .application_catalog import ApplicationCatalog
from .installers import ApplicationInstaller


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Reset and install a scenario application")
    parser.add_argument("--scenario", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    workspace_root = repo_root.parents[1]
    catalog = ApplicationCatalog(repo_root / "resources/applications", workspace_root)
    application = ScenarioLoader.application_reference(repo_root, args.scenario)
    profile = catalog.resolve(application)
    namespace_override = os.getenv("NAMESPACE")
    if namespace_override and namespace_override != profile.namespace:
        raise ValueError(
            f"scenario application {profile.id} requires namespace "
            f"{profile.namespace}; got {namespace_override}"
        )
    scenario_path = args.scenario if args.scenario.is_absolute() else repo_root / args.scenario
    scenario = json.loads(scenario_path.resolve().read_text())
    placement = scenario.get("placement")
    if not isinstance(placement, str) or not placement:
        raise ValueError("scenario placement must be a non-empty string")
    installer = ApplicationInstaller(CommandRunner(), repo_root, workspace_root)
    installer.validate(profile, placement)
    sibling_namespaces = catalog.other_namespaces(profile.id)

    result = installer.install(
        profile,
        placement,
        clear_namespaces=sibling_namespaces,
    )
    output_dir = os.getenv("OUTPUT_DIR")
    if output_dir:
        destination = Path(output_dir)
        if not destination.is_absolute():
            destination = repo_root / destination
        destination.mkdir(parents=True, exist_ok=True)
        rendered_path = destination / "application-rendered.yaml"
        rendered_path.write_text(result.rendered_manifest)
        (destination / "application-install.json").write_text(
            json.dumps(
                {
                    "application": profile.to_metadata(workspace_root),
                    "placement": placement,
                    "installer": result.installer,
                    "source": result.source,
                    "rendered_manifest": str(rendered_path),
                    "rendered_sha256": result.rendered_sha256,
                    "commands": list(result.commands),
                },
                indent=2,
                sort_keys=True,
            )
        )
    print(
        f"installed application={profile.id} installer={result.installer} "
        f"namespace={profile.namespace} source={result.source}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FileNotFoundError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"application prerun failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
