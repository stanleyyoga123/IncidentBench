from contextlib import contextmanager
from typing import Iterator

from psycopg import Connection
from psycopg.rows import dict_row


class Database:
    """Read-only database access solely for the distributed maintenance gate."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    @contextmanager
    def connection(self) -> Iterator[Connection]:
        with Connection.connect(self._dsn, row_factory=dict_row) as connection:
            connection.read_only = True
            yield connection
