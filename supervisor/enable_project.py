#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

MANAGED_BEGIN = "<!-- codex-autonomous-kit:begin -->"
MANAGED_END = "<!-- codex-autonomous-kit:end -->"

DEFAULT_CONFIG = {
    "codex_bin": "codex",
    "default_profile": "autonomous",
    "default_followup_prompt": (
        "Proceed with the project. Continue from your last checkpoint. "
        "Update the progress notes. Choose the next highest-value task yourself. "
        "Only stop when you are actually DONE or BLOCKED. "
        "End with exactly one status line: STATUS: CONTINUE, STATUS: DONE, or "
        "STATUS: BLOCKED: <reason>."
    ),
    "supervisor_root": "./runtime",
    "notify": False,
    "rate_limit_retry_seconds": 900,
    "max_rate_limit_retries": 8,
    "projects": [],
}

AUTO_REVIEW_CANDIDATES = [
    "README.md",
    "docs/usa-port-plan.md",
    "docs/ROADMAP.md",
    "docs/EXECUTION_PLAN.md",
    "docs/EMULATOR_ORACLE.md",
    "docs/re-notes.md",
    "docs/re-next.md",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Enable another repo for the Codex autonomous runner.",
    )
    parser.add_argument("project_path", help="Absolute or relative path to the target git repo.")
    parser.add_argument(
        "--goal",
        required=True,
        help="Long-term project goal. This becomes part of the repo-local AGENTS block and initial prompt.",
    )
    parser.add_argument(
        "--name",
        help="Project name to use in projects.json and logs. Defaults to the repo directory name.",
    )
    parser.add_argument(
        "--profile",
        default="autonomous",
        help="Runner profile name. Defaults to 'autonomous'.",
    )
    parser.add_argument(
        "--runner-root",
        default=str(Path(__file__).resolve().parent),
        help="Runner directory that contains projects.json. Defaults to this script's directory.",
    )
    parser.add_argument(
        "--config",
        help="Explicit path to projects.json. Defaults to <runner-root>/projects.json.",
    )
    parser.add_argument(
        "--review",
        action="append",
        default=[],
        metavar="PATH",
        help="Repo-relative doc to review before choosing the next task. Repeatable. If omitted, the helper auto-detects common docs.",
    )
    parser.add_argument(
        "--progress-path",
        default="docs/codex-progress.md",
        help="Repo-relative path for the autonomous progress log. Defaults to docs/codex-progress.md.",
    )
    return parser.parse_args()


def ensure_git_repo(project_root: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(project_root), "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        raise SystemExit(f"Not a git repo: {project_root}")


def unique_paths(items: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        if item not in seen:
            output.append(item)
            seen.add(item)
    return output


def detect_review_docs(project_root: Path, explicit: list[str]) -> list[str]:
    docs = [item.strip() for item in explicit if item.strip()]
    if docs:
        missing = [item for item in docs if not (project_root / item).exists()]
        if missing:
            raise SystemExit(
                "Missing review docs: " + ", ".join(missing)
            )
        return unique_paths(docs)

    detected = [item for item in AUTO_REVIEW_CANDIDATES if (project_root / item).exists()]
    return unique_paths(detected)


def load_or_init_config(config_path: Path) -> dict:
    if config_path.exists():
        return json.loads(config_path.read_text(encoding="utf-8"))

    example_path = config_path.parent / "projects.example.json"
    if example_path.exists():
        raw = json.loads(example_path.read_text(encoding="utf-8"))
        raw["projects"] = []
        return raw

    return json.loads(json.dumps(DEFAULT_CONFIG))


def render_doc_list(docs: list[str]) -> str:
    if not docs:
        return ""
    if len(docs) == 1:
        return f"`{docs[0]}`"
    if len(docs) == 2:
        return f"`{docs[0]}` and `{docs[1]}`"
    inner = ", ".join(f"`{item}`" for item in docs[:-1])
    return f"{inner}, and `{docs[-1]}`"


def normalize_goal(goal: str) -> str:
    cleaned = " ".join(goal.strip().split())
    if not cleaned:
        raise SystemExit("Goal must not be empty.")
    if cleaned[-1] not in ".!?":
        cleaned += "."
    return cleaned


def render_prompt(goal: str, review_docs: list[str], progress_path: str) -> str:
    parts = [
        "Work autonomously on this project.",
        goal,
        "Follow the repo AGENTS.md instructions.",
    ]
    if review_docs:
        parts.append(f"Review {', '.join(review_docs)} before choosing the next task.")
    parts.extend(
        [
            f"Keep `{progress_path}` updated after each meaningful chunk.",
            "Prefer existing make targets, existing scripts, and current repo workflows.",
            "Install useful tools when the current environment allows it.",
            "Create git commits and pushes for major validated milestones.",
            "Choose the next highest-value task yourself.",
            "Continue until you are DONE or truly BLOCKED.",
        ]
    )
    return " ".join(parts)


def render_managed_agents_block(goal: str, review_docs: list[str], progress_path: str) -> str:
    lines = [
        MANAGED_BEGIN,
        "## Repo-Local Autonomous Workflow",
        "",
        f"- {goal}",
        "- Keep that long-term goal in mind when choosing between plausible next tasks.",
    ]
    if review_docs:
        lines.append(
            f"- Before choosing the next task, review {render_doc_list(review_docs)}."
        )
    lines.extend(
        [
            f"- Keep a running autonomous work log at `{progress_path}`.",
            f"- After every meaningful chunk of work, update `{progress_path}` with findings, files touched, validation performed, next steps, and open risks.",
            "- Choose the next highest-value task yourself when the current chunk is complete.",
            "- Prefer small, validated increments over speculative rewrites.",
            "- Only stop when the task is actually done or when real human input is required.",
            "- Feel free to install tools you need when the current environment, sandbox, and permissions allow it.",
            f"- If installation is blocked, record the exact tool and blocking command in `{progress_path}` and continue with other useful work when possible.",
            "- For major validated milestones, stage the relevant files, create a focused git commit, and push it to the configured remote.",
            f"- Record the commit SHA and push status in `{progress_path}`.",
            "- Prefer existing make targets, existing scripts, and current repo workflows over one-off ad hoc commands.",
            "- Treat unrelated existing repo changes as user work unless the current autonomous run created them.",
            "",
            "## Completion Status Protocol",
            "",
            "End every final message with exactly one of these lines:",
            "",
            "- `STATUS: CONTINUE`",
            "- `STATUS: DONE`",
            "- `STATUS: BLOCKED: <specific reason>`",
            "",
            "Use `STATUS: DONE` only when the requested objective is genuinely complete.",
            "",
            "Use `STATUS: BLOCKED: ...` only when real human input, credentials, missing files, or permissions are required.",
            MANAGED_END,
        ]
    )
    return "\n".join(lines) + "\n"


def write_agents_file(agents_path: Path, block: str) -> None:
    if agents_path.exists():
        text = agents_path.read_text(encoding="utf-8")
        if MANAGED_BEGIN in text and MANAGED_END in text:
            start = text.index(MANAGED_BEGIN)
            end = text.index(MANAGED_END) + len(MANAGED_END)
            replacement = block.rstrip()
            updated = text[:start].rstrip() + "\n\n" + replacement + "\n"
        else:
            updated = text.rstrip() + "\n\n" + block
    else:
        updated = "# AGENTS.md\n\n" + block
    agents_path.write_text(updated, encoding="utf-8")


def create_progress_log(progress_path: Path, project_name: str, goal: str, review_docs: list[str]) -> None:
    if progress_path.exists():
        return

    progress_path.parent.mkdir(parents=True, exist_ok=True)
    review_line = ""
    if review_docs:
        review_line = (
            f"- Review {render_doc_list(review_docs)} before selecting the next autonomous task.\n"
        )

    progress_path.write_text(
        (
            "# Codex Progress Log\n\n"
            "## Project\n\n"
            f"- Workspace: `{project_name}`\n"
            f"- Goal: {goal}\n\n"
            "## Operating Notes\n\n"
            + review_line +
            "- Prefer existing reproducible repo workflows over new one-off tooling.\n"
            "- Record each meaningful work chunk below with validation, files touched, next steps, and risks.\n"
            "- For major milestones, also record the commit SHA and whether the push succeeded.\n\n"
            "## Session Log\n\n"
            f"### {date.today().isoformat()}\n\n"
            "- Initial autonomous setup completed.\n"
            "- Next autonomous runs should append progress entries here.\n"
        ),
        encoding="utf-8",
    )


def upsert_project(config: dict, entry: dict) -> tuple[dict, str]:
    projects = config.setdefault("projects", [])
    project_path = entry["path"]
    project_name = entry["name"]

    for index, project in enumerate(projects):
        if project.get("path") == project_path or project.get("name") == project_name:
            merged = dict(project)
            merged["name"] = project_name
            merged["path"] = project_path
            merged["prompt"] = entry["prompt"]
            merged["profile"] = entry["profile"]
            merged.setdefault("max_passes", 0)
            merged.setdefault("resume_existing", True)
            merged.setdefault("enabled", True)
            merged.setdefault("extra_args", [])
            projects[index] = merged
            return config, "updated"

    projects.append(entry)
    return config, "added"


def main() -> int:
    args = parse_args()
    runner_root = Path(args.runner_root).expanduser().resolve()
    config_path = Path(args.config).expanduser().resolve() if args.config else (runner_root / "projects.json")
    project_root = Path(args.project_path).expanduser().resolve()

    if not project_root.exists():
        raise SystemExit(f"Project path does not exist: {project_root}")

    ensure_git_repo(project_root)

    project_name = args.name or project_root.name
    goal = normalize_goal(args.goal)
    review_docs = detect_review_docs(project_root, args.review)
    progress_rel = args.progress_path
    progress_path = project_root / progress_rel
    agents_path = project_root / "AGENTS.md"

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = load_or_init_config(config_path)

    prompt = render_prompt(goal, review_docs, progress_rel)
    entry = {
        "name": project_name,
        "path": str(project_root),
        "prompt": prompt,
        "profile": args.profile,
        "max_passes": 0,
        "resume_existing": True,
        "enabled": True,
        "extra_args": [],
    }
    config, action = upsert_project(config, entry)
    config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    managed_block = render_managed_agents_block(goal, review_docs, progress_rel)
    write_agents_file(agents_path, managed_block)
    create_progress_log(progress_path, project_name, goal, review_docs)

    print(f"{action.capitalize()} autonomous project: {project_name}")
    print(f"Runner config: {config_path}")
    print(f"Repo AGENTS: {agents_path}")
    print(f"Progress log: {progress_path}")
    print("")
    print("Next step:")
    print(f"  continuum start {project_name}")
    print(f"  continuum service start {project_name}")
    print("  or")
    print(f"  cd {runner_root}")
    print(f"  ./launch_project.sh {project_name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
