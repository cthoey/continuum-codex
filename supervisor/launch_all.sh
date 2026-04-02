#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
CONFIG="${1:-$HERE/projects.json}"
PIDFILE="$HERE/supervisor.pid"
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

nohup python3 "$HERE/codex_supervisor.py" "$CONFIG" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "Started supervisor PID $(cat "$PIDFILE")"
echo "Tail logs with: tail -f '$LOGFILE'"
