#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
from pathlib import Path


CHILD: subprocess.Popen[str] | None = None
CAFFEINATE: subprocess.Popen[str] | None = None


def slugify(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")
    return slug or "project"


def write_pidfile(path: Path, pid: int) -> None:
    path.write_text(f"{pid}\n", encoding="utf-8")


def cleanup_pidfile(path: Path, expected_pid: int | None = None) -> None:
    if not path.exists():
        return
    if expected_pid is not None:
        try:
            current = int(path.read_text(encoding="utf-8").strip())
        except Exception:
            current = None
        if current != expected_pid:
            return
    path.unlink(missing_ok=True)


def stop_caffeinate() -> None:
    global CAFFEINATE
    if CAFFEINATE is None:
        return
    if CAFFEINATE.poll() is None:
        CAFFEINATE.terminate()
        try:
            CAFFEINATE.wait(timeout=5)
        except subprocess.TimeoutExpired:
            CAFFEINATE.kill()
            CAFFEINATE.wait()
    CAFFEINATE = None


def forward_signal(signum: int, _frame: object) -> None:
    if CHILD is not None and CHILD.poll() is None:
        try:
            CHILD.send_signal(signum)
        except ProcessLookupError:
            pass


def main(argv: list[str]) -> int:
    global CHILD
    global CAFFEINATE

    if len(argv) != 3:
        print("Usage: service_runner.py <config-path> <project-name>", file=sys.stderr)
        return 2

    config_path = Path(argv[1]).expanduser().resolve()
    project_name = argv[2]
    runner_root = Path(__file__).resolve().parent
    supervisor_path = runner_root / "codex_supervisor.py"
    slug = slugify(project_name)
    pidfile = runner_root / f"supervisor.{slug}.pid"
    caffeinate_pidfile = runner_root / f"caffeinate.{slug}.pid"

    if not config_path.exists():
        print(f"Config not found: {config_path}", file=sys.stderr)
        return 2
    if not supervisor_path.exists():
        print(f"Supervisor not found: {supervisor_path}", file=sys.stderr)
        return 2

    signal.signal(signal.SIGINT, forward_signal)
    signal.signal(signal.SIGTERM, forward_signal)

    cmd = [sys.executable, str(supervisor_path), str(config_path), project_name]
    CHILD = subprocess.Popen(cmd, text=True)
    write_pidfile(pidfile, CHILD.pid)

    try:
        if sys.platform == "darwin" and shutil.which("caffeinate"):
            CAFFEINATE = subprocess.Popen(
                ["caffeinate", "-is", "-w", str(CHILD.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            write_pidfile(caffeinate_pidfile, CAFFEINATE.pid)

        return CHILD.wait()
    finally:
        stop_caffeinate()
        cleanup_pidfile(caffeinate_pidfile)
        cleanup_pidfile(pidfile, CHILD.pid if CHILD is not None else None)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
