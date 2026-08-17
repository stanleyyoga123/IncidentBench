from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator

_SESSION_ID: ContextVar[str] = ContextVar(
    "session_id",
    default="default",
)


def get_session_id() -> str:
    return _SESSION_ID.get()


@contextmanager
def session(session_id: str) -> Iterator[None]:
    token = _SESSION_ID.set(session_id)
    try:
        yield
    finally:
        _SESSION_ID.reset(token)
