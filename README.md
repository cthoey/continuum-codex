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
- records per-project logs and runtime state
- retries temporary rate limits and stops on surfaced hard quota exhaustion
- works on Unix-like systems, with built-in `caffeinate` sleep prevention on macOS
- can expose project status and controls through SwiftBar
- can make milestone commits and pushes if your Codex rules allow Git commands

## How it works

1. Put reusable Codex profiles in `~/.codex/config.toml`.
2. Create a runner directory that contains the supervisor scripts and `projects.json`.
3. Run `enable_project.py` with a repo path and a long-term project goal.
4. Launch that project with `launch_project.sh <name>`.
5. Continuum keeps resuming the same Codex thread until the model ends with `STATUS: DONE` or `STATUS: BLOCKED: ...`.

Only repos you explicitly enable become autonomous.

## Quick start

Install Codex CLI, log in once, and create a runner:

```bash
git clone git@github.com:cthoey/continuum-codex.git
cd continuum-codex

brew install codex
codex login

mkdir -p ~/.codex ~/.codex/rules ~/continuum-runner
cp samples/config.toml.sample ~/.codex/config.toml
cp samples/global-AGENTS.md.sample ~/.codex/AGENTS.md

cp supervisor/*.py supervisor/*.sh ~/continuum-runner/
cp supervisor/projects.example.json ~/continuum-runner/projects.json
chmod +x ~/continuum-runner/*.py ~/continuum-runner/*.sh

cat >> ~/.codex/rules/default.rules <<'EOF'
prefix_rule(pattern=["git", "add"], decision="allow")
prefix_rule(pattern=["git", "commit"], decision="allow")
prefix_rule(pattern=["git", "push"], decision="allow")
EOF

python3 scripts/install_home.py \
  --runner-root ~/continuum-runner \
  --kit-root "$PWD"
```

Enable one repo:

```bash
cd ~/continuum-runner
./enable_project.py /absolute/path/to/project \
  --name my-project \
  --goal "The goal of this project is to ..."
```

Launch it:

```bash
cd ~/continuum-runner
./launch_project.sh my-project
```

That is enough to start one autonomous project. For the full from-scratch walkthrough, see [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md).

## Day-to-day commands

Launch:

```bash
cd ~/continuum-runner
./launch_project.sh my-project
```

Graceful restart:

```bash
cd ~/continuum-runner
./restart_project.sh my-project
```

Graceful stop:

```bash
cd ~/continuum-runner
./stop_project.sh my-project
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

If you use SwiftBar, enable the project once with `enable_project.py` and then use the menu bar plugin to start, stop, and restart it.

## Operational notes

- Continuum is project-specific by design. Repos that are not in `projects.json` remain ordinary interactive Codex repos.
- The runner is plain Python and shell, so the core flow is not macOS-only.
- On macOS, project launches start `caffeinate -is -w <supervisor-pid>`. This is intentional and prevents idle system sleep while a worker is active.
- Credits and quota handling are reactive, not predictive. Continuum does not know your remaining credits ahead of time; it only reacts to surfaced Codex failures.
- Temporary rate limits back off and retry. Surfaced hard quota exhaustion stops the worker and records the failure.
- Launches use `nohup`, so you can close the launch terminal after the worker starts.
- Milestone commits and pushes require Codex rules that allow `git add`, `git commit`, and `git push` outside the sandbox.
- The supervisor path does not require the interactive Stop hook.

## Repository layout

- [supervisor/](supervisor/): runner scripts, project enabler, example config
- [samples/](samples/): sample Codex config, AGENTS files, optional hook files
- [scripts/install_home.py](scripts/install_home.py): writes `~/.config/continuum/config.toml` and a `~/continuum-runner` alias
- [MACOS-SINGLE-PROJECT-SETUP.md](MACOS-SINGLE-PROJECT-SETUP.md): detailed setup guide
- [RELEASE_NOTES_v0.1.0.md](RELEASE_NOTES_v0.1.0.md): first public release notes
