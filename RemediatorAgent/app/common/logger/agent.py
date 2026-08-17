from typing import Any
import os
import shutil
import json

FOLDER = os.path.join("log", "agent")


class AgentLogger:
    def __init__(self, name: str, flush: bool = False):
        self._dst = os.path.join(FOLDER, name)
        if flush and os.path.isdir(self._dst):
            shutil.rmtree(self._dst)
        os.makedirs(self._dst, exist_ok=True)

    def log(self, conversation: list[dict[str, Any]]):
        path = os.path.join(self._dst, "conversation.json")
        json.dump(conversation, open(path, "w"))
