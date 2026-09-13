import os
import sys
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
os.environ.setdefault("orchestrator.base_url", "http://orchestrator.test")
os.environ.setdefault("orchestrator.token", "store")
os.environ.setdefault("api.submit_token", "submit")
os.environ.setdefault("client.model", "test-model")
os.environ.setdefault("client.url", "http://model.test/v1")
