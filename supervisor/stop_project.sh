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

if [[ ! -f "$PIDFILE" ]]; then
  cleanup_caffeinate
  cleanup_restart
  echo "No PID file found for '$PROJECT_NAME': $PIDFILE" >&2
  exit 1
fi

PID="$(cat "$PIDFILE" 2>/dev/null || true)"
if [[ -z "$PID" ]]; then
  cleanup_caffeinate
  cleanup_restart
  echo "PID file is empty for '$PROJECT_NAME': $PIDFILE" >&2
  rm -f "$PIDFILE"
  exit 1
fi

if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  cleanup_caffeinate
  cleanup_restart
  echo "Sent TERM to project supervisor '$PROJECT_NAME' (PID $PID)"
  exit 0
fi

cleanup_caffeinate
cleanup_restart
rm -f "$PIDFILE"
echo "No running project supervisor found for '$PROJECT_NAME'; removed stale PID file"
