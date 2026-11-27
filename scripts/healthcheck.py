"""One-shot non-sensitive liveness check for an operator's monitoring service."""
import json
import sys
import time
import urllib.request
from datetime import datetime,timezone

url=sys.argv[1] if len(sys.argv)>1 else "http://127.0.0.1:8000/api/health"
start=time.monotonic()
try:
    with urllib.request.urlopen(url,timeout=5) as response:
        payload=json.load(response)
    good=payload.get("status")=="ok"
except Exception:
    good=False
print(json.dumps({"time":datetime.now(timezone.utc).isoformat(),"healthy":good,"latency_ms":round((time.monotonic()-start)*1000)}))
sys.exit(0 if good else 1)
