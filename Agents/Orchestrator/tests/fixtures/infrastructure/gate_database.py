from contextlib import contextmanager
from unittest.mock import MagicMock


class GateDatabase:
    def __init__(self, *, locked: bool = True, maintenance: bool = False) -> None:
        self.locked = locked
        self.maintenance = maintenance
        self.open = False
        self.queries = []

    @contextmanager
    def connection(self):
        self.open = True
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.execute.side_effect = lambda query, *args: self.queries.append(query)
        cursor.fetchone.side_effect = [{"locked": self.locked}, {"maintenance": self.maintenance}]
        connection = MagicMock()
        connection.cursor.return_value = cursor
        try:
            yield connection
        finally:
            self.open = False

