"""Record pipeline subprocess arguments without rendering or calling a judge."""
import json
import os
from pathlib import Path
import sys

with Path(os.environ['PIPELINE_CALL_LOG']).open('a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\n')
if sys.argv[2] == os.environ.get('PIPELINE_FAIL_MODULE'):
    raise SystemExit(7)
