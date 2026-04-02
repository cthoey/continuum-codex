#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/stop_now_project.sh" "$@"
