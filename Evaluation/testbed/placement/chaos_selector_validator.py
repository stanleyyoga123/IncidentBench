from collections.abc import Iterable

from ..domain.chaos_schedule import ChaosSchedule
from ..domain.placement import PlacementProfile


def validate_pod_chaos_selectors(
    profile: PlacementProfile,
    schedules: Iterable[ChaosSchedule],
    label_key: str = "app",
) -> None:
    for schedule in schedules:
        if schedule.child_type == "PhysicalMachineChaos":
            continue
        child = schedule.manifest["spec"][schedule.child_key]
        selector = child.get("selector", {})
        nodes = selector.get("nodes")
        if nodes is not None and (
            not isinstance(nodes, list)
            or not nodes
            or any(not isinstance(node, str) for node in nodes)
            or len(set(nodes)) != len(nodes)
        ):
            raise ValueError(
                f"pod Schedule {schedule.reference} must target one or more unique nodes"
            )
        expressions = [
            expression
            for expression in selector.get("expressionSelectors", [])
            if expression.get("key") == label_key and expression.get("operator") == "In"
        ]
        if len(expressions) != 1:
            raise ValueError(
                f"pod Schedule {schedule.reference} must contain exactly one {label_key} In selector"
            )
        actual_values = expressions[0].get("values")
        if not isinstance(actual_values, list) or any(
            not isinstance(value, str) for value in actual_values
        ):
            raise ValueError(
                f"pod Schedule {schedule.reference} has invalid app selector values"
            )
        actual = set(actual_values)
        if not actual or len(actual) != len(actual_values):
            raise ValueError(
                f"pod Schedule {schedule.reference} must have unique, non-empty app selector values"
            )

        # Omitting selector.nodes intentionally follows every selected service
        # replica, including replicas moved outside their initial placement by
        # remediation. This is the strongest service-scoped experiment.
        if nodes is None:
            if not all(
                deployment in profile.allowed_nodes for deployment in actual
            ):
                raise ValueError(
                    f"pod Schedule {schedule.reference} selects an unknown "
                    f"deployment for placement {profile.reference}; "
                    f"apps={sorted(actual)}"
                )
            continue

        selected_nodes = set(nodes)

        # A node-scoped schedule selects every service eligible for its one node.
        node_scoped_expected = {
            deployment
            for deployment, allowed_nodes in profile.allowed_nodes.items()
            if len(nodes) == 1 and nodes[0] in allowed_nodes
        }
        node_scoped = len(nodes) == 1 and actual == node_scoped_expected

        # A bounded service-scoped schedule may include healthy remediation
        # destinations outside the service's initial placement. Restrict those
        # node names to the known worker universe from the placement profile.
        known_nodes = {
            node
            for allowed_nodes in profile.allowed_nodes.values()
            for node in allowed_nodes
        }
        service_scoped = (
            all(deployment in profile.allowed_nodes for deployment in actual)
            and selected_nodes <= known_nodes
        )
        if not node_scoped and not service_scoped:
            raise ValueError(
                f"pod Schedule {schedule.reference} does not match placement "
                f"{profile.reference}; nodes={sorted(selected_nodes)}, "
                f"apps={sorted(actual)}"
            )
