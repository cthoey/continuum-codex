# Continuum for Codex

Continuum is an open-source control layer for long-running Codex CLI projects.

Use it when you find yourself repeatedly nudging the same Codex project forward with the same prompt, for example `Proceed`. Do not use it when the work still needs frequent human decisions, prompt reframing, or review after every small step.

The name refers to continuity across many Codex passes. See [CHANGELOG.md](CHANGELOG.md) for release history.

## What it does

- opt-in autonomous runs per project, not one global autonomous mode
- can run one or more autonomous projects simultaneously
- starts with `codex exec` and resumes with `codex exec resume --last`
- writes project-specific goals and status rules into project-local `AGENTS.md`
- keeps a durable project-local progress log in `docs/codex-progress.md`
- provides per-project start, pause, stop, stop-now, and restart controls
- supports explicit `paused`, `stopped`, `force-stopped`, `review-needed`, `rate-limited`, `blocked`, `failed`, and `done` runtime states
- records per-project logs and runtime state
- retries temporary rate limits and stops on surfaced hard quota exhaustion
- can be used in macOS and Linux environments
- uses built-in `caffeinate` sleep prevention on macOS
- can run under `launchctl` on macOS or `systemd --user` on Linux for a cleaner long-lived background runtime
- can expose project status and controls through [SwiftBar](https://github.com/cthoey/swiftbar-plugins)
- can emit local alerts, append a runner event log, call an external notification command, or POST a webhook payload
- can make milestone commits and pushes if your Codex rules allow Git commands
- can explicitly configure and show the effective model and reasoning effort for each project

## How it works

1. Put reusable Codex profiles in `~/.codex/config.toml`.
2. Run `continuum init` to create or refresh the runner and home config.
3. Run `continuum enable` with a project path and a long-term project goal.
4. Launch that project with `continuum start <name>` or `continuum service start <name>`.
5. Continuum keeps the project going in the same Codex thread until the project reports that it has achieved its goal, ran into a blocker, or needs to hand the work back for human review.

Only projects you explicitly enable become autonomous.

The stable home-level control path is `~/.config/continuum/config.toml` plus `~/continuum-runner`.

## Technical details

Continuum is a wrapper around documented Codex CLI features. It does not replace Codex's own
instruction system, session model, or sandboxing model.

- Continuum starts the first pass with [`codex exec`](https://developers.openai.com/codex/noninteractive) and continues the same Codex session with `codex exec resume --last`. That is the core continuation loop.
- Continuum stores project-specific operating instructions in project-root `AGENTS.md`. Codex reads `AGENTS.md` files before it starts work and layers global guidance with project-specific guidance according to its own instruction discovery rules. See the official [`AGENTS.md` guide](https://developers.openai.com/codex/guides/agents-md).
- Continuum keeps the status protocol project-local. Projects should use `STATUS: BLOCKED: human review needed: <reason>` when the next step depends on human judgment, playtesting, runtime observation, or choosing between multiple plausible behaviors. Continuum surfaces that as `review-needed` instead of a generic blocked state.
- Continuum expects reusable Codex defaults, such as model choice, reasoning effort, profiles, approval policy, and sandbox mode, to live in `~/.codex/config.toml`. A project can also override `model` and `reasoning_effort` explicitly in `projects.json` or through `continuum enable --model ... --reasoning-effort ...`. For Codex's own configuration precedence and trusted-project behavior, see [Config basics](https://developers.openai.com/codex/config-basic).
- Continuum does not require a Codex `Stop` hook. The continuation loop is managed externally by the runner, not by the interactive Codex hook system. If you already use Codex hooks for validation or prompting behavior, Continuum can coexist with them, but the autonomous runner does not depend on them. See the official [Hooks documentation](https://developers.openai.com/codex/hooks).
- Continuum keeps its own runner state in `~/continuum-runner/` or the configured runner root. That state includes `projects.json`, per-project logs, per-project `status.json`, restart markers, and the runner event log. Codex still keeps its own session/thread history separately.

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

Enable one project:

```bash
./continuum enable /absolute/path/to/project \
  --name my-project \
  --goal "The goal of this project is to ..." \
  --model gpt-5.4 \
  --reasoning-effort xhigh
```

If you omit `--model` or `--reasoning-effort`, Continuum resolves them from the selected Codex profile and your `~/.codex/config.toml`.

Launch it:

```bash
./continuum start my-project
```

Or use the service-managed path:

```bash
./continuum service install my-project
./continuum service start my-project
```

That is enough to start one autonomous project. For full setup walkthroughs, see [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md) or [LINUX-SINGLE-PROJECT-SETUP.md](LINUX-SINGLE-PROJECT-SETUP.md).

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

Ad hoc stop-as-soon-as-possible:

```bash
./continuum stop-now my-project
```

Pause after the current pass:

```bash
./continuum pause my-project
```

Compatibility alias for `stop-now`:

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

`continuum status` shows the effective profile, model, and reasoning effort for each project.

Tail the project log:

```bash
tail -f ~/continuum-runner/runtime/my-project/logs/codex.log
```

Inspect saved state:

```bash
cat ~/continuum-runner/runtime/my-project/state/status.json
cat ~/continuum-runner/runtime/my-project/state/last_message.md
```

Inspect the runner event log:

```bash
tail -f ~/continuum-runner/continuum-notify.log
```

If you use [SwiftBar](https://github.com/cthoey/swiftbar-plugins), enable the project once with `continuum enable` and then use the menu bar plugin to start, restart, `Stop after pass`, `Stop now`, inspect logs, and open the project state files.

## Testing

Run the integration suite from the project root:

```bash
python3 -m unittest discover -s tests -v
```

These tests exercise the real `continuum` CLI against temporary projects and runner directories, including enablement, service definition generation, pause and stop-now behavior, inactivity detection, and notification/state output.

## Operational notes

- Continuum is project-specific by design. Projects that are not in `projects.json` remain ordinary interactive Codex projects.
- The stable install target is the home-level pair `~/.config/continuum/config.toml` and `~/continuum-runner`. Other paths should be treated as implementation detail or development setup.
- The runner is plain Python and shell, so the core flow is not macOS-only.
- Continuum does not require the interactive Codex `Stop` hook. The supervisor path manages continuation itself.
- On macOS, both detached launches and service mode keep the machine awake while a worker is active. The detached path uses `caffeinate -is -w <supervisor-pid>`, and service mode does the same inside `service_runner.py`.
- Credits and quota handling are reactive, not predictive. Continuum does not know your remaining credits ahead of time; it only reacts to surfaced Codex failures.
- Temporary rate limits back off and retry. Surfaced hard quota exhaustion stops the worker and records the failure.
- Long-running passes with no new `codex.log` activity for `inactivity_notify_after_seconds` move into an `inactive` state and emit a notification event once.
- Detached launches use `nohup`, so you can close the launch terminal after the worker starts.
- Service mode is the cleaner long-lived runtime: `launchctl` on macOS and `systemd --user` on Linux.
- `continuum stop` is the graceful boundary action. It lets the current pass finish, then stops before the next pass starts.
- `continuum stop-now` is the emergency stop path. It first sends `TERM`, waits briefly, then escalates to `KILL` only if the worker is still running.
- `continuum pause` is a controlled boundary action: it lets the current pass finish, then stops before the next pass starts.
- `continuum force-stop` is kept as a compatibility alias for `continuum stop-now`.
- `continuum force-restart` remains the detached-mode emergency restart control and should be used only when the normal graceful controls are not enough.
- Notification delivery is configured in `projects.json`: `notify`, `notification_command`, `notification_webhook_url`, `notification_webhook_timeout_seconds`, and `inactivity_notify_after_seconds`.
- `notification_command` receives one extra argument containing the JSON event payload. `notification_webhook_url` gets the same payload as a simple HTTP POST.
- Milestone commits and pushes require Codex rules that allow `git add`, `git commit`, and `git push` outside the sandbox.

## Project layout

- [supervisor/](supervisor/): runner scripts, project enabler, example config
- [supervisor/service_runner.py](supervisor/service_runner.py): foreground wrapper for launchctl and systemd service mode
- [supervisor/continuum_notify.py](supervisor/continuum_notify.py): shared event log, local notifications, external command, and webhook delivery
- [supervisor/pause_project.sh](supervisor/pause_project.sh): request a pause after the current pass
- [supervisor/stop_now_project.sh](supervisor/stop_now_project.sh): stop one project as soon as possible, escalating from `TERM` to `KILL` only when needed
- [supervisor/force_stop_project.sh](supervisor/force_stop_project.sh): compatibility wrapper for `stop_now_project.sh`
- [supervisor/force_restart_project.sh](supervisor/force_restart_project.sh): detached-mode emergency restart
- [samples/](samples/): sample Codex config, AGENTS files, optional hook files
- [tests/](tests/): integration tests for the CLI, runner state model, and notifier flow
- [continuum](continuum): CLI entry point, starting with `continuum doctor`
- [scripts/install_home.py](scripts/install_home.py): writes `~/.config/continuum/config.toml` and a `~/continuum-runner` alias
- [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md): detailed setup guide
- [LINUX-SINGLE-PROJECT-SETUP.md](LINUX-SINGLE-PROJECT-SETUP.md): Linux single-project setup guide
- [RELEASE_NOTES_v0.1.0.md](RELEASE_NOTES_v0.1.0.md): first public release notes
