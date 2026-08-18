from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExperimentConfig:
    repo_root: Path
    loadgenerator: str
    scenario_path: Path
    host: str
    baseline_seconds: int
    output_dir: Path
    namespace: str
    agent_namespace: str
    grace_period: int
    prometheus_url: str | None
    skip_agents: bool
    port_forward: bool
    port_forward_port: int

    @property
    def agents_enabled(self) -> bool:
        return not self.skip_agents

    @classmethod
    def from_namespace(cls, args, repo_root: Path, output_dir: Path) -> "ExperimentConfig":
        baseline_seconds = (
            int(args.baseline_minutes * 60)
            if args.baseline_minutes
            else args.duration
        )
        return cls(
            repo_root=repo_root,
            loadgenerator=args.loadgenerator,
            scenario_path=args.scenario,
            host=args.host,
            baseline_seconds=baseline_seconds,
            output_dir=output_dir,
            namespace=args.namespace,
            agent_namespace=args.agent_namespace,
            grace_period=0 if args.skip_agents else args.grace_period,
            prometheus_url=args.prometheus_url,
            skip_agents=args.skip_agents,
            port_forward=args.port_forward,
            port_forward_port=args.port_forward_port,
        )
