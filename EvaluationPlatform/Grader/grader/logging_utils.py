from __future__ import annotations

import logging
from pathlib import Path


LOGGER_NAME = "grader"
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(output_path: Path, *, verbose: bool = False) -> Path:
    """Configure a fresh verbose file log and a concise/verbose console log."""
    output = Path(output_path)
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "grader.log"
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    for handler in list(logger.handlers):
        if getattr(handler, "_grader_owned", False):
            logger.removeHandler(handler)
            handler.close()

    formatter = logging.Formatter(LOG_FORMAT)
    file_handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    file_handler._grader_owned = True  # type: ignore[attr-defined]
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler._grader_owned = True  # type: ignore[attr-defined]
    logger.addHandler(console_handler)
    logger.debug("logging configured file=%s verbose_console=%s", log_path, verbose)
    return log_path


def close_logging() -> None:
    """Flush and close handlers owned by the grader."""
    logger = logging.getLogger(LOGGER_NAME)
    for handler in list(logger.handlers):
        if getattr(handler, "_grader_owned", False):
            logger.removeHandler(handler)
            handler.close()
