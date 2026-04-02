#!/usr/bin/env python3
"""Optional Codex `notify` helper.

Configure in ~/.codex/config.toml:
    notify = ["python3", "/path/to/notify.py"]

This script tries a local desktop notification on macOS or Linux and also logs
JSON payloads to ~/codex-notify.log.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


def notify_local(title: str, message: str) -> None:
    system = platform.system().lower()
    if system == "darwin" and shutil.which("osascript"):
        subprocess.run(
            [
                "osascript",
                "-e",
                f'display notification "{message.replace("\"", "\\\"")}" with title "{title.replace("\"", "\\\"")}"',
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if system == "linux" and shutil.which("notify-send"):
        subprocess.run(
            ["notify-send", title, message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    if len(sys.argv) < 2:
        return 0

    try:
        payload = json.loads(sys.argv[1])
    except Exception:
        return 0

    log_path = Path.home() / "codex-notify.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")

    if payload.get("type") != "agent-turn-complete":
        return 0

    cwd = payload.get("cwd", "")
    message = payload.get("last-assistant-message", "Turn complete")
    title = f"Codex: {Path(cwd).name or 'task'}"
    notify_local(title, message[:240])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
