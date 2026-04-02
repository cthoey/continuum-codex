# Continuum for Codex: macOS Single-Project Setup

Continuum keeps long-running Codex CLI projects moving.

Use this setup when you keep nudging the same repo forward with "continue" and the work mostly needs continuity, not constant judgment. Do not use it when the project still needs frequent human decisions, prompt reframing, or review after every small step.

This guide enables exactly one repo for autonomous work. Other repos on the machine stay normal interactive Codex repos unless you opt them in later.

This guide is macOS-specific because it uses Homebrew and the built-in `caffeinate` integration. The runner itself is plain Python and shell, so the core Continuum flow is also suitable for Linux with Linux-appropriate install and sleep-management choices.

## Requirements

- macOS
- Codex CLI access
- a Git repo you want to run autonomously
- Python 3

This guide assumes the Continuum repo is cloned locally:

```bash
git clone git@github.com:cthoey/continuum-codex.git
cd continuum-codex
export KIT_ROOT="$PWD"
```

It also assumes your target repo has an absolute path:

```bash
export PROJECT_PATH="/absolute/path/to/project"
export PROJECT_NAME="my-project"
```

Sanity check the repo path:

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

Do not rely on Codex to infer the long-term goal from the repo name alone.

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

That means unattended runs do not pause for approval. If a tool install or network action is blocked by the current environment, the repo should record the blocker and continue with other useful work when possible.

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

Use the CLI instead of hand-editing `projects.json`, repo `AGENTS.md`, and `docs/codex-progress.md`:

```bash
"$KIT_ROOT/continuum" enable "$PROJECT_PATH" \
  --name "$PROJECT_NAME" \
  --goal "The goal of this project is to ..."
```

What the helper writes:

- a project entry in `projects.json`
- a managed autonomous block inside the repo root `AGENTS.md`
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

Inspect the `launchctl` service definition and runtime state:

```bash
"$KIT_ROOT/continuum" service status "$PROJECT_NAME"
```

What to expect:

- the first pass uses `codex exec`
- follow-up passes use `codex exec resume --last`
- `STATUS: CONTINUE` means keep looping
- `STATUS: DONE` or `STATUS: BLOCKED: ...` means stop

If you prefer SwiftBar, this is the point where it becomes useful. Project provisioning stays script-based, but day-to-day start, stop, and restart actions can happen from the menu bar once the repo is enabled.

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

Service-mode restart:

```bash
"$KIT_ROOT/continuum" service restart "$PROJECT_NAME"
```

Service-mode stop:

```bash
"$KIT_ROOT/continuum" service stop "$PROJECT_NAME"
```

## 8. Sleep, credits, and other common questions

- On macOS, both detached launches and service mode prevent idle sleep while the worker is active.
- The display can still sleep. Closing the laptop lid can still put the Mac to sleep.
- Credits and quota handling are reactive, not predictive. Continuum does not know your remaining credits ahead of time.
- Temporary rate limits back off and retry.
- Surfaced hard quota exhaustion stops the worker and records the failure.
- After you restore credits or limits, launch or restart the project again.

## 9. Keep other repos non-autonomous

If you want autonomy only for this one repo:

- do not add other repos to `~/continuum-runner/projects.json`
- do not copy the autonomous repo-local `AGENTS.md` block into other repos
- do not put the `STATUS:` continuation protocol into `~/.codex/AGENTS.md`

That keeps every other repo in normal interactive mode.

## Result

After this setup:

- Codex has reusable unattended profiles
- the selected repo has a long-term goal and autonomous status protocol
- the runner can keep resuming that one repo until it reports `DONE` or `BLOCKED`
- macOS sleep prevention is automatic while the worker is active
- other repos remain normal unless you explicitly opt them in later
