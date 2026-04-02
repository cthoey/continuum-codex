# Continuum v0.1.0

First public release of Continuum for Codex.

Continuum is for the specific pain point where you have a long-running Codex-friendly project and
keep sending the same “continue from the last checkpoint” prompt over and over. It adds a thin,
project-specific autonomous loop, progress logging, restart handling, and lightweight operator
visibility through SwiftBar.

## Highlights

- project-by-project autonomous runs instead of one global mode
- resumable Codex sessions via `codex exec resume --last`
- repo enabler script for adding new autonomous projects quickly
- repo-local goals and status protocol through managed `AGENTS.md` blocks
- progress checkpoints in `docs/codex-progress.md`
- graceful restart flow with visible restart-pending state
- macOS `caffeinate` integration for launched workers
- home-level Continuum config and `~/continuum-runner` alias support
- SwiftBar monitoring and control surface

## Good Fit

- long-running technical projects with a stable frontier
- repos where Codex can usually pick the next useful task from docs and progress notes
- workflows where the human role is mostly occasional supervision rather than constant steering

## Not A Good Fit

- projects needing frequent product or architecture decisions
- ambiguous work where the next prompt changes materially from turn to turn
- work that should be reviewed by a human after every small chunk

## Compatibility Notes

- current local/live installs may still use legacy path names such as `codex-runner`
- current repo transition still preserves compatibility with older environment variables
- this is a `0.1.0` release, not a stability guarantee
