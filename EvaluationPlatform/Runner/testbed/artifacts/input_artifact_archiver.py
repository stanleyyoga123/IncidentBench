import hashlib
import shutil
from pathlib import Path

from ..domain.chaos_schedule import ChaosSchedule
from ..domain.scenario import Scenario
from ..domain.placement import PlacementProfile
from .artifact_layout import ArtifactLayout


class InputArtifactArchiver:
    def __init__(self, layout: ArtifactLayout) -> None:
        self.layout = layout

    def archive(
        self,
        scenario: Scenario,
        schedules: tuple[ChaosSchedule, ...],
        placement: PlacementProfile,
    ) -> dict[str, Path]:
        self.layout.inputs.mkdir(parents=True, exist_ok=True)
        self.layout.archived_chaos.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(scenario.path, self.layout.archived_scenario)
        archived = {}
        for schedule in schedules:
            destination = self.layout.archived_chaos / f"{schedule.reference}.yaml"
            raw = schedule.source_path.read_bytes()
            if b"${node_ip:" in raw:
                import yaml
                destination.write_text(yaml.safe_dump(schedule.manifest, sort_keys=False))
            else:
                shutil.copyfile(schedule.source_path, destination)
            archived[schedule.reference] = destination
        shutil.copytree(
            placement.source_dir,
            self.layout.archived_placement_source,
        )
        self.layout.archived_placement_render.write_text(
            placement.rendered_manifest
        )
        archived_hash = hashlib.sha256(
            self.layout.archived_placement_render.read_bytes()
        ).hexdigest()
        if archived_hash != placement.rendered_sha256:
            raise ValueError("archived placement render hash does not match source")
        return archived
