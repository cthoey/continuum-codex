from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import time
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTINUUM = REPO_ROOT / "continuum"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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
        self.service_dir = self.root / "services"
        self.runtime_root = self.runner / "runtime"
        self.project_name = "test-project"
        self.project_slug = "test-project"
        self.status_path = self.runtime_root / self.project_slug / "state" / "status.json"
        self.notify_log = self.runner / "continuum-notify.log"

        self.repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", str(self.repo)], check=True, stdout=subprocess.DEVNULL)
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
            )

    def continuum(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [str(CONTINUUM), *args],
            cwd=REPO_ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
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
        self.assertTrue((self.repo / "AGENTS.md").exists())
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


def sys_platform() -> str:
    import sys

    return sys.platform


if __name__ == "__main__":
    unittest.main(verbosity=2)
