# Continuum for Codex

Continuum keeps long-running Codex CLI projects moving.

Use it when you keep nudging the same repo forward with "continue" and the project mostly needs continuity, not constant judgment. Do not use it when the work still needs frequent human decisions, prompt reframing, or review after every small step.

The name is literal: Continuum exists to preserve continuity across many Codex passes.

Current release: `v0.1.0`. See [CHANGELOG.md](CHANGELOG.md).

## What it does

- opt-in autonomous runs per repo, not one global autonomous mode
- starts with `codex exec` and resumes with `codex exec resume --last`
- writes project-specific goals and status rules into repo-local `AGENTS.md`
- keeps a durable repo-local progress log in `docs/codex-progress.md`
- launches, stops, and gracefully restarts one project at a time
- supports explicit `paused`, `stopped`, `force-stopped`, `rate-limited`, `blocked`, `failed`, and `done` runtime states
- records per-project logs and runtime state
- retries temporary rate limits and stops on surfaced hard quota exhaustion
- works on Unix-like systems, with built-in `caffeinate` sleep prevention on macOS
- can run under `launchctl` on macOS or `systemd --user` on Linux for a cleaner long-lived background runtime
- can expose project status and controls through SwiftBar
- can make milestone commits and pushes if your Codex rules allow Git commands

## How it works

1. Put reusable Codex profiles in `~/.codex/config.toml`.
2. Run `continuum init` to create or refresh the runner and home config.
3. Run `continuum enable` with a repo path and a long-term project goal.
4. Launch that project with `continuum start <name>` or `continuum service start <name>`.
5. Continuum keeps resuming the same Codex thread until the model ends with `STATUS: DONE` or `STATUS: BLOCKED: ...`.

Only repos you explicitly enable become autonomous.

## Quick start

Install Codex CLI, log in once, and create a runner:

```bash
git clone git@github.com:cthoey/continuum-codex.git
cd continuum-codex

brew install codex
codex login

mkdir -p ~/.codex ~/.codex/rules
cp samples/config.toml.sample ~/.codex/config.toml
cp samples/global-AGENTS.md.sample ~/.codex/AGENTS.md

cat >> ~/.codex/rules/default.rules <<'EOF'
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "push"], decision="allow")
EOF

./continuum init --runner-root ~/continuum-runner

./continuum doctor
```

Enable one repo:

```bash
./continuum enable /absolute/path/to/project \
  --name my-project \
  --goal "The goal of this project is to ..."
```

Launch it:

```bash
./continuum start my-project
```

Or use the service-managed path:

```bash
./continuum service install my-project
./continuum service start my-project
```

That is enough to start one autonomous project. For the full from-scratch walkthrough, see [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md).

## Day-to-day commands

Ad hoc detached launch:

```bash
./continuum start my-project
```

Ad hoc graceful restart:

```bash
./continuum restart my-project
```

Ad hoc graceful stop:

```bash
./continuum stop my-project
```

Pause after the current pass:

```bash
./continuum pause my-project
```

Detached-mode force stop:

```bash
./continuum force-stop my-project
```

Detached-mode force restart:

```bash
./continuum force-restart my-project
```

Install service mode:

```bash
./continuum service install my-project
```

Start through `launchctl` or `systemd --user`:

```bash
./continuum service start my-project
```

Service status:

```bash
./continuum service status
./continuum service status my-project
```

Service restart:

```bash
./continuum service restart my-project
```

Service stop:

```bash
./continuum service stop my-project
```

Check the overall install:

```bash
./continuum doctor
```

Inspect runner state:

```bash
./continuum status
./continuum status my-project
```

Tail the project log:

```bash
tail -f ~/continuum-runner/runtime/my-project/logs/codex.log
```

Inspect saved state:

```bash
cat ~/continuum-runner/runtime/my-project/state/status.json
cat ~/continuum-runner/runtime/my-project/state/last_message.md
```

If you use SwiftBar, enable the project once with `continuum enable` and then use the menu bar plugin to start, stop, and restart it.

## Operational notes

- Continuum is project-specific by design. Repos that are not in `projects.json` remain ordinary interactive Codex repos.
- The runner is plain Python and shell, so the core flow is not macOS-only.
- On macOS, both detached launches and service mode keep the machine awake while a worker is active. The detached path uses `caffeinate -is -w <supervisor-pid>`, and service mode does the same inside `service_runner.py`.
- Credits and quota handling are reactive, not predictive. Continuum does not know your remaining credits ahead of time; it only reacts to surfaced Codex failures.
- Temporary rate limits back off and retry. Surfaced hard quota exhaustion stops the worker and records the failure.
- Detached launches use `nohup`, so you can close the launch terminal after the worker starts.
- Service mode is the cleaner long-lived runtime: `launchctl` on macOS and `systemd --user` on Linux.
- `continuum pause` is a controlled boundary action: it lets the current pass finish, then stops before the next pass starts.
- `continuum force-stop` and `continuum force-restart` are detached-mode emergency controls. They immediately kill the active Codex subprocess and should be used only when the normal graceful controls are not enough.
- Milestone commits and pushes require Codex rules that allow `git add`, `git commit`, and `git push` outside the sandbox.
- The supervisor path does not require the interactive Stop hook.

## Repository layout

- [supervisor/](supervisor/): runner scripts, project enabler, example config
- [supervisor/service_runner.py](supervisor/service_runner.py): foreground wrapper for launchctl and systemd service mode
- [supervisor/pause_project.sh](supervisor/pause_project.sh): request a pause after the current pass
- [supervisor/force_stop_project.sh](supervisor/force_stop_project.sh): detached-mode emergency stop
- [supervisor/force_restart_project.sh](supervisor/force_restart_project.sh): detached-mode emergency restart
- [samples/](samples/): sample Codex config, AGENTS files, optional hook files
- [continuum](continuum): CLI entry point, starting with `continuum doctor`
- [scripts/install_home.py](scripts/install_home.py): writes `~/.config/continuum/config.toml` and a `~/continuum-runner` alias
- [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md): detailed setup guide
- [RELEASE_NOTES_v0.1.0.md](RELEASE_NOTES_v0.1.0.md): first public release notes
