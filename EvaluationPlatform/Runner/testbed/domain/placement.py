from dataclasses import dataclass
from pathlib import Path


APPLICATION_DEPLOYMENTS = (
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "paymentservice",
    "productcatalogservice",
    "recommendationservice",
    "redis-cart",
    "shippingservice",
)
HOSTNAME_LABEL = "kubernetes.io/hostname"
SERVICES_LABEL = "role"
SERVICES_LABEL_VALUE = "services"
MIN_ALLOWED_CPU = 6
NODE_CPU_CAPACITY = {
    "worker-node-1": 8,
    "worker-node-2": 4,
    "worker-node-3": 4,
    "worker-node-4": 2,
    "worker-node-5": 2,
    "worker-node-6": 4,
}


@dataclass(frozen=True)
class PlacementProfile:
    reference: str
    source_dir: Path
    rendered_manifest: str
    rendered_sha256: str
    allowed_nodes: dict[str, tuple[str, ...]]
    tolerations: dict[str, tuple[dict, ...]]

    @property
    def referenced_nodes(self) -> tuple[str, ...]:
        return tuple(
            sorted({node for nodes in self.allowed_nodes.values() for node in nodes})
        )

    @property
    def allowed_cpu_capacity(self) -> dict[str, int]:
        return {
            deployment: sum(NODE_CPU_CAPACITY[node] for node in nodes)
            for deployment, nodes in self.allowed_nodes.items()
        }

    def to_metadata(self, archived_source: Path, archived_render: Path) -> dict:
        return {
            "reference": self.reference,
            "source_dir": str(archived_source),
            "rendered_manifest": str(archived_render),
            "rendered_sha256": self.rendered_sha256,
            "allowed_nodes": {
                deployment: list(nodes)
                for deployment, nodes in sorted(self.allowed_nodes.items())
            },
            "allowed_cpu_capacity": self.allowed_cpu_capacity,
            "minimum_allowed_cpu": MIN_ALLOWED_CPU,
            "referenced_nodes": list(self.referenced_nodes),
            "normalization": None,
            "preflight": None,
            "verification": None,
            "observed_placement": None,
            "observed_placement_fingerprint": None,
        }
