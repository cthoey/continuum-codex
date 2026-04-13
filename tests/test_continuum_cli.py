from __future__ import annotations

import json
import os
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTINUUM = REPO_ROOT / "continuum"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_codex_supervisor_module():
    supervisor_dir = REPO_ROOT / "supervisor"
    module_path = supervisor_dir / "codex_supervisor.py"
    module_name = "continuum_codex_supervisor"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(supervisor_dir))
    try:
        assert spec and spec.loader
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
        sys.path.pop(0)
    return module


class ContinuumCliIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory(prefix="continuum-tests.")
        self.root = Path(self.tmpdir.name)
        self.repo = self.root / "repo"
        self.runner = self.root / "runner"
        self.home_config = self.root / "continuum-config.toml"
        self.home_runner = self.root / "home-runner"
        self.config = self.runner / "projects.json"
        self.fake_codex = self.root / "fake-codex.sh"
        self.codex_config = self.root / "codex-config.toml"
        self.service_dir = self.root / "services"
        self.runtime_root = self.runner / "runtime"
        self.project_name = "test-project"
        self.project_slug = "test-project"
        self.status_path = self.runtime_root / self.project_slug / "state" / "status.json"
        self.notify_log = self.runner / "continuum-notify.log"

        self.repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(self.repo)], check=True, stdout=subprocess.DEVNULL)
        self.codex_config.write_text(
            textwrap.dedent(
                """
                model = "gpt-5.4"
                model_reasoning_effort = "high"

                [profiles.autonomous]
                model = "gpt-5.4-mini"
                model_reasoning_effort = "medium"
                approval_policy = "never"
                sandbox_mode = "workspace-write"

                [profiles.autonomous.sandbox_workspace_write]
                network_access = false
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env["CONTINUUM_CODEX_CONFIG"] = str(self.codex_config)
        self.addCleanup(self._cleanup_background)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _cleanup_background(self) -> None:
        if not self.runner.exists():
            return
        for cmd in (
            ["force-stop", self.project_name],
            ["stop", self.project_name],
        ):
            subprocess.run(
                [
                    str(CONTINUUM),
                    *cmd,
                    "--runner-root",
                    str(self.runner),
                    "--home-config",
                    str(self.home_config),
                    "--config",
                    str(self.config),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                text=True,
                env=self.env,
            )

    def continuum(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [str(CONTINUUM), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
            env=self.env,
        )
        if check and completed.returncode != 0:
            self.fail(f"Command failed ({completed.returncode}): {' '.join(args)}\n{completed.stdout}")
        return completed

    def write_fake_codex(self, body: str) -> None:
        script = "#!/usr/bin/env bash\nset -euo pipefail\n" + body
        self.fake_codex.write_text(script, encoding="utf-8")
        self.fake_codex.chmod(0o755)

    def init_runner(self) -> None:
        self.continuum(
            "init",
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--home-runner-link",
            str(self.home_runner),
        )

    def write_single_project_config(self, *, inactivity_notify_after_seconds: int = 1800) -> None:
        payload = load_json(self.config)
        payload["codex_bin"] = str(self.fake_codex)
        payload["notify"] = False
        payload["inactivity_notify_after_seconds"] = inactivity_notify_after_seconds
        payload["projects"] = [
            {
                "name": self.project_name,
                "path": str(self.repo),
                "prompt": "Do test work.",
                "profile": None,
                "max_passes": 0,
                "resume_existing": True,
                "enabled": True,
                "extra_args": [],
            }
        ]
        self.config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def wait_for(self, predicate, timeout: float = 15.0, interval: float = 0.2) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if predicate():
                return
            time.sleep(interval)
        self.fail("Timed out waiting for test condition")

    def status_json(self) -> dict:
        output = self.continuum(
            "status",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
            "--json",
        )
        payload = json.loads(output.stdout)
        self.assertEqual(len(payload["projects"]), 1)
        return payload["projects"][0]

    def test_enable_and_service_install(self) -> None:
        self.init_runner()
        self.continuum(
            "enable",
            str(self.repo),
            "--name",
            self.project_name,
            "--goal",
            "The goal of this project is to validate the Continuum CLI.",
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
        )

        payload = load_json(self.config)
        self.assertEqual(payload["projects"][0]["name"], self.project_name)
        agents_text = (self.repo / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("STATUS: BLOCKED: human review needed:", agents_text)
        self.assertTrue((self.repo / "docs" / "codex-progress.md").exists())

        self.continuum(
            "service",
            "install",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--service-dir",
            str(self.service_dir),
            "--no-manager",
        )

        if shutil.which("launchctl") and sys_platform() == "darwin":
            service_file = self.service_dir / "dev.continuum.codex.test-project.plist"
        else:
            service_file = self.service_dir / "continuum-test-project.service"
        self.assertTrue(service_file.exists())
        contents = service_file.read_text(encoding="utf-8")
        self.assertIn("service_runner.py", contents)
        self.assertIn(self.project_name, contents)

    def test_enable_and_status_show_effective_model_and_reasoning(self) -> None:
        self.init_runner()
        self.continuum(
            "enable",
            str(self.repo),
            "--name",
            self.project_name,
            "--goal",
            "The goal of this project is to validate explicit model settings.",
            "--model",
            "gpt-5.4",
            "--reasoning-effort",
            "xhigh",
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
        )

        payload = load_json(self.config)
        project = payload["projects"][0]
        self.assertEqual(project["model"], "gpt-5.4")
        self.assertEqual(project["reasoning_effort"], "xhigh")

        status = self.status_json()
        self.assertEqual(status.get("effective_model"), "gpt-5.4")
        self.assertEqual(status.get("effective_reasoning_effort"), "xhigh")

        self.continuum(
            "enable",
            str(self.repo),
            "--name",
            self.project_name,
            "--goal",
            "The goal of this project is to validate profile-derived model settings.",
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
        )
        payload = load_json(self.config)
        project = payload["projects"][0]
        project.pop("model", None)
        project.pop("reasoning_effort", None)
        self.config.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        status = self.status_json()
        self.assertEqual(status.get("effective_model"), "gpt-5.4-mini")
        self.assertEqual(status.get("effective_reasoning_effort"), "medium")

    def test_pause_and_stop_now_update_runtime_state(self) -> None:
        self.init_runner()
        self.write_fake_codex(
            textwrap.dedent(
                """
                repo=""
                args=("$@")
                for ((i=0; i<${#args[@]}; i++)); do
                  if [[ "${args[$i]}" == "-C" ]]; then
                    repo="${args[$((i+1))]}"
                    break
                  fi
                done
                count_file="$repo/.fake-codex-count"
                count=0
                if [[ -f "$count_file" ]]; then
                  count=$(cat "$count_file")
                fi
                count=$((count + 1))
                printf '%s' "$count" > "$count_file"
                sleep 4
                printf 'chunk %s\\nSTATUS: CONTINUE\\n' "$count"
                """
            ).strip()
            + "\n"
        )
        self.write_single_project_config()

        self.continuum(
            "start",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )
        self.wait_for(lambda: self.status_path.exists())
        self.wait_for(lambda: self.status_json().get("overall_status") == "running")

        self.continuum(
            "pause",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
        )
        self.wait_for(lambda: self.status_json().get("overall_status") == "pause:requested")
        self.wait_for(lambda: self.status_json().get("overall_status") == "paused", timeout=12.0)

        self.write_fake_codex(
            textwrap.dedent(
                """
                sleep 30
                printf 'late output\\nSTATUS: CONTINUE\\n'
                """
            ).strip()
            + "\n"
        )
        self.continuum(
            "start",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )
        self.wait_for(lambda: self.status_json().get("overall_status") == "running")
        self.continuum(
            "stop-now",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )
        self.wait_for(lambda: self.status_json().get("overall_status") == "force-stopped")
        status = self.status_json()
        self.assertEqual(status.get("state_kind"), "force_stopped")
        self.assertEqual(status.get("last_status"), "INTERRUPTED")

    def test_stop_after_pass_updates_runtime_state(self) -> None:
        self.init_runner()
        self.write_fake_codex(
            textwrap.dedent(
                """
                sleep 8
                printf 'chunk\\nSTATUS: CONTINUE\\n'
                """
            ).strip()
            + "\n"
        )
        self.write_single_project_config()

        self.continuum(
            "start",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )
        self.wait_for(lambda: self.status_json().get("overall_status") == "running")

        self.continuum(
            "stop",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
        )

        control_path = self.runner / "control.test-project.json"
        self.wait_for(lambda: control_path.exists())
        control_payload = load_json(control_path)
        self.assertEqual(control_payload.get("action"), "stop_after_pass")
        self.wait_for(lambda: self.status_json().get("overall_status") == "stopped", timeout=12.0)

    def test_inactivity_emits_event_and_state(self) -> None:
        self.init_runner()
        self.write_fake_codex(
            textwrap.dedent(
                """
                sleep 5
                printf 'done\\nSTATUS: DONE\\n'
                """
            ).strip()
            + "\n"
        )
        self.write_single_project_config(inactivity_notify_after_seconds=2)

        self.continuum(
            "start",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )

        self.wait_for(lambda: self.status_json().get("overall_status") == "inactive", timeout=10.0)
        self.wait_for(lambda: self.notify_log.exists(), timeout=10.0)
        contents = self.notify_log.read_text(encoding="utf-8")
        self.assertIn('"event_type": "inactivity"', contents)

    def test_human_review_needed_is_a_distinct_runtime_state(self) -> None:
        self.init_runner()
        self.write_fake_codex(
            textwrap.dedent(
                """
                printf 'investigated\\nSTATUS: BLOCKED: human review needed: gameplay feel needs live verification\\n'
                """
            ).strip()
            + "\n"
        )
        self.write_single_project_config()

        self.continuum(
            "start",
            self.project_name,
            "--runner-root",
            str(self.runner),
            "--home-config",
            str(self.home_config),
            "--config",
            str(self.config),
        )

        self.wait_for(lambda: self.status_json().get("overall_status") == "review-needed", timeout=10.0)
        status = self.status_json()
        self.assertEqual(status.get("state_kind"), "review_needed")
        self.assertEqual(status.get("last_status"), "BLOCKED")
        self.assertEqual(status.get("blocked_reason_kind"), "human_review_needed")

    def test_status_prefers_running_when_restart_timed_out_but_worker_is_live(self) -> None:
        self.init_runner()
        self.write_single_project_config()

        state_dir = self.runtime_root / self.project_slug / "state"
        log_dir = self.runtime_root / self.project_slug / "logs"
        state_dir.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_path = log_dir / "codex.log"
        log_path.write_text("still working\n", encoding="utf-8")
        now = time.time()
        os.utime(log_path, (now, now))

        state_payload = {
            "state_version": 2,
            "project": self.project_name,
            "updated_at": "2026-04-02T12:00:00+00:00",
            "phase": "initial",
            "pass_num": 1,
            "state_kind": "running",
            "path": str(self.repo),
            "profile": None,
            "started_at": "2026-04-02T12:00:00+00:00",
            "pass_started_at": "2026-04-02T12:00:00+00:00",
            "last_status": "RUNNING",
            "status_detail": "Codex pass is running.",
            "active_codex_pid": 999999,
        }
        self.status_path.write_text(json.dumps(state_payload, indent=2) + "\n", encoding="utf-8")

        restart_state = {
            "project": self.project_name,
            "phase": "timed_out",
            "detail": "Graceful restart timed out.",
        }
        (self.runner / f"restart.{self.project_slug}.json").write_text(
            json.dumps(restart_state, indent=2) + "\n",
            encoding="utf-8",
        )

        status = self.status_json()
        self.assertEqual(status.get("restart_phase"), "timed_out")
        self.assertEqual(status.get("overall_status"), "running")


class ContinuumSupervisorUnitTests(unittest.TestCase):
    def test_usage_limit_message_is_classified_as_quota(self) -> None:
        module = load_codex_supervisor_module()
        signal = module.classify_failure_signal(
            "ERROR: You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage "
            "to purchase more credits or try again at Apr 8th, 2026 3:51 AM."
        )
        self.assertIsNotNone(signal)
        self.assertEqual(signal.kind, "quota_exhausted")

    def test_supervisor_self_heals_missing_caffeinate_pidfile(self) -> None:
        module = load_codex_supervisor_module()
        with tempfile.TemporaryDirectory(prefix="continuum-caffeinate.") as tmp:
            control_root = Path(tmp)
            fake_proc = mock.Mock()
            fake_proc.pid = 54321
            fake_proc.poll.return_value = None

            module.CAFFEINATE_PROCESS = None
            module.CAFFEINATE_PIDFILE = None
            module.CAFFEINATE_EXPECTED_PID = None

            with (
                mock.patch.object(module.platform, "system", return_value="Darwin"),
                mock.patch.object(module.shutil, "which", return_value="/usr/bin/caffeinate"),
                mock.patch.object(module.time, "sleep"),
                mock.patch.object(module.os, "getpid", return_value=11111),
                mock.patch.object(module, "_pid_is_running", return_value=False),
                mock.patch.object(module.subprocess, "Popen", return_value=fake_proc) as popen,
            ):
                module.ensure_supervisor_caffeinate(
                    control_root,
                    ["test-project"],
                    startup_grace_seconds=0,
                )

            pidfile = control_root / "caffeinate.test-project.pid"
            self.assertTrue(pidfile.exists())
            self.assertEqual(pidfile.read_text(encoding="utf-8").strip(), "54321")
            popen.assert_called_once_with(
                ["caffeinate", "-is", "-w", "11111"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )


def sys_platform() -> str:
    import sys

    return sys.platform


if __name__ == "__main__":
    unittest.main(verbosity=2)
