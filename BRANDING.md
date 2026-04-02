# Continuum Branding

This repository is still physically named `codex-autonomous-kit`, but the product and user-facing
name is `Continuum`.

## Canonical Naming

- Product/app name: `Continuum`
- Descriptor: `Continuum for Codex`
- Short internal nickname: `continuum`

## Transition Names

- Current public repository slug: `continuum-codex`
- Current local source folder in this tree: `codex-autonomous-kit`
- Current example/live runner folder name in existing installs: `codex-runner`
- Current SwiftBar plugin filename: `codex-runner.15s.py`

These old names remain for compatibility and to avoid breaking existing live setups.

## Recommended Names

- Public repository slug: `continuum-codex`
- Local runner folder: `~/continuum-runner`
- User config root: `~/.config/continuum/`
- User config file: `~/.config/continuum/config.toml`
- SwiftBar environment variable: `CONTINUUM_RUNNER_ROOT`

## Terminology

- Project: a repo that has been opted into autonomous work
- Worker: one active Codex execution for one project
- Supervisor: the outer loop that starts, resumes, retries, and stops workers
- Pass: one `codex exec` or `codex exec resume --last` cycle
- Progress log: the repo-local `docs/codex-progress.md` checkpoint file
- Restart pending: a requested clean restart that is waiting for the current pass to finish

## Naming Policy

- Prefer `Continuum` in UI text, docs, and user-facing descriptions.
- Keep old filenames and paths only where changing them would disrupt active installs.
- Add compatibility fallbacks before removing older names such as `codex-runner` or
  `RELAY_RUNNER_ROOT` / `CODEX_RUNNER_ROOT`.
