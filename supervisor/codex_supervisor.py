#!/usr/bin/env python3
"""Run multiple Codex projects unattended.

Usage:
    python3 codex_supervisor.py /path/to/projects.json [project_name ...]

The supervisor expects each Codex run to end its final message with exactly one line:
    STATUS: CONTINUE
    STATUS: DONE
    STATUS: BLOCKED: <reason>

For the first pass, the supervisor runs:
    codex exec ... <initial prompt>

For follow-up passes, it runs:
    codex exec resume --last ... <followup prompt>

Each project gets its own log and state files.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from continuum_notify import emit_notification

STATUS_CONTINUE = "CONTINUE"
STATUS_DONE = "DONE"
STATUS_BLOCKED = "BLOCKED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_FAILED = "FAILED"
STATUS_INTERRUPTED = "INTERRUPTED"
STATUS_RATE_LIMIT_WAIT = "RATE_LIMIT_WAIT"

STATE_RUNNING = "running"
STATE_INACTIVE = "inactive"
STATE_RATE_LIMIT_WAIT = "rate_limited_wait"
STATE_PAUSED = "paused"
STATE_STOPPED = "stopped"
STATE_FORCE_STOPPED = "force_stopped"
STATE_DONE = "done"
STATE_BLOCKED = "blocked"
STATE_FAILED = "failed"
STATE_MAX_PASSES = "max_passes"

CONTROL_ACTION_PAUSE = "pause_after_pass"

STATUS_RE = re.compile(r"^STATUS:\s*(CONTINUE|DONE|BLOCKED)(?::\s*(.*))?\s*$", re.MULTILINE)
QUOTA_PATTERNS = [
    re.compile(r"insufficient_quota", re.IGNORECASE),
    re.compile(r"exceeded your current quota", re.IGNORECASE),
    re.compile(r"plan and billing", re.IGNORECASE),
    re.compile(r"maximum monthly spend", re.IGNORECASE),
    re.compile(r"ran out of credits", re.IGNORECASE),
    re.compile(r"credit balance", re.IGNORECASE),
]
RATE_LIMIT_PATTERNS = [
    re.compile(r"rate limit", re.IGNORECASE),
    re.compile(r"too many requests", re.IGNORECASE),
    re.compile(r"slow down", re.IGNORECASE),
    re.compile(r"overloaded", re.IGNORECASE),
    re.compile(r"try again later", re.IGNORECASE),
    re.compile(r"\b503\b", re.IGNORECASE),
]
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 15 * 60
DEFAULT_MAX_RATE_LIMIT_RETRIES = 8

DEFAULT_FOLLOWUP_PROMPT = (
    "Proceed with the project. Continue from your last checkpoint. "
    "Update the progress notes. Choose the next highest-value task yourself. "
    "Only stop when you are actually DONE or BLOCKED. "
    "End with exactly one status line: STATUS: CONTINUE, STATUS: DONE, or STATUS: BLOCKED: <reason>."
)

PRINT_LOCK = threading.Lock()
STOP_EVENT = threading.Event()


@dataclass
class ProjectConfig:
    name: str
    path: str
    prompt: str
    profile: str | None = None
    model: str | None = None
    extra_args: list[str] = field(default_factory=list)
    followup_prompt: str | None = None
    max_passes: int = 0  # 0 => unlimited
    resume_existing: bool = True
    skip_git_repo_check: bool = False
    enabled: bool = True


@dataclass
class RuntimeConfig:
    codex_bin: str = "codex"
    default_profile: str | None = None
    default_followup_prompt: str = DEFAULT_FOLLOWUP_PROMPT
    supervisor_root: str = "./supervisor_state"
    notify: bool = True
    notification_command: list[str] = field(default_factory=list)
    notification_webhook_url: str | None = None
    notification_webhook_timeout_seconds: int = 10
    inactivity_notify_after_seconds: int = 30 * 60
    rate_limit_retry_seconds: int = DEFAULT_RATE_LIMIT_RETRY_SECONDS
    max_rate_limit_retries: int = DEFAULT_MAX_RATE_LIMIT_RETRIES
    projects: list[ProjectConfig] = field(default_factory=list)


@dataclass
class ParsedStatus:
    kind: str
    detail: str = ""


@dataclass
class FailureSignal:
    kind: str
    detail: str = ""


class SupervisorError(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def echo(msg: str) -> None:
    with PRINT_LOCK:
        print(msg, flush=True)


def load_config(path: Path) -> RuntimeConfig:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    projects_raw = raw.get("projects", [])
    projects: list[ProjectConfig] = []
    for item in projects_raw:
        projects.append(
            ProjectConfig(
                name=item["name"],
                path=item["path"],
                prompt=item["prompt"],
                profile=item.get("profile"),
                model=item.get("model"),
                extra_args=list(item.get("extra_args", [])),
                followup_prompt=item.get("followup_prompt"),
                max_passes=int(item.get("max_passes", 0)),
                resume_existing=bool(item.get("resume_existing", True)),
                skip_git_repo_check=bool(item.get("skip_git_repo_check", False)),
                enabled=bool(item.get("enabled", True)),
            )
        )

    return RuntimeConfig(
        codex_bin=raw.get("codex_bin", "codex"),
        default_profile=raw.get("default_profile"),
        default_followup_prompt=raw.get("default_followup_prompt", DEFAULT_FOLLOWUP_PROMPT),
        supervisor_root=raw.get("supervisor_root", "./supervisor_state"),
        notify=bool(raw.get("notify", True)),
        notification_command=list(raw.get("notification_command", []))
        if isinstance(raw.get("notification_command"), list)
        else [],
        notification_webhook_url=raw.get("notification_webhook_url")
        if isinstance(raw.get("notification_webhook_url"), str) and raw.get("notification_webhook_url")
        else None,
        notification_webhook_timeout_seconds=int(raw.get("notification_webhook_timeout_seconds", 10)),
        inactivity_notify_after_seconds=int(raw.get("inactivity_notify_after_seconds", 30 * 60)),
        rate_limit_retry_seconds=int(raw.get("rate_limit_retry_seconds", DEFAULT_RATE_LIMIT_RETRY_SECONDS)),
        max_rate_limit_retries=int(raw.get("max_rate_limit_retries", DEFAULT_MAX_RATE_LIMIT_RETRIES)),
        projects=projects,
    )


def select_projects(runtime: RuntimeConfig, selected_names: list[str]) -> None:
    if not selected_names:
        return

    selected_set = set(selected_names)
    by_name = {project.name: project for project in runtime.projects}
    missing = [name for name in selected_names if name not in by_name]
    if missing:
        raise SupervisorError(f"Unknown project name(s): {', '.join(missing)}")

    runtime.projects = [by_name[name] for name in selected_names]
    for project in runtime.projects:
        project.enabled = True


def ensure_executable_exists(binary: str) -> None:
    if shutil.which(binary) is None:
        raise SupervisorError(f"Could not find executable: {binary}")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        loaded = json.loads(read_text(path))
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def parse_status(message: str) -> ParsedStatus:
    matches = list(STATUS_RE.finditer(message))
    if not matches:
        return ParsedStatus(STATUS_UNKNOWN, "No STATUS line found")
    last = matches[-1]
    kind = last.group(1)
    detail = (last.group(2) or "").strip()
    return ParsedStatus(kind, detail)


def build_state_payload(
    runtime: RuntimeConfig,
    project: ProjectConfig,
    phase: str | None,
    pass_num: int,
    state_kind: str,
    prior_state: dict[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    prior_state = prior_state or {}
    payload: dict[str, Any] = {
        "state_version": 2,
        "project": project.name,
        "updated_at": utcnow_iso(),
        "phase": phase,
        "pass_num": pass_num,
        "state_kind": state_kind,
        "path": project.path,
        "profile": project.profile or runtime.default_profile,
        "started_at": prior_state.get("started_at") or utcnow_iso(),
    }
    payload.update(extra)
    return payload


def build_base_exec_args(runtime: RuntimeConfig, project: ProjectConfig) -> list[str]:
    args = [runtime.codex_bin, "exec", "-C", project.path]
    profile = project.profile or runtime.default_profile
    if profile:
        args.extend(["-p", profile])
    if project.model:
        args.extend(["-m", project.model])
    if project.skip_git_repo_check:
        args.append("--skip-git-repo-check")
    args.extend(project.extra_args)
    return args


def emit_runtime_notification(
    runtime: RuntimeConfig,
    runner_root: Path,
    *,
    event_type: str,
    project: ProjectConfig,
    title: str,
    message: str,
    severity: str = "info",
    **extra: Any,
) -> None:
    payload: dict[str, Any] = {
        "timestamp": utcnow_iso(),
        "event_type": event_type,
        "severity": severity,
        "project": project.name,
        "project_path": project.path,
        "title": title,
        "message": message,
    }
    payload.update(extra)
    emit_notification(
        runner_root=runner_root,
        enabled=runtime.notify,
        payload=payload,
        notification_command=runtime.notification_command,
        notification_webhook_url=runtime.notification_webhook_url,
        notification_webhook_timeout_seconds=runtime.notification_webhook_timeout_seconds,
    )


def classify_failure_signal(text: str) -> FailureSignal | None:
    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not candidate:
            continue
        for pattern in QUOTA_PATTERNS:
            if pattern.search(candidate):
                return FailureSignal("quota_exhausted", candidate)
        for pattern in RATE_LIMIT_PATTERNS:
            if pattern.search(candidate):
                return FailureSignal("rate_limited", candidate)

    for pattern in QUOTA_PATTERNS:
        if pattern.search(text):
            return FailureSignal("quota_exhausted", "Quota or credits exhausted")
    for pattern in RATE_LIMIT_PATTERNS:
        if pattern.search(text):
            return FailureSignal("rate_limited", "Temporarily rate limited or service overloaded")
    return None


def sleep_with_stop(seconds: int) -> bool:
    deadline = time.time() + max(seconds, 0)
    while not STOP_EVENT.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            return True
        time.sleep(min(5.0, remaining))
    return False


def sleep_with_control(seconds: int, control_path: Path) -> str:
    deadline = time.time() + max(seconds, 0)
    while not STOP_EVENT.is_set():
        control = load_json_file(control_path)
        if control.get("action") == CONTROL_ACTION_PAUSE:
            return "pause_requested"
        remaining = deadline - time.time()
        if remaining <= 0:
            return "completed"
        time.sleep(min(2.0, remaining))
    return "stop_requested"


def consume_control_action(control_path: Path, action: str) -> dict[str, Any] | None:
    control = load_json_file(control_path)
    if control.get("action") != action:
        return None
    control_path.unlink(missing_ok=True)
    return control


def clear_control_file(control_path: Path) -> None:
    control_path.unlink(missing_ok=True)


def run_codex_command(
    cmd: list[str],
    log_path: Path,
    on_start: Callable[[int], None] | None = None,
    inactivity_after_seconds: int = 0,
    on_inactive: Callable[[int], None] | None = None,
    on_activity_resumed: Callable[[], None] | None = None,
    on_heartbeat: Callable[[int, bool], None] | None = None,
) -> tuple[int, str, str]:
    ensure_dir(log_path.parent)
    start_offset = log_path.stat().st_size if log_path.exists() else 0
    with log_path.open("a", encoding="utf-8") as log_file:
        log_file.write("\n" + "=" * 80 + "\n")
        log_file.write(f"[{utcnow_iso()}] RUN: {' '.join(cmd)}\n")
        log_file.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=log_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if on_start is not None:
            on_start(proc.pid)
        last_activity_ts = time.time()
        try:
            last_activity_ts = max(last_activity_ts, log_path.stat().st_mtime)
        except Exception:
            pass
        inactivity_notified = False
        last_heartbeat_ts = 0.0

        while True:
            try:
                proc.wait(timeout=2.0)
                break
            except subprocess.TimeoutExpired:
                pass

            try:
                observed_mtime = log_path.stat().st_mtime
                if observed_mtime > last_activity_ts + 0.01:
                    last_activity_ts = observed_mtime
                    if inactivity_notified:
                        inactivity_notified = False
                        if on_activity_resumed is not None:
                            on_activity_resumed()
            except Exception:
                pass

            if inactivity_after_seconds > 0 and not inactivity_notified:
                inactive_for = int(time.time() - last_activity_ts)
                if inactive_for >= inactivity_after_seconds:
                    inactivity_notified = True
                    if on_inactive is not None:
                        on_inactive(inactive_for)

            now = time.time()
            if on_heartbeat is not None and (
                STOP_EVENT.is_set() or now - last_heartbeat_ts >= 30.0
            ):
                last_heartbeat_ts = now
                on_heartbeat(proc.pid, inactivity_notified)

        stdout_text, _ = proc.communicate()
        final_message = stdout_text or ""
        log_file.write(f"[{utcnow_iso()}] EXIT CODE: {proc.returncode}\n")
        log_file.flush()
    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as log_file:
            log_file.seek(start_offset)
            log_excerpt = log_file.read()
    except Exception:
        log_excerpt = ""
    return proc.returncode, final_message, log_excerpt


def project_worker(runtime: RuntimeConfig, project: ProjectConfig, root: Path, control_root: Path) -> None:
    name_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", project.name)
    project_root = root / name_slug
    logs_dir = project_root / "logs"
    state_dir = project_root / "state"
    ensure_dir(logs_dir)
    ensure_dir(state_dir)

    state_path = state_dir / "status.json"
    last_message_path = state_dir / "last_message.md"
    log_path = logs_dir / "codex.log"
    control_path = control_root / f"control.{name_slug}.json"

    pass_num = 0
    prior_state: dict[str, Any] = {}
    if state_path.exists():
        try:
            prior_state = json.loads(read_text(state_path))
            pass_num = int(prior_state.get("pass_num", 0))
        except Exception:
            prior_state = {}

    while not STOP_EVENT.is_set():
        if project.max_passes and pass_num >= project.max_passes:
            echo(f"[{project.name}] reached max_passes={project.max_passes}; stopping.")
            write_json(
                state_path,
                build_state_payload(
                    runtime,
                    project,
                    prior_state.get("phase"),
                    pass_num,
                    STATE_MAX_PASSES,
                    prior_state=prior_state,
                    last_status=prior_state.get("last_status"),
                    status_detail=f"Reached max_passes={project.max_passes}.",
                    finished_at=utcnow_iso(),
                    active_codex_pid=None,
                    last_message_file=str(last_message_path),
                    log_file=str(log_path),
                ),
            )
            return

        should_resume = False
        retry_phase = prior_state.get("retry_phase") if prior_state else None
        resumable_statuses = {STATUS_CONTINUE, STATUS_UNKNOWN, STATUS_INTERRUPTED, STATUS_RATE_LIMIT_WAIT, "RUNNING"}
        resumable_states = {STATE_RUNNING, STATE_RATE_LIMIT_WAIT, STATE_PAUSED, STATE_STOPPED, STATE_FORCE_STOPPED}
        if retry_phase == "initial":
            should_resume = False
        elif retry_phase == "resume":
            should_resume = True
        elif pass_num > 0 and (
            prior_state.get("last_status") in resumable_statuses or prior_state.get("state_kind") in resumable_states
        ):
            should_resume = True
        elif project.resume_existing and (
            prior_state.get("last_status") in resumable_statuses
            or prior_state.get("state_kind") in resumable_states
        ):
            should_resume = True

        base_args = build_base_exec_args(runtime, project)
        current_followup_prompt = project.followup_prompt or runtime.default_followup_prompt
        if should_resume:
            cmd = base_args + ["resume", "--last", current_followup_prompt]
            phase = "resume"
        else:
            cmd = base_args + [project.prompt]
            phase = "initial"

        pass_num += 1
        echo(f"[{project.name}] pass {pass_num} ({phase}) starting")
        pass_started_at = utcnow_iso()

        def on_codex_start(pid: int) -> None:
            write_json(
                state_path,
                build_state_payload(
                    runtime,
                    project,
                    phase,
                    pass_num,
                    STATE_RUNNING,
                    prior_state=prior_state,
                    last_status="RUNNING",
                    status_detail="Codex pass is running.",
                    command=cmd,
                    pass_started_at=pass_started_at,
                    active_codex_pid=pid,
                    last_message_file=str(last_message_path),
                    log_file=str(log_path),
                ),
            )

        def on_inactive(inactive_for: int) -> None:
            write_json(
                state_path,
                build_state_payload(
                    runtime,
                    project,
                    phase,
                    pass_num,
                    STATE_INACTIVE,
                    prior_state=prior_state,
                    last_status="RUNNING",
                    status_detail=f"No log activity for {inactive_for} seconds.",
                    command=cmd,
                    pass_started_at=pass_started_at,
                    active_codex_pid=load_json_file(state_path).get("active_codex_pid"),
                    inactivity_detected_at=utcnow_iso(),
                    inactivity_seconds=inactive_for,
                    last_message_file=str(last_message_path),
                    log_file=str(log_path),
                ),
            )
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="inactivity",
                project=project,
                title=f"Continuum inactive: {project.name}",
                message=f"No Codex log activity for {inactive_for // 60 if inactive_for >= 60 else inactive_for}{'m' if inactive_for >= 60 else 's'}.",
                severity="warn",
                inactivity_seconds=inactive_for,
                phase=phase,
                pass_num=pass_num,
            )

        def on_activity_resumed() -> None:
            write_json(
                state_path,
                build_state_payload(
                    runtime,
                    project,
                    phase,
                    pass_num,
                    STATE_RUNNING,
                    prior_state=prior_state,
                    last_status="RUNNING",
                    status_detail="Codex pass is running.",
                    command=cmd,
                    pass_started_at=pass_started_at,
                    active_codex_pid=load_json_file(state_path).get("active_codex_pid"),
                    inactivity_cleared_at=utcnow_iso(),
                    last_message_file=str(last_message_path),
                    log_file=str(log_path),
                ),
            )
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="activity_resumed",
                project=project,
                title=f"Continuum active again: {project.name}",
                message="Codex log activity resumed.",
                severity="info",
                phase=phase,
                pass_num=pass_num,
            )

        def on_heartbeat(pid: int, inactive: bool) -> None:
            current_state = load_json_file(state_path)
            state_kind = STATE_INACTIVE if inactive else STATE_RUNNING
            status_detail = "Codex pass is running."
            if STOP_EVENT.is_set():
                status_detail = "Stop requested; waiting for the current pass to finish."
            elif current_state.get("state_kind") == STATE_INACTIVE:
                status_detail = str(current_state.get("status_detail") or "No log activity detected.")

            payload = build_state_payload(
                runtime,
                project,
                phase,
                pass_num,
                state_kind,
                prior_state=prior_state,
                last_status="RUNNING",
                status_detail=status_detail,
                command=cmd,
                pass_started_at=pass_started_at,
                active_codex_pid=pid,
                last_message_file=str(last_message_path),
                log_file=str(log_path),
            )
            for key in (
                "control_action",
                "control_requested_at",
                "control_acknowledged_at",
                "inactivity_detected_at",
                "inactivity_seconds",
                "inactivity_cleared_at",
            ):
                if key in current_state:
                    payload[key] = current_state[key]
            if STOP_EVENT.is_set():
                payload["control_action"] = "stop_after_pass"
            write_json(state_path, payload)

        exit_code, final_message, log_excerpt = run_codex_command(
            cmd,
            log_path,
            on_start=on_codex_start,
            inactivity_after_seconds=runtime.inactivity_notify_after_seconds,
            on_inactive=on_inactive,
            on_activity_resumed=on_activity_resumed,
            on_heartbeat=on_heartbeat,
        )
        write_text(last_message_path, final_message)
        parsed = parse_status(final_message)

        finished_at = utcnow_iso()
        state_payload: dict[str, Any] = build_state_payload(
            runtime,
            project,
            phase,
            pass_num,
            STATE_RUNNING,
            prior_state=prior_state,
            last_status=parsed.kind,
            status_detail=parsed.detail,
            exit_code=exit_code,
            pass_started_at=pass_started_at,
            finished_at=finished_at,
            active_codex_pid=None,
            last_message_file=str(last_message_path),
            log_file=str(log_path),
        )

        write_json(state_path, state_payload)

        if STOP_EVENT.is_set():
            stopped_state = {
                **state_payload,
                "state_kind": STATE_STOPPED,
                "last_status": parsed.kind if parsed.kind != STATUS_UNKNOWN else STATUS_INTERRUPTED,
                "status_detail": "Stop requested after the current pass finished.",
                "control_action": "stop_after_pass",
            }
            write_json(state_path, stopped_state)
            echo(f"[{project.name}] stopped after current pass")
            return

        if exit_code != 0:
            failure_signal = classify_failure_signal(f"{final_message}\n{log_excerpt}")
            if failure_signal and failure_signal.kind == "quota_exhausted":
                msg = failure_signal.detail or "Quota or credits exhausted"
                state_payload.update(
                    {
                        "state_kind": STATE_BLOCKED,
                        "last_status": STATUS_BLOCKED,
                        "status_detail": msg,
                        "failure_kind": "quota_exhausted",
                        "retry_phase": phase,
                    }
                )
                write_json(state_path, state_payload)
                echo(f"[{project.name}] BLOCKED: {msg}")
                emit_runtime_notification(
                    runtime,
                    control_root,
                    event_type="quota_blocked",
                    project=project,
                    title=f"Continuum quota blocked: {project.name}",
                    message=msg[:240],
                    severity="error",
                    phase=phase,
                    pass_num=pass_num,
                )
                return

            if failure_signal and failure_signal.kind == "rate_limited":
                retry_count = int(prior_state.get("rate_limit_retry_count", 0)) + 1 if prior_state else 1
                msg = failure_signal.detail or "Temporarily rate limited or service overloaded"
                if retry_count <= runtime.max_rate_limit_retries:
                    state_payload.update(
                        {
                            "state_kind": STATE_RATE_LIMIT_WAIT,
                            "last_status": STATUS_RATE_LIMIT_WAIT,
                            "status_detail": msg,
                            "failure_kind": "rate_limited",
                            "rate_limit_retry_count": retry_count,
                            "retry_after_seconds": runtime.rate_limit_retry_seconds,
                            "retry_after_at": datetime.fromtimestamp(
                                time.time() + runtime.rate_limit_retry_seconds,
                                tz=timezone.utc,
                            ).isoformat(),
                            "retry_phase": phase,
                        }
                    )
                    write_json(state_path, state_payload)
                    echo(
                        f"[{project.name}] rate limited or overloaded; retry "
                        f"{retry_count}/{runtime.max_rate_limit_retries} in "
                        f"{runtime.rate_limit_retry_seconds}s"
                    )
                    emit_runtime_notification(
                        runtime,
                        control_root,
                        event_type="rate_limited",
                        project=project,
                        title=f"Continuum waiting: {project.name}",
                        message=f"Retrying after rate limit in {runtime.rate_limit_retry_seconds}s",
                        severity="warn",
                        phase=phase,
                        pass_num=pass_num,
                        retry_count=retry_count,
                        retry_after_seconds=runtime.rate_limit_retry_seconds,
                    )
                    wait_result = sleep_with_control(runtime.rate_limit_retry_seconds, control_path)
                    if wait_result == "pause_requested":
                        pause_request = consume_control_action(control_path, CONTROL_ACTION_PAUSE) or {}
                        paused_state = {
                            **state_payload,
                            "state_kind": STATE_PAUSED,
                            "status_detail": "Paused while waiting to retry after a rate limit.",
                            "control_action": CONTROL_ACTION_PAUSE,
                            "control_requested_at": pause_request.get("requested_at"),
                            "control_acknowledged_at": utcnow_iso(),
                        }
                        write_json(state_path, paused_state)
                        echo(f"[{project.name}] paused while waiting after rate limit")
                        emit_runtime_notification(
                            runtime,
                            control_root,
                            event_type="paused",
                            project=project,
                            title=f"Continuum paused: {project.name}",
                            message="Paused while waiting to retry after a rate limit.",
                            severity="info",
                            phase=phase,
                            pass_num=pass_num,
                        )
                        return
                    prior_state = state_payload
                    if wait_result != "completed":
                        stopped_state = {
                            **state_payload,
                            "state_kind": STATE_STOPPED,
                            "last_status": STATUS_INTERRUPTED,
                            "status_detail": "Stop requested while waiting to retry after a rate limit.",
                            "control_action": "stop_after_pass",
                        }
                        write_json(state_path, stopped_state)
                        return
                    continue

                state_payload.update(
                    {
                        "state_kind": STATE_BLOCKED,
                        "last_status": STATUS_BLOCKED,
                        "status_detail": (
                            f"Rate limited too many times ({retry_count - 1} retries): {msg}"
                        ),
                        "failure_kind": "rate_limited",
                        "rate_limit_retry_count": retry_count,
                        "retry_phase": phase,
                    }
                )
                write_json(state_path, state_payload)
                echo(f"[{project.name}] BLOCKED: rate limited too many times")
                emit_runtime_notification(
                    runtime,
                    control_root,
                    event_type="rate_limit_blocked",
                    project=project,
                    title=f"Continuum blocked: {project.name}",
                    message="Rate limited too many times",
                    severity="error",
                    phase=phase,
                    pass_num=pass_num,
                    retry_count=retry_count,
                )
                return

            state_payload.update(
                {
                    "state_kind": STATE_FAILED,
                    "last_status": STATUS_FAILED,
                    "status_detail": f"Codex exited non-zero ({exit_code})",
                    "failure_kind": "nonzero_exit",
                    "retry_phase": phase,
                }
            )
            write_json(state_path, state_payload)
            echo(f"[{project.name}] Codex exited non-zero ({exit_code}); stopping")
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="failed",
                project=project,
                title=f"Continuum failed: {project.name}",
                message=f"Exit code {exit_code}",
                severity="error",
                phase=phase,
                pass_num=pass_num,
                exit_code=exit_code,
            )
            return

        if parsed.kind == STATUS_CONTINUE:
            pause_request = consume_control_action(control_path, CONTROL_ACTION_PAUSE)
            if pause_request is not None:
                paused_state = {
                    **state_payload,
                    "state_kind": STATE_PAUSED,
                    "last_status": STATUS_CONTINUE,
                    "status_detail": "Pause requested after the current pass.",
                    "control_action": CONTROL_ACTION_PAUSE,
                    "control_requested_at": pause_request.get("requested_at"),
                    "control_acknowledged_at": utcnow_iso(),
                }
                write_json(state_path, paused_state)
                echo(f"[{project.name}] paused after current pass")
                emit_runtime_notification(
                    runtime,
                    control_root,
                    event_type="paused",
                    project=project,
                    title=f"Continuum paused: {project.name}",
                    message="Paused after the current pass finished.",
                    severity="info",
                    phase=phase,
                    pass_num=pass_num,
                )
                return
            echo(f"[{project.name}] requested CONTINUE")
            state_payload.update({"state_kind": STATE_RUNNING})
            prior_state = state_payload
            continue

        if parsed.kind == STATUS_DONE:
            state_payload.update({"state_kind": STATE_DONE})
            write_json(state_path, state_payload)
            echo(f"[{project.name}] DONE")
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="done",
                project=project,
                title=f"Continuum done: {project.name}",
                message="Task completed",
                severity="info",
                phase=phase,
                pass_num=pass_num,
            )
            return

        if parsed.kind == STATUS_BLOCKED:
            msg = parsed.detail or "Blocked"
            state_payload.update({"state_kind": STATE_BLOCKED})
            write_json(state_path, state_payload)
            echo(f"[{project.name}] BLOCKED: {msg}")
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="blocked",
                project=project,
                title=f"Continuum blocked: {project.name}",
                message=msg[:240],
                severity="warn",
                phase=phase,
                pass_num=pass_num,
            )
            return

        # Unknown status: try exactly one corrective resume, then stop on the next unknown.
        previous_unknown_count = int(prior_state.get("unknown_count", 0)) if prior_state else 0
        unknown_count = previous_unknown_count + 1
        state_payload["unknown_count"] = unknown_count
        write_json(state_path, state_payload)

        pause_request = consume_control_action(control_path, CONTROL_ACTION_PAUSE)
        if pause_request is not None:
            paused_state = {
                **state_payload,
                "state_kind": STATE_PAUSED,
                "last_status": STATUS_UNKNOWN,
                "status_detail": "Pause requested after the current pass.",
                "control_action": CONTROL_ACTION_PAUSE,
                "control_requested_at": pause_request.get("requested_at"),
                "control_acknowledged_at": utcnow_iso(),
            }
            write_json(state_path, paused_state)
            echo(f"[{project.name}] paused after current pass")
            emit_runtime_notification(
                runtime,
                control_root,
                event_type="paused",
                project=project,
                title=f"Continuum paused: {project.name}",
                message="Paused after the current pass finished.",
                severity="info",
                phase=phase,
                pass_num=pass_num,
            )
            return

        if unknown_count <= 1:
            echo(f"[{project.name}] missing STATUS line; requesting a corrective follow-up")
            prior_state = {
                **state_payload,
                "unknown_count": unknown_count,
                "last_status": STATUS_UNKNOWN,
            }
            project.followup_prompt = (
                "Continue from your last checkpoint. Your previous reply did not end with the required status line. "
                "Do the next highest-value work, then end with exactly one status line: "
                "STATUS: CONTINUE, STATUS: DONE, or STATUS: BLOCKED: <reason>."
            )
            continue

        echo(f"[{project.name}] missing STATUS line twice; stopping")
        failed_state = {
            **state_payload,
            "state_kind": STATE_FAILED,
            "last_status": STATUS_UNKNOWN,
            "status_detail": "Missing STATUS line twice; manual review needed.",
            "failure_kind": "missing_status_line",
        }
        write_json(state_path, failed_state)
        emit_runtime_notification(
            runtime,
            control_root,
            event_type="needs_review",
            project=project,
            title=f"Continuum needs review: {project.name}",
            message="Missing STATUS line twice",
            severity="warn",
            phase=phase,
            pass_num=pass_num,
        )
        return

    if STOP_EVENT.is_set():
        stopped_state = build_state_payload(
            runtime,
            project,
            prior_state.get("phase"),
            pass_num,
            STATE_STOPPED,
            prior_state=prior_state,
            last_status=prior_state.get("last_status", STATUS_INTERRUPTED),
            status_detail="Stop requested by signal.",
            finished_at=utcnow_iso(),
            active_codex_pid=None,
            last_message_file=str(last_message_path),
            log_file=str(log_path),
        )
        write_json(state_path, stopped_state)


def install_signal_handlers() -> None:
    def handler(signum: int, _frame: Any) -> None:
        echo(f"Received signal {signum}; waiting for active Codex runs to finish.")
        STOP_EVENT.set()

    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python3 codex_supervisor.py /path/to/projects.json [project_name ...]", file=sys.stderr)
        return 2

    config_path = Path(argv[1]).expanduser().resolve()
    if not config_path.exists():
        print(f"Config file does not exist: {config_path}", file=sys.stderr)
        return 2

    runtime = load_config(config_path)
    try:
        select_projects(runtime, argv[2:])
    except SupervisorError as e:
        print(str(e), file=sys.stderr)
        return 2
    ensure_executable_exists(runtime.codex_bin)

    root = Path(runtime.supervisor_root).expanduser()
    if not root.is_absolute():
        root = (config_path.parent / root).resolve()
    ensure_dir(root)
    control_root = config_path.parent

    install_signal_handlers()

    threads: list[threading.Thread] = []
    for project in runtime.projects:
        if not project.enabled:
            continue
        project_path = Path(project.path).expanduser().resolve()
        if not project_path.exists():
            echo(f"[SKIP] {project.name}: path does not exist: {project_path}")
            continue
        project.path = str(project_path)
        t = threading.Thread(
            target=project_worker,
            args=(runtime, project, root, control_root),
            name=f"codex-{project.name}",
            daemon=False,
        )
        threads.append(t)
        t.start()

    if not threads:
        echo("No enabled projects to run.")
        return 1

    for t in threads:
        t.join()

    echo("All project workers finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
