# Continuum for Codex: macOS Single-Project Setup

This guide sets up Continuum for Codex from scratch on macOS so that exactly one project runs
autonomously.

The examples below still use a `codex-runner` folder name for compatibility with existing installs.
For a brand-new setup, `continuum-runner` is the cleaner long-term name.

If you are standardizing a machine-level install, prefer a home config at
`~/.config/continuum/config.toml` and a home runner alias such as `~/continuum-runner`.

Use this setup for projects where the agent mostly needs continued execution rather than constant
human steering. It is a good fit when you keep finding yourself sending the same "continue from the
last checkpoint and keep going" prompt just to nudge Codex along.

Do not use this setup for projects that still need frequent human decisions, prompt reframing, or
close supervision after every small chunk.

It keeps autonomy project-specific:

- Global Codex config defines reusable profiles.
- Only the target project gets the autonomous `AGENTS.md` protocol.
- Only the target project is listed in the supervisor `projects.json`.

If you have other repos on the same machine, they remain normal interactive Codex repos unless you explicitly add the same setup to them later.

## What this guide uses

This guide assumes the starter kit is here:

```bash
/path/to/codex-autonomous-kit
```

It also assumes your target project is a Git repo and has an absolute path like:

```bash
/absolute/path/to/project
```

## 1. Pick the project path

Set the kit root once in your shell:

```bash
export KIT_ROOT="/path/to/codex-autonomous-kit"
```

Then set the project path:

Set the project path once in your shell so you can reuse it in later commands:

```bash
export PROJECT_PATH="/absolute/path/to/project"
export PROJECT_NAME="$(basename "$PROJECT_PATH")"
```

Quick sanity check:

```bash
test -d "$PROJECT_PATH" && git -C "$PROJECT_PATH" rev-parse --is-inside-work-tree
```

Expected output:

```text
true
```

If that command fails, stop and fix the project path first.

If you want a different label in logs and SwiftBar than the repo directory name, replace
`$PROJECT_NAME` later by passing `--name "your-label"` to `enable_project.py`.

## 1.5 Define the project goal

Before wiring up autonomy, write down the overall goal for this specific project in one or two
sentences.

Use a concrete statement such as:

```text
The goal of this project is to decompile the Game Boy Advance game Mega Man Zero 3 for the eventual purpose of running it natively on macOS, Linux, and Windows.
```

This should be different for each autonomous project. Do not rely on Codex to infer the long-term
goal from the repo name alone.

## 2. Install Codex CLI

Use Homebrew on macOS:

```bash
brew install codex
```

If `codex` is already installed, upgrade it:

```bash
brew upgrade codex
```

Verify the install:

```bash
codex --version
```

## 3. Authenticate once

For a local macOS unattended runner, the simplest path is to log in once and let `codex exec` reuse that saved auth:

```bash
codex login
```

If your installed version does not expose `codex login`, run:

```bash
codex
```

and complete the login flow.

## 4. Create `~/.codex/config.toml`

Create the config directory:

```bash
mkdir -p ~/.codex
```

Copy the sample config from the kit:

```bash
cp "$KIT_ROOT/samples/config.toml.sample" ~/.codex/config.toml
```

The sample already defines the important unattended profiles:

- `autonomous`
- `autonomous_fast`

The important behavior is:

- `approval_policy = "never"`
- `sandbox_mode = "workspace-write"`
- `sandbox_workspace_write.network_access = false`

That means unattended runs will not pause for approval. If the agent needs to install something and
the current sandbox or network policy blocks it, the command will fail and the agent should record
the blocker rather than waiting for a prompt.

Also note: in `workspace-write`, protected paths such as `.git` remain read-only in the sandbox.
That means unattended `git add`, `git commit`, and `git push` for milestone checkpoints need rules
that allow those commands to run outside the sandbox.

Do not add a global default profile such as:

```toml
profile = "autonomous"
```

Leaving the profile unset globally keeps your normal interactive Codex sessions safer.

## 4.5 Add Git rules for autonomous milestone commits and pushes

Create the rules directory:

```bash
mkdir -p ~/.codex/rules
```

Append these rules to `~/.codex/rules/default.rules`:

```python
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "push"], decision="allow")
```

These rules let autonomous projects stage files, create milestone commits, and push them without
switching the whole profile to `danger-full-access`.

## 5. Create a neutral global `~/.codex/AGENTS.md`

Do not copy `samples/global-AGENTS.md.sample` as-is if you want autonomy to stay project-specific.

That sample adds the `STATUS:` continuation protocol globally, which would affect every repo on your machine.

Instead, create a neutral global file with shared safety defaults only:

```md
# ~/.codex/AGENTS.md

## Global working defaults
- Do not revert unrelated existing changes.
- Prefer small, validated changes over large speculative rewrites.
- Explain when sandbox limits block a necessary command.
- Prefer project-local guidance over generic assumptions.
- For interactive or non-autonomous work, do not create commits unless explicitly asked.
- For autonomous supervisor-driven projects, create git commits and pushes for major validated milestones.
- Keep autonomous milestone commits focused and descriptive.
```

## 6. Create a runner directory

Keep the runner outside the Downloads kit so the runtime state has a stable home.

Example:

```bash
mkdir -p ~/codex-runner
cp "$KIT_ROOT/supervisor/codex_supervisor.py" ~/codex-runner/
cp "$KIT_ROOT/supervisor/enable_project.py" ~/codex-runner/
cp "$KIT_ROOT/supervisor/launch_all.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/launch_project.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/restart_project.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/stop_project.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/notify.py" ~/codex-runner/
cp "$KIT_ROOT/supervisor/projects.example.json" ~/codex-runner/projects.json
chmod +x ~/codex-runner/codex_supervisor.py ~/codex-runner/enable_project.py ~/codex-runner/launch_all.sh ~/codex-runner/launch_project.sh ~/codex-runner/restart_project.sh ~/codex-runner/stop_project.sh ~/codex-runner/notify.py
```

## 7. Enable the project with the helper

Use the helper instead of hand-editing `projects.json`, repo `AGENTS.md`, and
`docs/codex-progress.md` yourself:

```bash
cd ~/codex-runner
./enable_project.py "$PROJECT_PATH" \
  --goal "The goal of this project is to <repeat the long-term project goal here>."
```

What the helper does:

- adds or updates the project entry in `projects.json`
- creates `docs/codex-progress.md` if it does not already exist
- creates or updates a managed autonomous block inside the repo root `AGENTS.md`
- auto-detects common review docs such as `README.md`, `docs/ROADMAP.md`, and
  `docs/EXECUTION_PLAN.md`

Useful optional flags:

```bash
./enable_project.py "$PROJECT_PATH" \
  --goal "The goal of this project is to <repeat the long-term project goal here>." \
  --name "$PROJECT_NAME" \
  --profile autonomous_fast \
  --review README.md \
  --review docs/ROADMAP.md
```

If you want to see or hand-tune what it wrote, the resulting `projects.json` entry will look like:

```json
{
  "codex_bin": "codex",
  "default_profile": "autonomous",
  "default_followup_prompt": "Proceed with the project. Continue from your last checkpoint. Update the progress notes. Choose the next highest-value task yourself. Only stop when you are actually DONE or BLOCKED. End with exactly one status line: STATUS: CONTINUE, STATUS: DONE, or STATUS: BLOCKED: <reason>.",
  "supervisor_root": "./runtime",
  "notify": false,
  "rate_limit_retry_seconds": 900,
  "max_rate_limit_retries": 8,
  "projects": [
    {
      "name": "single-project",
      "path": "/absolute/path/to/project",
      "prompt": "Work autonomously on this project. The goal of this project is to <repeat the long-term project goal here>. Follow the repo AGENTS.md instructions, keep progress notes updated, choose the next highest-value task yourself, install useful tools when the current environment allows it, create git commits and pushes for major validated milestones, and continue until you are DONE or truly BLOCKED.",
      "profile": "autonomous",
      "max_passes": 0,
      "resume_existing": true,
      "enabled": true,
      "extra_args": []
    }
  ]
}
```

Optional adjustments:

- Change `"name"` if you want a different project label in logs and SwiftBar.
- Use `"profile": "autonomous_fast"` if you want a cheaper/faster background run.
- Leave `"notify": false` for the simplest initial setup.
- Tune `"rate_limit_retry_seconds"` and `"max_rate_limit_retries"` if you want different retry behavior for temporary rate limits.

Important:

- Only projects listed here will run under the supervisor.
- This is the main project-specific switch for unattended execution.

Notes:

- The long-term project goal is important. Do not rely on Codex to infer it from the repo name.
- The helper writes the `STATUS:` continuation protocol into the repo-local managed `AGENTS.md`
  block because that protocol is required for the supervisor loop.
- The helper is the preferred path for opting more repos into autonomy later.
- SwiftBar is the preferred control surface for already-enabled projects, but project provisioning
  stays script-based because it needs explicit inputs such as the repo path and project goal.

## 8. Start one autonomous project

Launch the selected project by name:

```bash
cd ~/codex-runner
./launch_project.sh "$PROJECT_NAME" ./projects.json
```

This starts one background supervisor process for that project only.

On macOS, this also starts a matching `caffeinate -is -w <supervisor-pid>` watcher so the machine
stays awake while that supervisor is active. This is intentional. It will prevent idle system sleep
while the project is running. The display can still sleep, and lid-close sleep still wins.

If you want multiple simultaneous projects later, launch each one separately with its own
`./launch_project.sh <project-name> ./projects.json` command.

## 9. Watch logs and state

Tail the supervisor log:

```bash
tail -f ~/codex-runner/supervisor."$PROJECT_NAME".out.log
```

Tail the project Codex log:

```bash
tail -f ~/codex-runner/runtime/"$PROJECT_NAME"/logs/codex.log
```

Inspect the latest saved final message:

```bash
cat ~/codex-runner/runtime/"$PROJECT_NAME"/state/last_message.md
```

Inspect the current state:

```bash
cat ~/codex-runner/runtime/"$PROJECT_NAME"/state/status.json
```

What to expect:

- First pass uses `codex exec`.
- Later passes use `codex exec resume --last`.
- If the final message ends with `STATUS: CONTINUE`, the supervisor loops.
- If it ends with `STATUS: DONE` or `STATUS: BLOCKED: ...`, the loop stops.
- If Codex hits a temporary rate limit or transient overload, the supervisor waits and retries automatically.
- If Codex hits a hard quota or credits exhaustion condition, the supervisor stops and records a blocked state.
- The quota handling is reactive:
  the runner does not know your remaining credits ahead of time and only reacts when the Codex CLI
  reports a quota or rate-limit error.
- After you restore credits or limits, start or restart the project again so it can continue.

## 10. Stop the project runner cleanly

When you want to stop that project's background supervisor:

```bash
cd ~/codex-runner
./stop_project.sh "$PROJECT_NAME"
```

`stop_project.sh` requests a graceful stop. It does not force-kill the active `codex exec` pass.

## 10.5 Restart the project runner cleanly

If you want to restart the project under the current runner configuration, use:

```bash
cd ~/codex-runner
./restart_project.sh "$PROJECT_NAME" ./projects.json
```

This sends `TERM`, waits for the current pass to finish and the supervisor to exit, then launches
the project again. On macOS, the relaunched project also gets the automatic `caffeinate` watcher.
The restart path is request-based: while the current pass is finishing, the runner writes a small
`restart.<project>.json` marker that status tools can read to show that a clean restart is pending.
The default graceful-restart wait is 7200 seconds (2 hours). Override it with
`CODEX_RESTART_WAIT_TIMEOUT_SECONDS` if you need a shorter or longer threshold.

## 11. Optional: keep the Stop hook for interactive Codex use

The supervisor path above does not require hooks.

If you also want interactive TUI sessions to auto-continue when the model emits `STATUS: CONTINUE`, add the hook files too:

```bash
mkdir -p ~/.codex/hooks
cp "$KIT_ROOT/samples/hooks.json" ~/.codex/hooks.json
cp "$KIT_ROOT/samples/auto_continue.py" ~/.codex/hooks/auto_continue.py
chmod +x ~/.codex/hooks/auto_continue.py
```

This is optional. It affects interactive Codex sessions, not the supervisor loop.

## 12. How to keep other projects non-autonomous

If you want autonomy only for this one project:

- Do not add other repos to `~/codex-runner/projects.json`.
- Do not copy the autonomous repo-local `AGENTS.md` into other repos.
- Do not put the `STATUS:` continuation protocol into `~/.codex/AGENTS.md`.

That keeps other repos in normal interactive mode.

## 13. First-run checklist

Before you trust the setup, confirm all of these:

1. `codex --version` works.
2. `codex login` completed successfully.
3. `~/.codex/config.toml` exists and includes the `autonomous` profile.
4. `~/.codex/AGENTS.md` exists and does not contain the global `STATUS:` protocol.
5. `$PROJECT_PATH/AGENTS.md` exists and does contain the managed autonomous block with the exact `STATUS:` protocol.
6. `~/codex-runner/projects.json` contains exactly one enabled project.
7. The `path` field in `projects.json` matches `$PROJECT_PATH`.
8. `./launch_project.sh "$PROJECT_NAME" ./projects.json` starts successfully.
9. `runtime/$PROJECT_NAME/state/status.json` appears after the first run.

## 14. If the project does not continue automatically

Check these in order:

1. Open `$PROJECT_PATH/AGENTS.md` and confirm the exact `STATUS:` lines are present.
2. Open `~/codex-runner/runtime/$PROJECT_NAME/state/last_message.md` and confirm the last line is one of:
   - `STATUS: CONTINUE`
   - `STATUS: DONE`
   - `STATUS: BLOCKED: <reason>`
3. Open `~/codex-runner/runtime/$PROJECT_NAME/logs/codex.log` and inspect the last pass.
4. Confirm `resume_existing` is `true` in `projects.json`.
5. Confirm the project path in `projects.json` is the same working directory you expect.

## Result

After this setup:

- Codex has reusable unattended profiles.
- Only the one project you selected is configured for autonomous continuation.
- The supervisor will keep resuming that one project until the model reports `DONE` or `BLOCKED`.
- You can manage the project from scripts with `launch_project.sh`, `restart_project.sh`, and
  `stop_project.sh`.
- On macOS, the launched project keeps the machine awake automatically through `caffeinate` while
  the supervisor is active.
- Other repos remain normal unless you explicitly opt them in later.

## Adding Another Project Later

Once the base runner and global Codex setup already exist, you do not need to repeat this guide by
hand for every new repo.

Use the helper:

```bash
cd ~/codex-runner
./enable_project.py /absolute/path/to/another-project \
  --goal "The goal of this project is to ..."
```

That helper updates `projects.json`, creates `docs/codex-progress.md` if needed, and inserts or
updates the managed autonomous block in the repo's `AGENTS.md`.
