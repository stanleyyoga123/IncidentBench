import sys

import uvicorn

from api import create_app
from common.logger import get_logger
from config import SETTINGS

LOGGER = get_logger("Main")


app = create_app()


def main() -> int:
    try:
        uvicorn.run(
            app,
            host=SETTINGS.detector.api_host,
            port=SETTINGS.detector.api_port,
        )
    except Exception:
        LOGGER.exception("Detector process stopped after a fatal error")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
