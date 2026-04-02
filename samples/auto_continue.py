#!/usr/bin/env python3
"""Codex Stop hook: auto-continue only when the assistant explicitly says STATUS: CONTINUE.

Install to: ~/.codex/hooks/auto_continue.py
Pair with:  ~/.codex/hooks.json
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

CONTINUE_RE = re.compile(r"^STATUS:\s*CONTINUE\s*$", re.MULTILINE)
DONE_RE = re.compile(r"^STATUS:\s*DONE\s*$", re.MULTILINE)
BLOCKED_RE = re.compile(r"^STATUS:\s*BLOCKED:\s*.+$", re.MULTILINE)

FOLLOWUP_PROMPT = (
    "Proceed with the project. Continue from your last checkpoint. "
    "Update the project notes/progress log. Choose the next highest-value task yourself. "
    "Only stop when you are actually DONE or BLOCKED. "
    "End with exactly one status line: STATUS: CONTINUE, STATUS: DONE, or STATUS: BLOCKED: <reason>."
)


def emit(payload: dict[str, Any]) -> int:
    print(json.dumps(payload))
    return 0


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception as exc:  # pragma: no cover
        return emit({"continue": False, "stopReason": f"Hook input parse failure: {exc}"})

    last_message = (data.get("last_assistant_message") or "").strip()

    if CONTINUE_RE.search(last_message):
        return emit(
            {
                "decision": "block",
                "reason": FOLLOWUP_PROMPT,
            }
        )

    if DONE_RE.search(last_message) or BLOCKED_RE.search(last_message):
        return emit({"continue": False, "stopReason": "terminal status reached"})

    return emit({"continue": False})


if __name__ == "__main__":
    raise SystemExit(main())
