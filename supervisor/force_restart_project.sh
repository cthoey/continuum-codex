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
LAUNCHD_SERVICE="$HOME/Library/LaunchAgents/dev.continuum.codex.${SLUG}.plist"
SYSTEMD_SERVICE="$HOME/.config/systemd/user/continuum-${SLUG}.service"

if [[ -f "$LAUNCHD_SERVICE" || -f "$SYSTEMD_SERVICE" ]]; then
  echo "Force-restart for '$PROJECT_NAME' is only supported for detached runner mode. Use service controls for service-managed projects." >&2
  exit 1
fi

"$HERE/force_stop_project.sh" "$PROJECT_NAME" "$CONFIG" >/dev/null
exec "$HERE/launch_project.sh" "$PROJECT_NAME" "$CONFIG"
