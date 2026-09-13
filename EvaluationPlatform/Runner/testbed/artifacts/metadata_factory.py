from datetime import datetime, timezone


class MetadataFactory:
    @staticmethod
    def create(
        config,
        scenario,
        args,
        schedules,
        archived_schedules,
        placement,
        archived_placement_source,
        archived_placement_render,
    ) -> dict:
        argument_values = {k: str(v) if hasattr(v, "__fspath__") else v
                           for k, v in vars(args).items() if k != "lifecycle"}
        for key in argument_values:
            if any(word in key.lower() for word in ("token", "secret", "password", "dsn")):
                argument_values[key] = "<redacted>"
        scenario_duration = sum(step.duration for step in scenario.steps)
        total_duration = (
            config.baseline_seconds + config.grace_period + scenario_duration
        )
        return {
            "schema_version": 2,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "repo_root": str(config.repo_root),
            "args": argument_values,
            "namespace": config.namespace,
            "application": getattr(config, "application", "online-boutique"),
            "agent_namespace": config.agent_namespace,
            "host": config.host,
            "baseline_seconds": config.baseline_seconds,
            "grace_period": config.grace_period,
            "agents_enabled": config.agents_enabled,
            "scenario": scenario.to_dict(),
            "placement": placement.to_metadata(
                archived_placement_source,
                archived_placement_render,
            ),
            "chaos_definitions": [
                schedule.to_metadata(archived_schedules[schedule.reference])
                for schedule in schedules
            ],
            "loadgenerator": {
                "scenario": config.loadgenerator,
                "startup_delay_seconds": getattr(config, "startup_delay_seconds", 0),
                "command": None,
                "returncode": None,
                "duration_seconds": total_duration,
            },
            "commands": {},
            "snapshots": [],
            "timeseries": [],
            "chaos_steps": [],
            "metrics": None,
            "phases": [],
            "status": "running",
        }
