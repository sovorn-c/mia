#!/usr/bin/env bash
# Seed missing epic/story entries in specs/execution-status.yaml from epic capsules.
# Existing status values remain authoritative; this script only adds missing entries
# and refreshes descriptive fields/task counters.
set -euo pipefail
source "$(dirname "${BASH_SOURCE[0]}")/lib/python-env.sh"

"$PYTHON" - <<'PY'
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

specs = Path("specs")
status_path = specs / "execution-status.yaml"
release_path = specs / "release-plan.yaml"

status: dict[str, Any]
if status_path.exists():
    loaded = yaml.safe_load(status_path.read_text(encoding="utf-8")) or {}
    status = loaded if isinstance(loaded, dict) else {}
else:
    status = {}

release = yaml.safe_load(release_path.read_text(encoding="utf-8")) or {}
status["version"] = str(release.get("version", status.get("version", "0.0.0")))
status["updated_at"] = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
epics_out = status.setdefault("epics", {})

for epic_path in sorted((specs / "epics").glob("e*/epic.yaml")):
    epic = yaml.safe_load(epic_path.read_text(encoding="utf-8")) or {}
    epic_id = epic.get("id")
    if not epic_id:
        continue

    epic_out = epics_out.setdefault(epic_id, {})
    epic_out["title"] = epic.get("title", epic_out.get("title", ""))
    epic_out.setdefault("status", epic.get("status", "planned"))
    stories_out = epic_out.setdefault("stories", {})

    for story in epic.get("stories") or []:
        if not isinstance(story, dict) or not story.get("id"):
            continue
        story_id = str(story["id"])
        story_out = stories_out.setdefault(story_id, {})
        story_out["title"] = story.get("title", story_out.get("title", ""))
        story_out.setdefault("status", story.get("status", "failing"))
        if story.get("bcps") is not None:
            story_out["bcps"] = story["bcps"]
        if story.get("risk") is not None:
            story_out["risk"] = story["risk"]

        tasks_name = story.get("tasks_file") or f"{story_id}-tasks.yaml"
        tasks_path = epic_path.parent / str(tasks_name)
        if not tasks_path.exists():
            continue
        tasks_doc = yaml.safe_load(tasks_path.read_text(encoding="utf-8")) or {}
        tasks = [task for task in tasks_doc.get("tasks") or [] if isinstance(task, dict)]
        story_out["tasks_total"] = len(tasks)
        story_out["tasks_passing"] = sum(
            task.get("status") in {"passing", "completed", "done"} for task in tasks
        )
        story_out["tasks_failing"] = sum(task.get("status") == "failing" for task in tasks)

status_path.write_text(
    "# specs/execution-status.yaml — Generated status index; existing statuses remain authoritative\n"
    + yaml.safe_dump(status, sort_keys=False, allow_unicode=True, width=100),
    encoding="utf-8",
)
print(f"sync-status-from-epics: wrote {status_path}")
PY
