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
LOGFILE="$HERE/supervisor.${SLUG}.out.log"

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG" >&2
  exit 1
fi

if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Project supervisor already running for '$PROJECT_NAME' with PID $OLD_PID" >&2
    exit 1
  fi
  rm -f "$PIDFILE"
fi

if [[ -f "$CAFFEINATE_PIDFILE" ]]; then
  OLD_CAFFEINATE_PID="$(cat "$CAFFEINATE_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_CAFFEINATE_PID" ]] && kill -0 "$OLD_CAFFEINATE_PID" 2>/dev/null; then
    kill "$OLD_CAFFEINATE_PID" 2>/dev/null || true
  fi
  rm -f "$CAFFEINATE_PIDFILE"
fi

if [[ -f "$RESTART_PIDFILE" ]]; then
  OLD_RESTART_PID="$(cat "$RESTART_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_RESTART_PID" ]] && kill -0 "$OLD_RESTART_PID" 2>/dev/null; then
    echo "Project restart already pending for '$PROJECT_NAME' with PID $OLD_RESTART_PID" >&2
    exit 1
  fi
  rm -f "$RESTART_PIDFILE"
fi

if [[ -f "$RESTART_STATEFILE" ]]; then
  rm -f "$RESTART_STATEFILE"
fi

if [[ -f "$CONTROL_STATEFILE" ]]; then
  rm -f "$CONTROL_STATEFILE"
fi

nohup python3 "$HERE/codex_supervisor.py" "$CONFIG" "$PROJECT_NAME" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
SUPERVISOR_PID="$(cat "$PIDFILE")"

if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1; then
  nohup caffeinate -is -w "$SUPERVISOR_PID" >/dev/null 2>&1 &
  echo $! > "$CAFFEINATE_PIDFILE"
  echo "Started project supervisor '$PROJECT_NAME' with PID $SUPERVISOR_PID"
  echo "Automatic caffeinate enabled with PID $(cat "$CAFFEINATE_PIDFILE")"
else
  echo "Started project supervisor '$PROJECT_NAME' with PID $SUPERVISOR_PID"
fi

echo "Tail logs with: tail -f '$LOGFILE'"
