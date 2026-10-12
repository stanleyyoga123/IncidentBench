import secrets
from typing import Callable

from fastapi import Header, HTTPException


def bearer(expected: str) -> Callable:
    def authorize(authorization: str | None = Header(default=None)) -> None:
        prefix = "Bearer "
        supplied = (
            authorization[len(prefix) :]
            if authorization and authorization.startswith(prefix)
            else ""
        )
        if not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status_code=401, detail="invalid bearer token")

    return authorize
