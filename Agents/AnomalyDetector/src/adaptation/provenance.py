from adaptation.profile import DetectorProfile
from schema.detection import Detection


def attach_profile(
    detection: Detection,
    profile: DetectorProfile,
) -> Detection:
    """Attach the exact runtime profile used to an anomaly decision."""
    if not detection.is_anomaly:
        return detection

    profile_detail = "\n".join(profile.provenance_lines())
    detail = f"{detection.detail}\n{profile_detail}" if detection.detail else profile_detail
    return detection.model_copy(
        update={
            "detail": detail,
            "profile_id": profile.id,
            "profile_version": profile.version,
            "profile_parameters": profile.parameters.copy(),
        },
        deep=True,
    )
