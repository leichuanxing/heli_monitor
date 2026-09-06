import json
import sys
import urllib.request

base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost").rstrip("/")
for path in ("/health/live", "/health/ready"):
    with urllib.request.urlopen(base + path, timeout=10) as response:
        payload = json.load(response)
        if response.status != 200 or payload.get("status") != "ok":
            raise SystemExit(f"{path} failed: {response.status} {payload}")
        print(f"{path}: ok")

