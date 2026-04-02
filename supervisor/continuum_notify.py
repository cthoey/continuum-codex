#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def notify_local(title: str, message: str) -> None:
    system = platform.system().lower()
    try:
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
    except Exception:
        return


def post_webhook(url: str, payload: dict[str, Any], timeout_seconds: int) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Continuum for Codex",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds):
            return
    except urllib.error.URLError:
        return


def emit_notification(
    *,
    runner_root: Path,
    enabled: bool,
    payload: dict[str, Any],
    notification_command: list[str] | None = None,
    notification_webhook_url: str | None = None,
    notification_webhook_timeout_seconds: int = 10,
) -> None:
    runner_root.mkdir(parents=True, exist_ok=True)
    log_path = runner_root / "continuum-notify.log"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, sort_keys=True) + "\n")

    if not enabled:
        return

    title = str(payload.get("title") or payload.get("event_type") or "Continuum")
    message = str(payload.get("message") or payload.get("detail") or "")
    notify_local(title, message[:240])

    if notification_command:
        try:
            subprocess.run(
                [*notification_command, json.dumps(payload)],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except Exception:
            pass

    if notification_webhook_url:
        post_webhook(notification_webhook_url, payload, notification_webhook_timeout_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit a Continuum notification event.")
    parser.add_argument("--config", required=True, help="Path to projects.json.")
    parser.add_argument("--payload", required=True, help="JSON payload string.")
    args = parser.parse_args(argv)

    config_path = Path(args.config).expanduser().resolve()
    payload = json.loads(args.payload)
    if not isinstance(payload, dict):
        raise SystemExit("Notification payload must be a JSON object.")

    config = load_json(config_path)
    runner_root = config_path.parent
    emit_notification(
        runner_root=runner_root,
        enabled=bool(config.get("notify", True)),
        payload=payload,
        notification_command=list(config.get("notification_command", []))
        if isinstance(config.get("notification_command"), list)
        else None,
        notification_webhook_url=config.get("notification_webhook_url")
        if isinstance(config.get("notification_webhook_url"), str) and config.get("notification_webhook_url")
        else None,
        notification_webhook_timeout_seconds=int(config.get("notification_webhook_timeout_seconds", 10)),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
