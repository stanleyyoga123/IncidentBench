import logging
import sys

LOGGER = logging.getLogger("analyzer")


def configure_logging() -> None:
    if LOGGER.handlers:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def progress(message: str) -> None:
    LOGGER.info(message)
