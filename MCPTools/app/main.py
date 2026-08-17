import uvicorn

from config import get_settings
from server import create_app

SETTINGS = get_settings()
app = create_app(SETTINGS)

if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.server.host, port=SETTINGS.server.port)
