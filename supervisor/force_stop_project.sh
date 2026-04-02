#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -eq 1 ]] && [[ "$1" == "-h" || "$1" == "--help" ]]; then
  echo "Usage: $0 <project-name> [config-path]"
  exit 0
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 <project-name> [config-path]" >&2
  exit 2
fi

PROJECT_NAME="$1"
if [[ "$PROJECT_NAME" == -* ]]; then
  echo "Project name cannot start with '-': $PROJECT_NAME" >&2
  exit 2
fi

CONFIG="${2:-$HERE/projects.json}"
SLUG="$(printf '%s' "$PROJECT_NAME" | LC_ALL=C tr -cs 'A-Za-z0-9._-' '_' | sed 's/^_//; s/_$//')"
PIDFILE="$HERE/supervisor.${SLUG}.pid"
CAFFEINATE_PIDFILE="$HERE/caffeinate.${SLUG}.pid"
RESTART_PIDFILE="$HERE/restart.${SLUG}.pid"
RESTART_STATEFILE="$HERE/restart.${SLUG}.json"
CONTROL_STATEFILE="$HERE/control.${SLUG}.json"
LAUNCHD_SERVICE="$HOME/Library/LaunchAgents/dev.continuum.codex.${SLUG}.plist"
SYSTEMD_SERVICE="$HOME/.config/systemd/user/continuum-${SLUG}.service"

if [[ -f "$LAUNCHD_SERVICE" || -f "$SYSTEMD_SERVICE" ]]; then
  echo "Force-stop for '$PROJECT_NAME' is only supported for detached runner mode. Use service controls for service-managed projects." >&2
  exit 1
fi

resolve_status_path() {
  python3 - "$CONFIG" "$SLUG" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1]).expanduser().resolve()
slug = sys.argv[2]

runtime_root = Path("./supervisor_state")
try:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    raw_root = payload.get("supervisor_root", "./supervisor_state")
    runtime_root = Path(str(raw_root)).expanduser()
except Exception:
    pass

if not runtime_root.is_absolute():
    runtime_root = (config_path.parent / runtime_root).resolve()

print(runtime_root / slug / "state" / "status.json")
PY
}

STATUS_PATH="$(resolve_status_path)"

read_active_codex_pid() {
  python3 - "$STATUS_PATH" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists():
    raise SystemExit(0)

try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    raise SystemExit(0)

pid = payload.get("active_codex_pid")
if isinstance(pid, int) and pid > 0:
    print(pid)
PY
}

write_force_stopped_state() {
  python3 - "$STATUS_PATH" "$PROJECT_NAME" <<'PY'
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
        "state_version": 2,
        "project": project_name,
        "updated_at": now,
        "finished_at": now,
        "state_kind": "force_stopped",
        "last_status": "INTERRUPTED",
        "status_detail": "Force stop requested by operator.",
        "active_codex_pid": None,
        "control_action": "force_stop",
    }
)

state_path.parent.mkdir(parents=True, exist_ok=True)
state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
}

cleanup_aux() {
  if [[ -f "$CAFFEINATE_PIDFILE" ]]; then
    CAFFEINATE_PID="$(cat "$CAFFEINATE_PIDFILE" 2>/dev/null || true)"
    if [[ -n "$CAFFEINATE_PID" ]] && kill -0 "$CAFFEINATE_PID" 2>/dev/null; then
      kill "$CAFFEINATE_PID" 2>/dev/null || true
    fi
    rm -f "$CAFFEINATE_PIDFILE"
  fi

  if [[ -f "$RESTART_PIDFILE" ]]; then
    RESTART_PID="$(cat "$RESTART_PIDFILE" 2>/dev/null || true)"
    if [[ -n "$RESTART_PID" ]] && kill -0 "$RESTART_PID" 2>/dev/null; then
      kill "$RESTART_PID" 2>/dev/null || true
    fi
  fi

  rm -f "$RESTART_PIDFILE" "$RESTART_STATEFILE" "$CONTROL_STATEFILE"
}

ACTIVE_CODEX_PID="$(read_active_codex_pid || true)"
SUPERVISOR_PID=""
if [[ -f "$PIDFILE" ]]; then
  SUPERVISOR_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
fi

if [[ -n "$ACTIVE_CODEX_PID" ]] && kill -0 "$ACTIVE_CODEX_PID" 2>/dev/null; then
  kill -KILL "$ACTIVE_CODEX_PID" 2>/dev/null || true
fi

if [[ -n "$SUPERVISOR_PID" ]] && kill -0 "$SUPERVISOR_PID" 2>/dev/null; then
  kill -KILL "$SUPERVISOR_PID" 2>/dev/null || true
fi

cleanup_aux
rm -f "$PIDFILE"
write_force_stopped_state

echo "Force stopped '$PROJECT_NAME'"
