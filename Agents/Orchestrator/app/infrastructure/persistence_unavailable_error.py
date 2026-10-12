class PersistenceUnavailableError(Exception):
    """Persistence response is unavailable; the operation may already have committed."""
