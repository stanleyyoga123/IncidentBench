#!/usr/bin/env bash
set -euo pipefail
python - "$1" "$2" <<'PYTHON'
import json, sys
from datetime import datetime, timezone
from pathlib import Path
context = json.loads(Path(sys.argv[1]).read_text())
output = Path(sys.argv[2]) / "sessions"
output.mkdir(exist_ok=True)
now = datetime.now(timezone.utc).isoformat()
for kind, filename in [("rca", "rca_session"), ("remediation", "remediation_run")]:
    row = {"id": "synthetic-" + kind, "workflow_id": context["run_id"],
           "status": "succeeded", "created_at": now, "started_at": now,
           "completed_at": now, "result": {"summary": "Synthetic exporter example; not observed evidence."}}
    (output / (filename + ".json")).write_text(json.dumps([row], indent=2) + "\n")
PYTHON
