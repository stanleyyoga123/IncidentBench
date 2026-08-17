import functools
import time
from typing import Callable, TypeVar, ParamSpec

from common.logger.console import get_logger

P = ParamSpec("P")
T = TypeVar("T")

LOGGER = get_logger("decorator")


def retry(
    retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
):
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            current_delay = delay

            for attempt in range(1, retries + 1):
                try:
                    return func(*args, **kwargs)

                except Exception as e:
                    if attempt == retries:
                        raise

                    LOGGER.info(
                        f"[Retry {attempt}/{retries}] " f"{func.__name__} failed: {e}"
                    )

                    time.sleep(current_delay)
                    current_delay *= backoff

            raise RuntimeError("Unexpected retry failure")

        return wrapper

    return decorator
