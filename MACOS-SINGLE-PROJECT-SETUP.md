# Continuum for Codex: macOS Single-Project Setup

Continuum is an open-source control layer for long-running Codex CLI projects.

Use this setup when you find yourself repeatedly nudging the same Codex project forward with the same prompt, for example `Proceed`. Do not use it when the work still needs frequent human decisions, prompt reframing, or review after every small step.

This guide enables exactly one project for autonomous work. Other projects on the machine stay normal interactive Codex projects unless you opt them in later.

This guide is macOS-specific because it uses Homebrew and the built-in `caffeinate` integration. The runner itself is plain Python and shell, and it can also be used in Linux environments with Linux-appropriate install and sleep-management choices.

## Requirements

- macOS
- Codex CLI access
- a Git-based project you want to run autonomously
- Python 3

This guide assumes the Continuum project is cloned locally:

```bash
git clone git@github.com:cthoey/continuum-codex.git
cd continuum-codex
export KIT_ROOT="$PWD"
```

It also assumes your target project has an absolute path:

```bash
export PROJECT_PATH="/absolute/path/to/project"
export PROJECT_NAME="my-project"
```

Sanity check the project path:

```bash
test -d "$PROJECT_PATH" && git -C "$PROJECT_PATH" rev-parse --is-inside-work-tree
```

Expected output:

```text
true
```

## 1. Write the project goal

Before you enable autonomy, write down the long-term goal in one or two sentences.

Example:

```text
The goal of this project is to decompile the Game Boy Advance game Mega Man Zero 3 for the eventual purpose of running it natively on macOS, Linux, and Windows.
```

Do not rely on Codex to infer the long-term goal from the project name alone.

## 2. Install and authenticate Codex CLI

```bash
brew install codex
codex login
```

If your installed version does not expose `codex login`, run `codex` and complete the login flow there.

## 3. Create the Codex config and Git rules

Create the config directories:

```bash
mkdir -p ~/.codex ~/.codex/rules
```

Copy the shipped samples:

```bash
cp "$KIT_ROOT/samples/config.toml.sample" ~/.codex/config.toml
cp "$KIT_ROOT/samples/global-AGENTS.md.sample" ~/.codex/AGENTS.md
```

Add Git rules for autonomous milestone commits and pushes:

```bash
cat >> ~/.codex/rules/default.rules <<'EOF'
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "push"], decision="allow")
EOF
```

Important defaults in the sample config:

- `approval_policy = "never"`
- `sandbox_mode = "workspace-write"`
- `sandbox_workspace_write.network_access = false`

That means unattended runs do not pause for approval. If a tool install or network action is blocked by the current environment, the project should record the blocker and continue with other useful work when possible.

Continuum does not require a Codex `Stop` hook for its continuation loop. The runner manages
continuation itself through `codex exec` and `codex exec resume --last`. Codex hooks are optional
and can still be used separately if you already rely on them for validation or prompt shaping.

## 4. Create the runner

Use the CLI to create or refresh the runner and install the home-level config:

```bash
"$KIT_ROOT/continuum" init --runner-root ~/continuum-runner
```

That creates:

- `~/.config/continuum/config.toml`
- `~/continuum-runner`

If you already have a live runner elsewhere, pass that path to `--runner-root` instead.

Run the built-in setup check:

```bash
"$KIT_ROOT/continuum" doctor
```

## 5. Enable the project

Use the CLI instead of hand-editing `projects.json`, project `AGENTS.md`, and `docs/codex-progress.md`:

```bash
"$KIT_ROOT/continuum" enable "$PROJECT_PATH" \
  --name "$PROJECT_NAME" \
  --goal "The goal of this project is to ..." \
  --model gpt-5.4 \
  --reasoning-effort xhigh
```

Both flags are optional. If you omit them, Continuum uses the model and reasoning defaults from the selected Codex profile in `~/.codex/config.toml`.

What the helper writes:

- a project entry in `projects.json`
- a managed autonomous block inside the project root `AGENTS.md`
- `docs/codex-progress.md` if it does not already exist

It also auto-detects common planning docs such as `README.md`, `docs/ROADMAP.md`, and `docs/EXECUTION_PLAN.md`.

## 6. Launch and monitor it

For a quick detached run:

```bash
"$KIT_ROOT/continuum" start "$PROJECT_NAME"
```

For the `launchctl`-managed service path, which is the cleaner long-lived background runtime on macOS:

```bash
"$KIT_ROOT/continuum" service install "$PROJECT_NAME"
"$KIT_ROOT/continuum" service start "$PROJECT_NAME"
```

Both paths write the same project logs and state files.

Tail the worker log:

```bash
tail -f ~/continuum-runner/runtime/"$PROJECT_NAME"/logs/codex.log
```

Inspect saved state:

```bash
"$KIT_ROOT/continuum" status "$PROJECT_NAME"
```

That status view includes the effective profile, model, and reasoning effort for the project.

Inspect the `launchctl` service definition and runtime state:

```bash
"$KIT_ROOT/continuum" service status "$PROJECT_NAME"
```

Tail the runner event log:

```bash
tail -f ~/continuum-runner/continuum-notify.log
```

What to expect:

- the first pass uses `codex exec`
- follow-up passes use `codex exec resume --last`
- `STATUS: CONTINUE` means keep looping
- `STATUS: DONE` or `STATUS: BLOCKED: ...` means stop

If you prefer [SwiftBar](https://github.com/cthoey/swiftbar-plugins), this is the point where it becomes useful. Project provisioning stays script-based, but day-to-day start, stop, restart, log inspection, and state-file access can happen from the menu bar once the project is enabled.

## 7. Restart or stop it cleanly

Graceful restart:

```bash
"$KIT_ROOT/continuum" restart "$PROJECT_NAME"
```

Graceful stop:

```bash
"$KIT_ROOT/continuum" stop "$PROJECT_NAME"
```

`restart_project.sh` and `stop_project.sh` do not force-kill the active `codex exec` pass. They wait for a clean boundary.

Stop as soon as possible:

```bash
"$KIT_ROOT/continuum" stop-now "$PROJECT_NAME"
```

Pause after the current pass:

```bash
"$KIT_ROOT/continuum" pause "$PROJECT_NAME"
```

Service-mode restart:

```bash
"$KIT_ROOT/continuum" service restart "$PROJECT_NAME"
```

Service-mode stop:

```bash
"$KIT_ROOT/continuum" service stop "$PROJECT_NAME"
```

Compatibility alias for `stop-now`:

```bash
"$KIT_ROOT/continuum" force-stop "$PROJECT_NAME"
```

Detached-mode emergency restart:

```bash
"$KIT_ROOT/continuum" force-restart "$PROJECT_NAME"
```

`stop-now` first sends `TERM`, waits briefly, then escalates to `KILL` only if the worker is still running. Use it only when the graceful controls are not enough. `force-stop` is kept as a compatibility alias for the same behavior.

## 8. Sleep, credits, and other common questions

- On macOS, both detached launches and service mode prevent idle sleep while the worker is active.
- The display can still sleep. Closing the laptop lid can still put the Mac to sleep.
- Credits and quota handling are reactive, not predictive. Continuum does not know your remaining credits ahead of time.
- Temporary rate limits back off and retry.
- Surfaced hard quota exhaustion stops the worker and records the failure.
- `continuum status` now distinguishes useful runtime states such as `running`, `paused`, `force-stopped`, `waiting`, `blocked`, `failed`, and `done`.
- Long-running passes with no fresh `codex.log` activity for `inactivity_notify_after_seconds` move into an `inactive` state and emit one notification event.
- The runner appends all notification events to `~/continuum-runner/continuum-notify.log` even if desktop notifications are disabled.
- If you want external delivery, add `notification_command` or `notification_webhook_url` in `~/continuum-runner/projects.json`.
- After you restore credits or limits, launch or restart the project again.

## 9. Keep other projects non-autonomous

If you want autonomy only for this one project:

- do not add other projects to `~/continuum-runner/projects.json`
- do not copy the autonomous project-local `AGENTS.md` block into other projects
- do not put the `STATUS:` continuation protocol into `~/.codex/AGENTS.md`

That keeps every other project in normal interactive mode.

## Result

After this setup:

- Codex has reusable unattended profiles
- the selected project has a long-term goal and autonomous status protocol
- the runner can keep resuming that one project until it reports `DONE` or `BLOCKED`
- macOS sleep prevention is automatic while the worker is active
- other projects remain normal unless you explicitly opt them in later
