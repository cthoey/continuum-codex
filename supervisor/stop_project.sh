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
CAFFEINATE_PIDFILE="$HERE/caffeinate.${SLUG}.pid"
RESTART_PIDFILE="$HERE/restart.${SLUG}.pid"
RESTART_STATEFILE="$HERE/restart.${SLUG}.json"
CONTROL_STATEFILE="$HERE/control.${SLUG}.json"
LAUNCHD_SERVICE="$HOME/Library/LaunchAgents/dev.continuum.codex.${SLUG}.plist"
LAUNCHD_TARGET="gui/$(id -u)/dev.continuum.codex.${SLUG}"
SYSTEMD_SERVICE="$HOME/.config/systemd/user/continuum-${SLUG}.service"
SYSTEMD_TARGET="continuum-${SLUG}.service"

cleanup_caffeinate() {
  if [[ ! -f "$CAFFEINATE_PIDFILE" ]]; then
    return
  fi

  CAFFEINATE_PID="$(cat "$CAFFEINATE_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$CAFFEINATE_PID" ]] && kill -0 "$CAFFEINATE_PID" 2>/dev/null; then
    kill "$CAFFEINATE_PID" 2>/dev/null || true
  fi
  rm -f "$CAFFEINATE_PIDFILE"
}

cleanup_restart() {
  if [[ -f "$RESTART_PIDFILE" ]]; then
    RESTART_PID="$(cat "$RESTART_PIDFILE" 2>/dev/null || true)"
    if [[ -n "$RESTART_PID" ]] && kill -0 "$RESTART_PID" 2>/dev/null; then
      kill "$RESTART_PID" 2>/dev/null || true
    fi
    rm -f "$RESTART_PIDFILE"
  fi

  rm -f "$RESTART_STATEFILE"
}

cleanup_control() {
  rm -f "$CONTROL_STATEFILE"
}

write_stop_requested() {
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
        "action": "stop_after_pass",
        "phase": "requested",
        "detail": "Stop requested; finish the current pass and then stop.",
        "updated_at": now,
        "requested_at": payload.get("requested_at", now),
    }
)

state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
PY
}

signal_service_term() {
  local signaled="false"
  if [[ -f "$LAUNCHD_SERVICE" ]] && command -v launchctl >/dev/null 2>&1; then
    launchctl kill TERM "$LAUNCHD_TARGET" >/dev/null 2>&1 || true
    signaled="true"
  fi
  if [[ -f "$SYSTEMD_SERVICE" ]] && command -v systemctl >/dev/null 2>&1; then
    systemctl --user kill --signal=TERM "$SYSTEMD_TARGET" >/dev/null 2>&1 || true
    signaled="true"
  fi
  [[ "$signaled" == "true" ]]
}

if [[ ! -f "$PIDFILE" ]]; then
  if signal_service_term; then
    write_stop_requested
    cleanup_restart
    echo "Requested clean stop for service-managed project '$PROJECT_NAME'"
    exit 0
  fi
  cleanup_caffeinate
  cleanup_restart
  cleanup_control
  echo "No PID file found for '$PROJECT_NAME': $PIDFILE" >&2
  exit 1
fi

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  if signal_service_term; then
    write_stop_requested
    cleanup_restart
    rm -f "$PIDFILE"
    echo "Requested clean stop for service-managed project '$PROJECT_NAME'"
    exit 0
  fi
  cleanup_caffeinate
  cleanup_restart
  cleanup_control
  echo "PID file is empty for '$PROJECT_NAME': $PIDFILE" >&2
  rm -f "$PIDFILE"
  exit 1
fi

if kill -0 "$PID" 2>/dev/null; then
  write_stop_requested
  signal_service_term >/dev/null 2>&1 || true
  kill "$PID"
  cleanup_restart
  echo "Sent TERM to project supervisor '$PROJECT_NAME' (PID $PID)"
  exit 0
fi

cleanup_caffeinate
cleanup_restart
cleanup_control
rm -f "$PIDFILE"
echo "No running project supervisor found for '$PROJECT_NAME'; removed stale PID file"
