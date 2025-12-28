#!/usr/bin/env bash
set -euo pipefail

url="${1:-http://127.0.0.1:8000/healthz}"
require_db="${REQUIRE_DB:-true}"

resp="$(curl -sS "$url")"

python - "$resp" "$require_db" <<'PY'
import json
import sys

resp = sys.argv[1]
require_db = sys.argv[2].lower() == "true"

data = json.loads(resp)
if data.get("ok") is not True:
    sys.exit("healthz ok is not true")

if require_db and data.get("db") is not True:
    sys.exit("healthz db is not true")

print("healthz ok:", data)
PY
