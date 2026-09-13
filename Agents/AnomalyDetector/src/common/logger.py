import logging

logging.getLogger("httpx").setLevel(logging.WARNING)
import sys


def get_logger(name: str, level: str = logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
    )

    return logging.getLogger(name)
