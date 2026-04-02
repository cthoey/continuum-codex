# Changelog

All notable changes to Continuum for Codex will be documented in this file.

The format is based on Keep a Changelog and this project follows Semantic Versioning, starting in
the `0.x` phase while the install shape and operator workflow continue to evolve.

## [Unreleased]

### Changed

- rewrote the README around what Continuum is, when to use it, and how to operate it
- simplified the macOS single-project setup guide
- removed the standalone branding document and folded the minimal naming note into the main docs
- added a `continuum doctor` command to validate local Continuum, Codex, runner, and project setup
- expanded `continuum` into a CLI wrapper for init, enable, start, stop, restart, and status
- added launchctl and systemd user-service support through `continuum service ...`

## [0.1.0] - 2026-04-02

### Added

- project-by-project autonomous supervisor flow built around `codex exec` and `codex exec resume --last`
- repo enabler script to provision `projects.json`, repo `AGENTS.md`, and `docs/codex-progress.md`
- graceful restart workflow with restart-state markers for external status tools
- macOS `caffeinate` integration in the runner launch path
- home-level Continuum config and `~/continuum-runner` alias installer
- SwiftBar monitor support for project status, restart state, timestamps, and runner actions
- initial branding and naming map for Continuum

### Changed

- product naming moved from internal kit wording to `Continuum for Codex`
- SwiftBar monitor now supports home-level config resolution and compatibility fallbacks for older env vars
- default graceful restart wait increased to 7200 seconds for long Codex passes

### Notes

- this is the first public `0.x` release, intended for technically comfortable users
- install paths and configuration conventions may still change before `1.0`
