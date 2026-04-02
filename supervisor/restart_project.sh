#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"

write_restart_state() {
  local statefile="$1"
  local project_name="$2"
  local phase="$3"
  local detail="${4:-}"
  local supervisor_pid="${5:-}"

  python3 - "$statefile" "$project_name" "$phase" "$detail" "$supervisor_pid" <<'PY'
from __future__ import annotations
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

state_path = Path(sys.argv[1])
project_name = sys.argv[2]
phase = sys.argv[3]
detail = sys.argv[4]
supervisor_pid = sys.argv[5]
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
        "action": "restart",
        "phase": phase,
        "detail": detail,
        "updated_at": now,
        "requested_at": payload.get("requested_at", now),
    }
)

if supervisor_pid:
    payload["supervisor_pid"] = supervisor_pid
else:
    payload.pop("supervisor_pid", None)

state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
}

cleanup_caffeinate_pidfile() {
  if [[ ! -f "$CAFFEINATE_PIDFILE" ]]; then
    return
  fi

  CAFFEINATE_PID="$(cat "$CAFFEINATE_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$CAFFEINATE_PID" ]] && kill -0 "$CAFFEINATE_PID" 2>/dev/null; then
    kill "$CAFFEINATE_PID" 2>/dev/null || true
  fi
  rm -f "$CAFFEINATE_PIDFILE"
}

cleanup_restart_files() {
  rm -f "$RESTART_PIDFILE" "$RESTART_STATEFILE"
}

run_worker() {
  local target_pid="$1"
  local temp_caffeinate_pid=""

  if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1 && [[ ! -f "$CAFFEINATE_PIDFILE" ]]; then
    caffeinate -is -w "$target_pid" >/dev/null 2>&1 &
    temp_caffeinate_pid="$!"
  fi

  write_restart_state "$RESTART_STATEFILE" "$PROJECT_NAME" "waiting" "Waiting for the current pass to finish before restarting." "$target_pid"
  kill "$target_pid"

  local deadline=$((SECONDS + WAIT_TIMEOUT_SECONDS))
  while kill -0 "$target_pid" 2>/dev/null; do
    if (( SECONDS >= deadline )); then
      if [[ -n "$temp_caffeinate_pid" ]] && kill -0 "$temp_caffeinate_pid" 2>/dev/null; then
        kill "$temp_caffeinate_pid" 2>/dev/null || true
      fi
      write_restart_state "$RESTART_STATEFILE" "$PROJECT_NAME" "timed_out" "Timed out waiting for the supervisor to exit cleanly after ${WAIT_TIMEOUT_SECONDS} seconds." "$target_pid"
      rm -f "$RESTART_PIDFILE"
      exit 1
    fi
    sleep 2
  done

  if [[ -n "$temp_caffeinate_pid" ]] && kill -0 "$temp_caffeinate_pid" 2>/dev/null; then
    kill "$temp_caffeinate_pid" 2>/dev/null || true
  fi

  cleanup_caffeinate_pidfile
  rm -f "$PIDFILE"
  write_restart_state "$RESTART_STATEFILE" "$PROJECT_NAME" "relaunching" "Launching a fresh supervisor instance."
  rm -f "$RESTART_PIDFILE"

  if "$HERE/launch_project.sh" "$PROJECT_NAME" "$CONFIG" >/dev/null 2>&1; then
    rm -f "$RESTART_STATEFILE"
    exit 0
  fi

  write_restart_state "$RESTART_STATEFILE" "$PROJECT_NAME" "failed" "Relaunch failed after the supervisor exited."
  exit 1
}

if [[ $# -ge 1 ]] && [[ "$1" == "--worker" ]]; then
  if [[ $# -ne 4 ]]; then
    echo "Usage: $0 --worker <project-name> <config-path> <supervisor-pid>" >&2
    exit 2
  fi
  PROJECT_NAME="$2"
  CONFIG="$3"
  TARGET_PID="$4"
else
  if [[ $# -eq 1 ]] && [[ "$1" == "-h" || "$1" == "--help" ]]; then
    echo "Usage: $0 <project-name> [config-path]"
    exit 0
  fi

  if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "Usage: $0 <project-name> [config-path]" >&2
    exit 2
  fi

  PROJECT_NAME="$1"
  CONFIG="${2:-$HERE/projects.json}"
  TARGET_PID=""
fi

if [[ "$PROJECT_NAME" == -* ]]; then
  echo "Project name cannot start with '-': $PROJECT_NAME" >&2
  exit 2
fi

SLUG="$(printf '%s' "$PROJECT_NAME" | LC_ALL=C tr -cs 'A-Za-z0-9._-' '_' | sed 's/^_//; s/_$//')"
PIDFILE="$HERE/supervisor.${SLUG}.pid"
CAFFEINATE_PIDFILE="$HERE/caffeinate.${SLUG}.pid"
RESTART_PIDFILE="$HERE/restart.${SLUG}.pid"
RESTART_STATEFILE="$HERE/restart.${SLUG}.json"
CONTROL_STATEFILE="$HERE/control.${SLUG}.json"
WAIT_TIMEOUT_SECONDS="${CODEX_RESTART_WAIT_TIMEOUT_SECONDS:-7200}"

if [[ -n "$TARGET_PID" ]]; then
  run_worker "$TARGET_PID"
fi

if [[ -f "$RESTART_PIDFILE" ]]; then
  OLD_RESTART_PID="$(cat "$RESTART_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_RESTART_PID" ]] && kill -0 "$OLD_RESTART_PID" 2>/dev/null; then
    echo "Restart already pending for '$PROJECT_NAME' (PID $OLD_RESTART_PID)"
    exit 0
  fi
  rm -f "$RESTART_PIDFILE"
fi

if [[ -f "$PIDFILE" ]]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$PID" ]] && kill -0 "$PID" 2>/dev/null; then
    write_restart_state "$RESTART_STATEFILE" "$PROJECT_NAME" "requested" "Restart requested; waiting for the current pass to finish." "$PID"
    nohup "$0" --worker "$PROJECT_NAME" "$CONFIG" "$PID" >/dev/null 2>&1 &
    echo $! > "$RESTART_PIDFILE"
    echo "Requested graceful restart for '$PROJECT_NAME'; waiting for supervisor PID $PID to exit."
    exit 0
  fi
fi

cleanup_caffeinate_pidfile
cleanup_restart_files
rm -f "$CONTROL_STATEFILE"
rm -f "$PIDFILE"
exec "$HERE/launch_project.sh" "$PROJECT_NAME" "$CONFIG"
