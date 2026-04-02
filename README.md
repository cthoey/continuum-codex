# Continuum

Continuum for Codex.

This repository is still physically named `codex-autonomous-kit` for now, but the product and UI
name is `Continuum`.

Continuum is a starter kit for running OpenAI Codex CLI on long-lived autonomous project loops.

This kit is aimed at a specific pain point:

- you have a long-running project that mostly needs more time rather than constant human steering
- you find yourself submitting the same follow-up prompt over and over just to keep Codex moving
- the next step is usually "continue from the last checkpoint and keep going" rather than a fresh
  strategic decision every few minutes

This repo packages a small supervisor plus sample config and instruction files so you can:

- run autonomous Codex work project-by-project
- keep one Codex thread chain per working directory
- resume unfinished work automatically with `codex exec resume --last`
- record logs and state per project
- handle temporary rate limits differently from hard quota exhaustion
- checkpoint major milestones with git commits and pushes

## Naming

- Product/app name: `Continuum`
- Descriptor: `Continuum for Codex`
- Current GitHub repository slug: `continuum-codex`
- Current local folder name in this tree: `codex-autonomous-kit` (transition name)
- Recommended future local runner folder: `~/continuum-runner`
- Recommended future user config location: `~/.config/continuum/config.toml`

See [BRANDING.md](BRANDING.md) for the naming map and terminology.

## Version

Current version: `0.1.0`

See [CHANGELOG.md](CHANGELOG.md) for release history.

## Good Fit

Use this kit when:

- the project has a clear long-term goal and a stable working frontier
- Codex can usually choose the next useful step from repo docs and recent progress notes
- you mostly want automatic continuation, logging, and checkpointing
- you would otherwise keep nudging the agent forward with near-repetitive prompts

Do not use this kit when:

- the project needs frequent product or architecture decisions from you
- the next task is ambiguous enough that the agent needs constant steering
- the work is risky enough that you want to review each chunk before it continues
- you are still discovering the problem and the prompt has to change substantially from turn to turn

## How It Works

The kit uses a simple loop:

1. first pass:
   `codex exec -C <repo> -p <profile> "<initial prompt>"`
2. later passes:
   `codex exec -C <repo> -p <profile> resume --last "<follow-up prompt>"`
3. the repo-local `AGENTS.md` tells Codex to end with one status line:
   - `STATUS: CONTINUE`
   - `STATUS: DONE`
   - `STATUS: BLOCKED: <reason>`
4. the supervisor reads that status and decides whether to resume, stop, or mark the project blocked

This design keeps autonomy project-specific. The supervisor only runs projects that you list in
`projects.json`.

## Recommended Shape

- Keep global Codex config reusable and neutral.
- Put the long-term goal and autonomous protocol in repo-local `AGENTS.md`.
- Launch projects one at a time with `launch_project.sh`.
- If you want multiple projects simultaneously, launch each project separately.
- Use separate worktrees or separate clones for simultaneous tasks on the same repo.
- On macOS, launched supervisors automatically start a matching `caffeinate -is -w <pid>`
  watcher so the machine stays awake while autonomous work is active.

## Repository Contents

- `samples/continuum-config.toml.sample`
  Sample home-level Continuum config for user-specific paths such as the live runner root.
- `samples/config.toml.sample`
  Suggested `~/.codex/config.toml` with reusable autonomous profiles.
- `samples/global-AGENTS.md.sample`
  Neutral global guidance that does not force autonomous behavior into every repo.
- `samples/repo-AGENTS.md.sample`
  Repo-local autonomous template with project goal, status protocol, and milestone commit guidance.
- `samples/hooks.json`
  Optional interactive Stop hook sample.
- `samples/auto_continue.py`
  Optional interactive Stop hook helper.
- `supervisor/codex_supervisor.py`
  The unattended runner.
- `supervisor/enable_project.py`
  Add or update another repo in the runner without hand-editing all of the setup files.
- `supervisor/launch_project.sh`
  Launch one named project.
- `supervisor/restart_project.sh`
  Gracefully restart one named project.
- `supervisor/stop_project.sh`
  Stop one named project.
- `supervisor/launch_all.sh`
  Legacy “launch everything in the config” entry point.
- `supervisor/projects.example.json`
  Example runner config.
- `supervisor/notify.py`
  Optional Codex `notify` helper.
- `scripts/install_home.py`
  Install a home-level Continuum config and a `~/continuum-runner` alias that points at the live runner.
- `MACOS-SINGLE-PROJECT-AUTONOMOUS-SETUP.md`
  Step-by-step macOS guide for enabling one project.

## Quick Start

1. Copy `samples/config.toml.sample` to `~/.codex/config.toml`.
2. Create a neutral `~/.codex/AGENTS.md` with shared safety defaults.
3. Copy `supervisor/` somewhere permanent.
4. Install a home-level Continuum config and runner alias:

```bash
python3 scripts/install_home.py \
  --runner-root /absolute/path/to/codex-runner \
  --kit-root /absolute/path/to/continuum-codex
```

5. Enable a repo with one command:

```bash
cd /path/to/codex-runner
./enable_project.py /absolute/path/to/project \
  --goal "The goal of this project is to ..."
```

By default, the project name becomes the repo directory name. Use `--name <label>` if you want a
different name in logs and SwiftBar.

6. Launch a single project:

```bash
cd /path/to/codex-runner
./launch_project.sh my-project
```

Graceful restart:

```bash
cd /path/to/codex-runner
./restart_project.sh my-project ./projects.json
```

Stop:

```bash
cd /path/to/codex-runner
./stop_project.sh my-project
```

That helper:

- adds or updates the project entry in `projects.json`
- creates `docs/codex-progress.md` if it does not already exist
- creates or updates a managed autonomous block inside the repo's `AGENTS.md`
- auto-detects common review docs such as `README.md`, `docs/ROADMAP.md`, and `docs/EXECUTION_PLAN.md`
- is the preferred way to opt more repos into autonomy after the base runner exists

Use SwiftBar to manage projects that are already enabled.
Use `enable_project.py` to provision new ones.

Provisioning stays script-based on purpose because new autonomous projects need explicit inputs such
as the repo path and the long-term project goal. That is safer and less error-prone than trying to
collect those inputs from a menu bar action.

The home-level config is the right place for machine-specific paths such as the live runner root.
The repo-local `AGENTS.md` and `docs/codex-progress.md` stay in the project because they express
that project's goal and working state.

## Operational Notes

- `workspace-write` keeps protected paths like `.git` read-only in the sandbox.
  If you want unattended milestone commits and pushes, add Git rules such as:

```python
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "push"], decision="allow")
```

- Temporary rate limits or transient overloads are retried automatically.
- Hard quota or credits exhaustion is treated as a blocked state.
- The quota handling is reactive, not predictive:
  the kit does not know your remaining credits ahead of time; it only reacts when the Codex CLI
  surfaces quota or rate-limit failures.
- If quota exhaustion is reported clearly by the CLI, the project is marked blocked and stops.
  If the CLI uses an unfamiliar error shape, it may land as a generic failure instead of a clean
  quota-blocked state.
- After you restore credits or limits, launch or restart the project again; the runner is designed
  to continue the same thread chain when possible.
- The optional Stop hook is for interactive use only. The supervisor path does not require it.
- The kit is macOS-friendly, but the supervisor is plain Python and shell and can be adapted to
  other Unix-like environments.
- On macOS, project launches automatically start `caffeinate -is -w <supervisor-pid>`.
  This is intentional and is part of the kit's behavior.
- `caffeinate` keeps the machine awake while the supervisor runs, so it will stand in the way of
  idle system sleep. It does not defeat lid-close sleep.
- The display can still sleep because the kit uses `-is`, not display-wake flags.
- Launches use `nohup`, so after starting a project you can close the launch terminal or quit
  iTerm without killing the detached worker.
- `restart_project.sh` sends `TERM`, waits for the active pass to finish and the supervisor to
  exit, then launches the project again under the current runner configuration.
- The restart path is request-based: it writes a lightweight `restart.<project>.json` marker while
  a clean restart is pending, which makes it easy for external status UIs such as SwiftBar to show
  "restart requested, waiting for current pass to finish."
- The default graceful-restart wait is 7200 seconds (2 hours). Override it with
  `CODEX_RESTART_WAIT_TIMEOUT_SECONDS` if a machine needs a different threshold.
- `stop_project.sh` is the script-first way to request a clean stop; it does not force-kill the
  active Codex pass.
- `enable_project.py` is the script-first way to opt more repos into the runner after the global
  Codex setup already exists. It is meant to remove the repetitive hand-editing of `projects.json`,
  repo `AGENTS.md`, and `docs/codex-progress.md`.
