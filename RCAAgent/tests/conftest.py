import os


os.environ.setdefault("database.dsn", "postgresql://unused")
os.environ.setdefault("api.submit_token", "test-submit-token")
os.environ.setdefault("mcp.url", "http://mcp.test/mcp")
os.environ.setdefault("mcp.token", "test-mcp-token")
os.environ.setdefault("client.model", "test-model")
os.environ.setdefault("client.url", "http://model.test/v1")
