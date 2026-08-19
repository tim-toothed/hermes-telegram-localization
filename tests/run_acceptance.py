import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
checks = {}
for name in ("runtime_acceptance.py", "stratified_acceptance.py"):
    proc = subprocess.run([sys.executable, str(HERE / name)], capture_output=True, text=True)
    if proc.returncode != 0:
        checks[name] = {"status": "ERROR", "returncode": proc.returncode, "stderr": proc.stderr[-2000:]}
        continue
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    checks[name] = {"status": "OK", "summary": payload["summary"], "network_calls": payload["network_calls"]}
summary = {
    status: sum(item.get("summary", {}).get(status, 0) for item in checks.values())
    for status in ("PASS", "FAIL", "BLOCKED")
}
payload = {"summary": summary, "checks": checks}
print(json.dumps(payload, ensure_ascii=False, indent=2))
raise SystemExit(1 if summary["FAIL"] or any(x["status"] != "OK" for x in checks.values()) else 0)
