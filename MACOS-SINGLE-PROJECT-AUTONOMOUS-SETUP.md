# Continuum for Codex: macOS Single-Project Setup

Continuum keeps long-running Codex CLI projects moving.

Use this setup when you keep nudging the same repo forward with "continue" and the work mostly needs continuity, not constant judgment. Do not use it when the project still needs frequent human decisions, prompt reframing, or review after every small step.

This guide enables exactly one repo for autonomous work. Other repos on the machine stay normal interactive Codex repos unless you opt them in later.

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

Create a runner directory and copy the supervisor files into it:

```bash
mkdir -p ~/continuum-runner
cp "$KIT_ROOT"/supervisor/*.py "$KIT_ROOT"/supervisor/*.sh ~/continuum-runner/
cp "$KIT_ROOT"/supervisor/projects.example.json ~/continuum-runner/projects.json
chmod +x ~/continuum-runner/*.py ~/continuum-runner/*.sh
```

Install the home-level config and runner alias:

```bash
python3 "$KIT_ROOT/scripts/install_home.py" \
  --runner-root ~/continuum-runner \
  --kit-root "$KIT_ROOT"
```

That creates:

- `~/.config/continuum/config.toml`
- `~/continuum-runner`

If you already have a live runner elsewhere, pass that path to `--runner-root` instead.

## 5. Enable the project

Use the helper instead of hand-editing `projects.json`, repo `AGENTS.md`, and `docs/codex-progress.md`:

```bash
cd ~/continuum-runner
./enable_project.py "$PROJECT_PATH" \
  --name "$PROJECT_NAME" \
  --goal "The goal of this project is to ..."
```

What the helper writes:

- a project entry in `projects.json`
- a managed autonomous block inside the repo root `AGENTS.md`
- `docs/codex-progress.md` if it does not already exist

It also auto-detects common planning docs such as `README.md`, `docs/ROADMAP.md`, and `docs/EXECUTION_PLAN.md`.

## 6. Launch and monitor it

Launch the project:

```bash
cd ~/continuum-runner
./launch_project.sh "$PROJECT_NAME"
```

Tail the worker log:

```bash
tail -f ~/continuum-runner/runtime/"$PROJECT_NAME"/logs/codex.log
```

Inspect saved state:

```bash
cat ~/continuum-runner/runtime/"$PROJECT_NAME"/state/status.json
cat ~/continuum-runner/runtime/"$PROJECT_NAME"/state/last_message.md
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
cd ~/continuum-runner
./restart_project.sh "$PROJECT_NAME"
```

Graceful stop:

```bash
cd ~/continuum-runner
./stop_project.sh "$PROJECT_NAME"
```

`restart_project.sh` and `stop_project.sh` do not force-kill the active `codex exec` pass. They wait for a clean boundary.

## 8. Sleep, credits, and other common questions

- On macOS, launches start `caffeinate -is -w <supervisor-pid>`. This is intentional and prevents idle system sleep while the worker is active.
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
