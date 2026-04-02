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

nohup python3 "$HERE/codex_supervisor.py" "$CONFIG" "$PROJECT_NAME" >> "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "Started project supervisor '$PROJECT_NAME' with PID $(cat "$PIDFILE")"
echo "Tail logs with: tail -f '$LOGFILE'"
