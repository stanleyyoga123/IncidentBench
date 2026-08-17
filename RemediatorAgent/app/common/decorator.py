import functools
import inspect
import time
from typing import Awaitable, Callable, TypeVar, ParamSpec, cast

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


def log_runtime():
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
                start = time.perf_counter()
                try:
                    return await cast(Callable[P, Awaitable[T]], func)(*args, **kwargs)
                finally:
                    stop = time.perf_counter()
                    LOGGER.info(
                        f"Runtime {func.__qualname__}: {stop - start:.6f} seconds"
                    )

            return cast(Callable[P, T], async_wrapper)

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                stop = time.perf_counter()
                LOGGER.info(f"Runtime {func.__qualname__}: {stop - start:.6f} seconds")

        return wrapper

    return decorator
