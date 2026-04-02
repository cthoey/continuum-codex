#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Install a home-level Continuum config and runner alias.",
    )
    parser.add_argument(
        "--runner-root",
        required=True,
        help="Path to the existing live runner directory.",
    )
    parser.add_argument(
        "--kit-root",
        help="Optional path to the Continuum source repo on this machine.",
    )
    parser.add_argument(
        "--config-path",
        default="~/.config/continuum/config.toml",
        help="Home-level Continuum config path.",
    )
    parser.add_argument(
        "--home-runner-link",
        default="~/continuum-runner",
        help="Home-level symlink path that should point at the live runner.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing non-matching config file or symlink.",
    )
    return parser.parse_args()


def render_config(home_runner_link: Path, kit_root: Path | None) -> str:
    lines = [
        "# Continuum user config",
        "",
        "# Home-level path to the live runner that owns projects.json, runtime state, logs, and pidfiles.",
        f'runner_root = "{home_runner_link}"',
    ]
    if kit_root is not None:
        lines.extend(
            [
                "",
                "# Optional source repo location for local Continuum development.",
                f'kit_root = "{kit_root}"',
            ]
        )
    lines.append("")
    return "\n".join(lines)


def ensure_symlink(link_path: Path, target_path: Path, force: bool) -> None:
    if link_path.exists() or link_path.is_symlink():
        if not link_path.is_symlink():
            try:
                if link_path.resolve() == target_path.resolve():
                    return
            except Exception:
                pass
        if link_path.is_symlink() and link_path.resolve() == target_path.resolve():
            return
        if not force:
            raise SystemExit(
                f"Home runner link already exists and does not match target: {link_path}"
            )
        if link_path.is_dir() and not link_path.is_symlink():
            raise SystemExit(
                f"Refusing to replace existing directory without manual intervention: {link_path}"
            )
        link_path.unlink()
    link_path.parent.mkdir(parents=True, exist_ok=True)
    link_path.symlink_to(target_path)


def write_config(config_path: Path, content: str, force: bool) -> None:
    if config_path.exists():
        existing = config_path.read_text(encoding="utf-8")
        if existing == content:
            return
        if not force:
            raise SystemExit(
                f"Config already exists and differs: {config_path}"
            )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")


def main() -> int:
    args = parse_args()

    runner_root = Path(args.runner_root).expanduser().resolve()
    if not runner_root.exists():
        raise SystemExit(f"Runner root does not exist: {runner_root}")

    config_path = Path(args.config_path).expanduser()
    home_runner_link = Path(args.home_runner_link).expanduser()
    kit_root = Path(args.kit_root).expanduser().resolve() if args.kit_root else None

    ensure_symlink(home_runner_link, runner_root, args.force)
    config_content = render_config(home_runner_link, kit_root)
    write_config(config_path, config_content, args.force)

    print(f"Continuum config: {config_path}")
    print(f"Home runner alias: {home_runner_link} -> {runner_root}")
    if kit_root is not None:
        print(f"Kit repo: {kit_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
