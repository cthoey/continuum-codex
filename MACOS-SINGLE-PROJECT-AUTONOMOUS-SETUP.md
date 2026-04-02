# macOS: Enable One Project for Autonomous Codex

This guide sets up Codex from scratch on macOS so that exactly one project runs autonomously.

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

## 6. Create a repo-local `AGENTS.md` in the target project

This file is what makes this one project autonomous.

Create:

```bash
$PROJECT_PATH/AGENTS.md
```

Use this starting template:

```md
# AGENTS.md

## Project goal
- The goal of this project is to <describe the overall long-term goal here>.
- Keep that long-term goal in mind when choosing between plausible next tasks.

## Autonomous execution protocol
- Work autonomously unless you are truly blocked.
- Maintain a running progress log inside the repo at `docs/codex-progress.md` unless the repo already has a better location.
- After every meaningful chunk of work, update the progress log with findings, files touched, next steps, and open risks.
- Choose the next highest-value task yourself when the current chunk is complete.
- Prefer small, validated increments over speculative rewrites.
- Only stop when the task is actually done or when real human input is required.
- Feel free to install tools you need when the current environment, sandbox, and permissions allow it.
- If installation is blocked, record the exact tool and blocking command in the progress log and continue with other useful work when possible.
- For major validated milestones, stage the relevant files, create a focused git commit, and push it to the configured remote.
- Record the commit SHA and push status in the progress log.

## Completion status protocol
End every final message with exactly one of these lines:
- `STATUS: CONTINUE`
- `STATUS: DONE`
- `STATUS: BLOCKED: <specific reason>`

## Validation
- Run the most relevant available build, test, or lint commands after changes.
- When there are no formal tests, use lightweight reproducible validation commands and record them.

## Safety
- Do not revert unrelated existing changes.
- Do not create commits unless explicitly asked.
```

Notes:

- The `Project goal` section is important. It tells the agent the long-term outcome for this repo.
- The `STATUS:` section is required for the supervisor loop.
- Keep this file in the project root.
- Do not add this file to repos you do not want to run autonomously.

## 7. Create a runner directory

Keep the runner outside the Downloads kit so the runtime state has a stable home.

Example:

```bash
mkdir -p ~/codex-runner
cp "$KIT_ROOT/supervisor/codex_supervisor.py" ~/codex-runner/
cp "$KIT_ROOT/supervisor/launch_all.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/launch_project.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/stop_project.sh" ~/codex-runner/
cp "$KIT_ROOT/supervisor/notify.py" ~/codex-runner/
cp "$KIT_ROOT/supervisor/projects.example.json" ~/codex-runner/projects.json
chmod +x ~/codex-runner/codex_supervisor.py ~/codex-runner/launch_all.sh ~/codex-runner/launch_project.sh ~/codex-runner/stop_project.sh ~/codex-runner/notify.py
```

## 8. Edit `~/codex-runner/projects.json` for one project

Replace the example file with a single-project config like this:

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
      "prompt": "Work autonomously on this project. The overall project goal is to <repeat the long-term project goal here>. Follow the repo AGENTS.md instructions, keep progress notes updated, choose the next highest-value task yourself, install useful tools when the current environment allows it, create git commits and pushes for major validated milestones, and continue until you are DONE or truly BLOCKED.",
      "profile": "autonomous",
      "max_passes": 0,
      "resume_existing": true,
      "enabled": true,
      "extra_args": []
    }
  ]
}
```

Now replace the placeholder path with your real path:

```bash
perl -0pi -e 's|/absolute/path/to/project|'"$PROJECT_PATH"'|g' ~/codex-runner/projects.json
```

Optional adjustments:

- Change `"name"` to the repo name you want in logs.
- Replace the goal text in `"prompt"` with the real long-term goal for this project.
- Use `"profile": "autonomous_fast"` if you want a cheaper/faster background run.
- Leave `"notify": false` for the simplest initial setup.
- Tune `"rate_limit_retry_seconds"` and `"max_rate_limit_retries"` if you want different retry behavior for temporary rate limits.

Important:

- Only projects listed here will run under the supervisor.
- This is the main project-specific switch for unattended execution.

## 9. Start one autonomous project

Launch the selected project by name:

```bash
cd ~/codex-runner
./launch_project.sh single-project ./projects.json
```

This starts one background supervisor process for that project only.

If you want multiple simultaneous projects later, launch each one separately with its own
`./launch_project.sh <project-name> ./projects.json` command.

## 10. Watch logs and state

Tail the supervisor log:

```bash
tail -f ~/codex-runner/supervisor.single-project.out.log
```

Tail the project Codex log:

```bash
tail -f ~/codex-runner/runtime/single-project/logs/codex.log
```

Inspect the latest saved final message:

```bash
cat ~/codex-runner/runtime/single-project/state/last_message.md
```

Inspect the current state:

```bash
cat ~/codex-runner/runtime/single-project/state/status.json
```

What to expect:

- First pass uses `codex exec`.
- Later passes use `codex exec resume --last`.
- If the final message ends with `STATUS: CONTINUE`, the supervisor loops.
- If it ends with `STATUS: DONE` or `STATUS: BLOCKED: ...`, the loop stops.
- If Codex hits a temporary rate limit or transient overload, the supervisor waits and retries automatically.
- If Codex hits a hard quota or credits exhaustion condition, the supervisor stops and records a blocked state.

## 11. Stop the project runner cleanly

When you want to stop that project's background supervisor:

```bash
cd ~/codex-runner
./stop_project.sh single-project
```

## 12. Optional: keep the Stop hook for interactive Codex use

The supervisor path above does not require hooks.

If you also want interactive TUI sessions to auto-continue when the model emits `STATUS: CONTINUE`, add the hook files too:

```bash
mkdir -p ~/.codex/hooks
cp "$KIT_ROOT/samples/hooks.json" ~/.codex/hooks.json
cp "$KIT_ROOT/samples/auto_continue.py" ~/.codex/hooks/auto_continue.py
chmod +x ~/.codex/hooks/auto_continue.py
```

This is optional. It affects interactive Codex sessions, not the supervisor loop.

## 13. How to keep other projects non-autonomous

If you want autonomy only for this one project:

- Do not add other repos to `~/codex-runner/projects.json`.
- Do not copy the autonomous repo-local `AGENTS.md` into other repos.
- Do not put the `STATUS:` continuation protocol into `~/.codex/AGENTS.md`.

That keeps other repos in normal interactive mode.

## 14. First-run checklist

Before you trust the setup, confirm all of these:

1. `codex --version` works.
2. `codex login` completed successfully.
3. `~/.codex/config.toml` exists and includes the `autonomous` profile.
4. `~/.codex/AGENTS.md` exists and does not contain the global `STATUS:` protocol.
5. `$PROJECT_PATH/AGENTS.md` exists and does contain the exact `STATUS:` protocol.
6. `~/codex-runner/projects.json` contains exactly one enabled project.
7. The `path` field in `projects.json` matches `$PROJECT_PATH`.
8. `./launch_all.sh ./projects.json` starts successfully.
9. `runtime/single-project/state/status.json` appears after the first run.

## 15. If the project does not continue automatically

Check these in order:

1. Open `$PROJECT_PATH/AGENTS.md` and confirm the exact `STATUS:` lines are present.
2. Open `~/codex-runner/runtime/single-project/state/last_message.md` and confirm the last line is one of:
   - `STATUS: CONTINUE`
   - `STATUS: DONE`
   - `STATUS: BLOCKED: <reason>`
3. Open `~/codex-runner/runtime/single-project/logs/codex.log` and inspect the last pass.
4. Confirm `resume_existing` is `true` in `projects.json`.
5. Confirm the project path in `projects.json` is the same working directory you expect.

## Result

After this setup:

- Codex has reusable unattended profiles.
- Only the one project you selected is configured for autonomous continuation.
- The supervisor will keep resuming that one project until the model reports `DONE` or `BLOCKED`.
- Other repos remain normal unless you explicitly opt them in later.
