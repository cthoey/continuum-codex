#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$HERE/projects.json}"
PIDFILE="$HERE/supervisor.pid"
CAFFEINATE_PIDFILE="$HERE/caffeinate.pid"
LOGFILE="$HERE/supervisor.out.log"

if [[ ! -f "$CONFIG" ]]; then
  echo "Config not found: $CONFIG" >&2
  exit 1
fi

if [[ -f "$PIDFILE" ]]; then
  OLD_PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Supervisor already running with PID $OLD_PID" >&2
    exit 1
  fi
fi

if [[ -f "$CAFFEINATE_PIDFILE" ]]; then
  OLD_CAFFEINATE_PID="$(cat "$CAFFEINATE_PIDFILE" 2>/dev/null || true)"
  if [[ -n "$OLD_CAFFEINATE_PID" ]] && kill -0 "$OLD_CAFFEINATE_PID" 2>/dev/null; then
    kill "$OLD_CAFFEINATE_PID" 2>/dev/null || true
  fi
  rm -f "$CAFFEINATE_PIDFILE"
fi

nohup python3 "$HERE/codex_supervisor.py" "$CONFIG" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
SUPERVISOR_PID="$(cat "$PIDFILE")"

if [[ "$(uname -s)" == "Darwin" ]] && command -v caffeinate >/dev/null 2>&1; then
  nohup caffeinate -is -w "$SUPERVISOR_PID" >/dev/null 2>&1 &
  echo $! > "$CAFFEINATE_PIDFILE"
  echo "Started supervisor PID $SUPERVISOR_PID"
  echo "Automatic caffeinate enabled with PID $(cat "$CAFFEINATE_PIDFILE")"
else
  echo "Started supervisor PID $SUPERVISOR_PID"
fi

echo "Tail logs with: tail -f '$LOGFILE'"
