#!/usr/bin/env python3
"""Check that the built wheel exposes the retained public package surface."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from zipfile import ZipFile

REQUIRED_PREFIXES = ("mia_cli/tui/",)
FORBIDDEN_PREFIXES = (
    "mia_agent/profiles/",
    "mia_agent/profiles.py",
    "mia_agent/herd/",
    "mia_agent/herd.py",
    "mia_agent/mode_runtime.py",
    "mia_agent/orchestration.py",
    "mia_agent/orchestration/",
    "mia_agent/orchestration_events.py",
    "mia_agent/orchestration_models.py",
    "mia_agent/agents/legacy.py",
    "mia_agent/agents/legacy/",
    "mia_agent/legacy.py",
)
FORBIDDEN_TEXT = re.compile(
    r"\b(AgentProfile|ProfileManager|ModeRuntime|ModeCatalog|WorkflowStage|"
    r"HerdManager|ManagedAgent|AgentState|MiaHerdApp|HerdEvent|"
    r"InvokeSubagentTool|OrchestrationEventEnvelope|OrchestrationErrorEvent)\b|"
    r"mia_agent\.(profiles|herd|orchestration(_events|_models)?)|"
    r"--profile\b|/profile([^A-Za-z0-9_-]|$)|--mode\b|"
    r"/mode([^A-Za-z0-9_-]|$)|code_mode\b"
)


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: check-wheel-surface.py WHEEL", file=sys.stderr)
        return 2
    wheel_path = Path(sys.argv[1])
    if not wheel_path.is_file():
        print(f"wheel not found: {wheel_path}", file=sys.stderr)
        return 2

    with ZipFile(wheel_path) as wheel:
        names = wheel.namelist()
        missing = [
            prefix
            for prefix in REQUIRED_PREFIXES
            if not any(name.startswith(prefix) for name in names)
        ]
        forbidden = [
            prefix
            for prefix in FORBIDDEN_PREFIXES
            if any(name.startswith(prefix) for name in names)
        ]
        if missing or forbidden:
            if missing:
                print(f"required wheel paths missing: {', '.join(missing)}", file=sys.stderr)
            if forbidden:
                print(f"forbidden wheel paths found: {', '.join(forbidden)}", file=sys.stderr)
            return 1

        for name in names:
            if name.endswith((".py", "entry_points.txt")):
                text = wheel.read(name).decode("utf-8", errors="replace")
                if FORBIDDEN_TEXT.search(text):
                    print(f"retired public surface found in: {name}", file=sys.stderr)
                    return 1

    print("wheel surface: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
