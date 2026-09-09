"""Fail closed on missing, stale, or unhealthy TeaStore baseline traffic."""

import csv
import math
from pathlib import Path


def assess_baseline(path: Path, now: float, *, window_seconds=300,
                    minimum_requests=100, maximum_failure_ratio=0.01) -> dict:
    result = {"passed": False, "window_seconds": window_seconds,
              "minimum_requests": minimum_requests,
              "maximum_failure_ratio": maximum_failure_ratio, "errors": []}
    try:
        samples = []
        with path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                if row.get("Name") != "Aggregated":
                    continue
                sample = (float(row["Timestamp"]), int(row["Total Request Count"]),
                          int(row["Total Failure Count"]))
                if not math.isfinite(sample[0]) or not 0 <= sample[2] <= sample[1]:
                    raise ValueError("invalid sample")
                if samples and any(a < b for a, b in zip(sample, samples[-1])):
                    raise ValueError("non-monotonic samples")
                samples.append(sample)
        if not samples:
            raise ValueError("no aggregate samples")
    except (OSError, ValueError, KeyError, csv.Error, TypeError):
        result["errors"].append("baseline statistics missing or invalid")
        return result

    last = samples[-1]
    age = now - last[0]
    result["sample_age_seconds"] = round(age, 3)
    if not 0 <= age <= 15:
        result["errors"].append("baseline statistics are stale or future-dated")
    anchors = [sample for sample in samples if sample[0] <= last[0] - window_seconds]
    if not anchors:
        result["errors"].append(f"baseline requires at least {window_seconds} seconds of traffic")
    else:
        anchor = anchors[-1]
        requests, failures = last[1] - anchor[1], last[2] - anchor[2]
        ratio = failures / requests if requests else None
        result.update(requests=requests, failures=failures, failure_ratio=ratio)
        if requests < minimum_requests:
            result["errors"].append("insufficient requests in the baseline window")
        if ratio is not None and ratio > maximum_failure_ratio:
            result["errors"].append("recent baseline failure ratio exceeds threshold")
    total_ratio = last[2] / last[1] if last[1] else None
    result["total_failure_ratio"] = total_ratio
    if total_ratio is not None and total_ratio > maximum_failure_ratio:
        result["errors"].append("whole baseline failure ratio exceeds threshold")
    result["passed"] = not result["errors"]
    return result
