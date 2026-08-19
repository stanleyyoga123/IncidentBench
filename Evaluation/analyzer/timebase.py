from testbed.reporting.chaos_window import ChaosWindow, ChaosWindowReader


def chaos_t0(metadata: dict) -> float | None:
    windows = ChaosWindowReader().windows(metadata)
    if not windows:
        return None
    return min(window.start for window in windows)


def first_chaos_window(metadata: dict) -> ChaosWindow | None:
    windows = ChaosWindowReader().windows(metadata)
    if not windows:
        return None
    return min(windows, key=lambda window: window.start)


def elapsed_minutes(timestamp: float, origin: float) -> float:
    return (timestamp - origin) / 60.0
