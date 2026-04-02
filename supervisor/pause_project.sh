#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -eq 1 ]] && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: $0 <project-name>"
  exit 0
fi

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <project-name>" >&2
  exit 2
fi

PROJECT_NAME="$1"
if [[ "$PROJECT_NAME" == -* ]]; then
  echo "Project name cannot start with '-': $PROJECT_NAME" >&2
  exit 2
fi

SLUG="$(printf '%s' "$PROJECT_NAME" | LC_ALL=C tr -cs 'A-Za-z0-9._-' '_' | sed 's/^_//; s/_$//')"
PIDFILE="$HERE/supervisor.${SLUG}.pid"
CONTROL_STATEFILE="$HERE/control.${SLUG}.json"

if [[ ! -f "$PIDFILE" ]]; then
  echo "No PID file found for '$PROJECT_NAME': $PIDFILE" >&2
  exit 1
fi

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
  echo "No running project supervisor found for '$PROJECT_NAME'" >&2
  exit 1
fi

python3 - "$CONTROL_STATEFILE" "$PROJECT_NAME" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
project_name = sys.argv[2]
now = datetime.now(timezone.utc).isoformat()

payload = {}
if state_path.exists():
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        payload = {}

payload.update(
    {
        "project": project_name,
        "action": "pause_after_pass",
        "phase": "requested",
        "detail": "Pause requested; stop after the current pass finishes.",
        "updated_at": now,
        "requested_at": payload.get("requested_at", now),
    }
)

state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY

echo "Requested pause-after-pass for '$PROJECT_NAME'"
