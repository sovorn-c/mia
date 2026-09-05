#!/usr/bin/env python3
"""Validate repository specification consistency across release-plan, execution-status, and epic capsules."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


def _load_yaml(path: Path, errors: list[str]) -> Any:
    try:
        content = path.read_text(encoding="utf-8")
        return yaml.safe_load(content)
    except yaml.YAMLError as exc:
        errors.append(f"YAML syntax error in {path}: {exc}")
        return None
    except Exception as exc:
        errors.append(f"Failed to read {path}: {exc}")
        return None


def check_spec_consistency(repo_root: Path) -> list[str]:
    errors: list[str] = []
    specs_dir = repo_root / "specs"

    if not specs_dir.is_dir():
        return [f"specs directory not found at {specs_dir}"]

    # 1. Parse all YAML files in specs/ for syntax errors
    for yf in sorted(specs_dir.rglob("*.yaml")) + sorted(specs_dir.rglob("*.yml")):
        # Skip hidden or temporary files if any
        if yf.name.startswith("."):
            continue
        try:
            yaml.safe_load(yf.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            errors.append(f"YAML syntax error in {yf.relative_to(repo_root)}: {exc}")

    if errors:
        return errors

    release_plan_path = specs_dir / "release-plan.yaml"
    execution_status_path = specs_dir / "execution-status.yaml"

    if not release_plan_path.is_file():
        errors.append(f"Missing release-plan at {release_plan_path}")
        return errors
    if not execution_status_path.is_file():
        errors.append(f"Missing execution-status at {execution_status_path}")
        return errors

    release_plan = _load_yaml(release_plan_path, errors) or {}
    execution_status = _load_yaml(execution_status_path, errors) or {}

    if errors:
        return errors

    # 2. Version validation
    rp_version = str(release_plan.get("version", ""))
    es_version = str(execution_status.get("version", ""))
    if rp_version and es_version and rp_version != es_version:
        errors.append(
            f"Version mismatch: release-plan has {rp_version!r} but execution-status has {es_version!r}"
        )

    # 3. Epic inventory and consistency
    rp_epics = release_plan.get("epics") or []
    if not isinstance(rp_epics, list):
        errors.append("release-plan.yaml: 'epics' must be a list")
        return errors

    seen_epic_ids: set[str] = set()
    rp_epic_map: dict[str, dict[str, Any]] = {}

    for epic_entry in rp_epics:
        if not isinstance(epic_entry, dict):
            errors.append("release-plan.yaml: each epic entry must be a dictionary")
            continue
        eid = epic_entry.get("id")
        if not eid:
            errors.append("release-plan.yaml: epic entry missing 'id'")
            continue
        if eid in seen_epic_ids:
            errors.append(f"Duplicate epic ID {eid!r} found in release-plan.yaml")
        seen_epic_ids.add(eid)
        rp_epic_map[eid] = epic_entry

    es_epics = execution_status.get("epics") or {}
    if not isinstance(es_epics, dict):
        errors.append("execution-status.yaml: 'epics' must be a mapping")
        es_epics = {}

    # Check that execution_status does not contain duplicate or unknown epics
    for eid in es_epics:
        if eid not in seen_epic_ids:
            errors.append(f"execution-status.yaml contains epic {eid!r} not in release-plan.yaml")

    # 4. Dependency validation and status drift
    satisfied_statuses = {"completed", "passing", "done"}
    for eid, rp_epic in rp_epic_map.items():
        es_epic = es_epics.get(eid)
        if not es_epic:
            errors.append(f"Epic {eid!r} in release-plan is missing from execution-status.yaml")
            continue

        rp_status = str(rp_epic.get("status", "")).strip().lower()
        es_status = str(es_epic.get("status", "")).strip().lower()

        # Status drift: e.g. planned in one, completed/passing in another
        if (rp_status == "planned" and es_status in satisfied_statuses) or (
            es_status == "planned" and rp_status in satisfied_statuses
        ):
            errors.append(
                f"Status drift for epic {eid!r}: release-plan has {rp_status!r} but execution-status has {es_status!r}"
            )

        # BCP drift between release plan and execution status
        rp_bcps = rp_epic.get("bcps")
        es_bcps = es_epic.get("bcps")
        if es_bcps is not None and rp_bcps is not None and es_bcps != rp_bcps:
            errors.append(
                f"BCP drift for epic {eid!r}: release-plan has {rp_bcps} but execution-status has {es_bcps}"
            )

        # Dependencies validation
        depends_on = rp_epic.get("depends_on") or []
        for dep in depends_on:
            if dep not in seen_epic_ids:
                errors.append(f"Epic {eid!r} depends on unknown epic {dep!r}")
            elif rp_status in satisfied_statuses:
                dep_status = str(rp_epic_map[dep].get("status", "")).strip().lower()
                if dep_status not in satisfied_statuses:
                    errors.append(
                        f"Dependency unsatisfied: epic {eid!r} ({rp_status}) depends on {dep!r} ({dep_status})"
                    )

    # 5. Capsule validation
    seen_story_ids: set[str] = set()
    for eid, rp_epic in rp_epic_map.items():
        capsule_rel = rp_epic.get("capsule_dir")
        if not capsule_rel:
            errors.append(f"Epic {eid!r} missing 'capsule_dir' in release-plan.yaml")
            continue

        capsule_dir = repo_root / capsule_rel
        if not capsule_dir.is_dir():
            errors.append(f"Capsule directory missing for epic {eid!r}: {capsule_rel}")
            continue

        epic_yaml_path = capsule_dir / "epic.yaml"
        if not epic_yaml_path.is_file():
            errors.append(
                f"Missing epic.yaml for epic {eid!r} at {epic_yaml_path.relative_to(repo_root)}"
            )
            continue

        epic_data = _load_yaml(epic_yaml_path, errors)
        if not isinstance(epic_data, dict):
            continue

        ey_id = epic_data.get("id")
        if ey_id != eid:
            errors.append(
                f"Epic manifest ID mismatch at {epic_yaml_path.relative_to(repo_root)}: expected {eid!r}, got {ey_id!r}"
            )

        stories = epic_data.get("stories") or []
        story_bcp_sum = 0

        for story in stories:
            if not isinstance(story, dict):
                errors.append(
                    f"{epic_yaml_path.relative_to(repo_root)}: story entry must be a dictionary"
                )
                continue

            sid = story.get("id")
            if not sid:
                errors.append(f"{epic_yaml_path.relative_to(repo_root)}: story entry missing 'id'")
                continue

            if sid in seen_story_ids:
                errors.append(f"Duplicate story ID {sid!r} across epics")
            seen_story_ids.add(sid)

            s_bcps = story.get("bcps", 0)
            if isinstance(s_bcps, int):
                story_bcp_sum += s_bcps

            # Spec file
            spec_file_name = story.get("spec_file")
            if spec_file_name:
                spec_path = capsule_dir / spec_file_name
                if not spec_path.is_file():
                    errors.append(
                        f"Missing spec file {spec_file_name!r} for story {sid!r} in {capsule_dir.relative_to(repo_root)}"
                    )

            # Task ledger
            tasks_file_name = story.get("tasks_file") or f"{sid}-tasks.yaml"
            tasks_path = capsule_dir / tasks_file_name
            if not tasks_path.is_file():
                errors.append(
                    f"Missing tasks file {tasks_file_name!r} for story {sid!r} in {capsule_dir.relative_to(repo_root)}"
                )
            else:
                tasks_data = _load_yaml(tasks_path, errors)
                if isinstance(tasks_data, dict):
                    task_story_id = tasks_data.get("story_id")
                    if task_story_id and task_story_id != sid:
                        errors.append(
                            f"Task ledger {tasks_path.relative_to(repo_root)} story_id mismatch: expected {sid!r}, got {task_story_id!r}"
                        )
                    tasks_list = tasks_data.get("tasks") or []
                    if not isinstance(tasks_list, list) or len(tasks_list) == 0:
                        errors.append(
                            f"Task ledger {tasks_path.relative_to(repo_root)} has no tasks"
                        )
                    else:
                        for t in tasks_list:
                            if not isinstance(t, dict):
                                continue
                            tid = t.get("id", "")
                            t_verify = str(t.get("verify", "")).strip()
                            if not t_verify:
                                errors.append(
                                    f"Task {tid!r} in {tasks_path.relative_to(repo_root)} has missing or empty verify command"
                                )

        # BCP consistency check
        expected_bcps = epic_data.get("total_bcps") or epic_data.get("bcps") or rp_epic.get("bcps")
        if expected_bcps is not None and story_bcp_sum > 0 and story_bcp_sum != expected_bcps:
            errors.append(
                f"BCP sum drift in epic {eid!r}: stories sum to {story_bcp_sum} but epic declares {expected_bcps}"
            )

    return errors


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors = check_spec_consistency(repo_root)
    if errors:
        print(f"specification consistency: {len(errors)} error(s) found:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("specification consistency: clean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
