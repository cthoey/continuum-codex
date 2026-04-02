# Codex Autonomous Kit

Starter kit for running OpenAI Codex CLI on long-lived autonomous project loops.

This repo packages a small supervisor plus sample config and instruction files so you can:

- run autonomous Codex work project-by-project
- keep one Codex thread chain per working directory
- resume unfinished work automatically with `codex exec resume --last`
- record logs and state per project
- handle temporary rate limits differently from hard quota exhaustion
- checkpoint major milestones with git commits and pushes

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

## Repository Contents

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
- `supervisor/launch_project.sh`
  Launch one named project.
- `supervisor/stop_project.sh`
  Stop one named project.
- `supervisor/launch_all.sh`
  Legacy “launch everything in the config” entry point.
- `supervisor/projects.example.json`
  Example runner config.
- `supervisor/notify.py`
  Optional Codex `notify` helper.
- `MACOS-SINGLE-PROJECT-AUTONOMOUS-SETUP.md`
  Step-by-step macOS guide for enabling one project.

## Quick Start

1. Copy `samples/config.toml.sample` to `~/.codex/config.toml`.
2. Copy `samples/global-AGENTS.md.sample` to `~/.codex/AGENTS.md`.
3. Add a repo-local `AGENTS.md` using `samples/repo-AGENTS.md.sample`.
4. Copy `supervisor/` somewhere permanent.
5. Edit `projects.json`.
6. Launch a single project:

```bash
cd /path/to/codex-runner
./launch_project.sh my-project ./projects.json
```

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
- The optional Stop hook is for interactive use only. The supervisor path does not require it.
- The kit is macOS-friendly, but the supervisor is plain Python and shell and can be adapted to
  other Unix-like environments.
