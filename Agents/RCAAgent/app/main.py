import uvicorn
from api import create_app
from config import SETTINGS

app = create_app(SETTINGS)

if __name__ == "__main__":
    uvicorn.run(app, host=SETTINGS.api.host, port=SETTINGS.api.port)
