class SnapshotCommandCatalog:
    def __init__(self, namespace: str) -> None:
        self.namespace = namespace

    def commands(self) -> list[tuple[str, list[str]]]:
        ns = self.namespace
        return [
            ("pods-wide", ["kubectl", "get", "pods", "-n", ns, "-o", "wide"]),
            ("pods-json", ["kubectl", "get", "pods", "-n", ns, "-o", "json"]),
            ("deployments", ["kubectl", "get", "deployments", "-n", ns, "-o", "wide"]),
            ("deployments-json", ["kubectl", "get", "deployments", "-n", ns, "-o", "json"]),
            ("hpa", ["kubectl", "get", "hpa", "-n", ns, "-o", "wide"]),
            ("services", ["kubectl", "get", "services", "-n", ns, "-o", "wide"]),
            ("events", ["kubectl", "get", "events", "-n", ns, "--sort-by=.lastTimestamp"]),
            ("nodes", ["kubectl", "get", "nodes", "-o", "wide"]),
            ("top-pods", ["kubectl", "top", "pods", "-n", ns]),
            ("top-nodes", ["kubectl", "top", "nodes"]),
            (
                "pod-restarts",
                [
                    "kubectl", "get", "pods", "-n", ns, "-o",
                    "custom-columns=POD:.metadata.name,PHASE:.status.phase,RESTARTS:.status.containerStatuses[*].restartCount",
                ],
            ),
            (
                "resource-requests-limits",
                [
                    "kubectl", "get", "pods", "-n", ns, "-o",
                    "custom-columns=POD:.metadata.name,CONTAINER:.spec.containers[*].name,CPU_REQ:.spec.containers[*].resources.requests.cpu,MEM_REQ:.spec.containers[*].resources.requests.memory,CPU_LIMIT:.spec.containers[*].resources.limits.cpu,MEM_LIMIT:.spec.containers[*].resources.limits.memory",
                ],
            ),
        ]
