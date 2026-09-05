"""Tests for reproducible release quality, specification consistency, and release gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]
SPEC_CHECKER = ROOT / "scripts" / "check-spec-consistency.py"


def _create_minimal_spec_tree(base: Path) -> dict[str, Path]:
    """Create a minimal valid specification fixture tree in base."""
    specs_dir = base / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    capsule_dir = specs_dir / "epics" / "e01-test"
    capsule_dir.mkdir(parents=True, exist_ok=True)

    release_plan = {
        "version": "0.6.0",
        "target_release": "v0.6.0-test",
        "release": {
            "version": "0.6.0",
            "status": "planned",
        },
        "epics": [
            {
                "id": "e01",
                "slug": "test",
                "title": "Test Epic",
                "status": "planned",
                "capsule_dir": "specs/epics/e01-test",
                "depends_on": [],
                "bcps": 4,
            }
        ],
    }
    (specs_dir / "release-plan.yaml").write_text(yaml.safe_dump(release_plan), encoding="utf-8")

    execution_status = {
        "version": "0.6.0",
        "epics": {
            "e01": {
                "title": "Test Epic",
                "status": "planned",
                "bcps": 4,
                "stories": {
                    "e01s01": {
                        "title": "Test Story",
                        "status": "planned",
                        "bcps": 4,
                    }
                },
            }
        },
    }
    (specs_dir / "execution-status.yaml").write_text(
        yaml.safe_dump(execution_status), encoding="utf-8"
    )

    epic_yaml = {
        "id": "e01",
        "slug": "test",
        "title": "Test Epic",
        "status": "planned",
        "target_version": "0.6.0",
        "total_bcps": 4,
        "depends_on": [],
        "stories": [
            {
                "id": "e01s01",
                "title": "Test Story",
                "status": "planned",
                "bcps": 4,
                "spec_file": "e01s01-test.md",
                "tasks_file": "e01s01-tasks.yaml",
                "depends_on": [],
            }
        ],
    }
    (capsule_dir / "epic.yaml").write_text(yaml.safe_dump(epic_yaml), encoding="utf-8")

    tasks_yaml = {
        "story_id": "e01s01",
        "title": "Test Story",
        "spec": "e01s01-test.md",
        "status": "failing",
        "bcps": 4,
        "tasks": [
            {
                "id": "e01s01t01",
                "title": "Task 1",
                "status": "failing",
                "verify": "echo ok",
            }
        ],
    }
    (capsule_dir / "e01s01-tasks.yaml").write_text(yaml.safe_dump(tasks_yaml), encoding="utf-8")
    (capsule_dir / "e01s01-test.md").write_text("# e01s01 test\n", encoding="utf-8")

    return {
        "root": base,
        "specs_dir": specs_dir,
        "capsule_dir": capsule_dir,
        "release_plan": specs_dir / "release-plan.yaml",
        "execution_status": specs_dir / "execution-status.yaml",
        "epic_yaml": capsule_dir / "epic.yaml",
        "tasks_yaml": capsule_dir / "e01s01-tasks.yaml",
    }


def _run_spec_checker(repo_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SPEC_CHECKER), str(repo_path)],
        capture_output=True,
        text=True,
    )


def test_spec_consistency_valid_fixture(tmp_path: Path) -> None:
    _create_minimal_spec_tree(tmp_path)
    result = _run_spec_checker(tmp_path)
    assert result.returncode == 0, f"Expected 0, got {result.returncode}: {result.stderr}"
    assert "specification consistency: clean" in result.stdout.lower() or result.returncode == 0


def test_spec_consistency_real_repo() -> None:
    result = _run_spec_checker(ROOT)
    assert result.returncode == 0, (
        f"Repository spec consistency failed:\n{result.stderr}\n{result.stdout}"
    )


def test_spec_consistency_rejects_malformed_yaml(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    paths["release_plan"].write_text("invalid: [yaml: broken", encoding="utf-8")
    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "yaml" in result.stderr.lower() or "syntax" in result.stderr.lower()


def test_spec_consistency_rejects_duplicate_epic_id(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["release_plan"].read_text(encoding="utf-8"))
    data["epics"].append(dict(data["epics"][0]))
    paths["release_plan"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "duplicate" in result.stderr.lower()


def test_spec_consistency_rejects_missing_capsule_dir(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["release_plan"].read_text(encoding="utf-8"))
    data["epics"][0]["capsule_dir"] = "specs/epics/nonexistent"
    paths["release_plan"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "capsule" in result.stderr.lower() or "missing" in result.stderr.lower()


def test_spec_consistency_rejects_bcp_drift(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["epic_yaml"].read_text(encoding="utf-8"))
    data["stories"][0]["bcps"] = 99
    paths["epic_yaml"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "bcp" in result.stderr.lower()


def test_spec_consistency_rejects_status_drift(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["execution_status"].read_text(encoding="utf-8"))
    data["epics"]["e01"]["status"] = "completed"
    paths["execution_status"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "status" in result.stderr.lower()


def test_spec_consistency_rejects_invalid_dependency(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["release_plan"].read_text(encoding="utf-8"))
    data["epics"][0]["depends_on"] = ["e99"]
    paths["release_plan"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "depend" in result.stderr.lower()


def test_spec_consistency_rejects_missing_task_verify(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    data = yaml.safe_load(paths["tasks_yaml"].read_text(encoding="utf-8"))
    data["tasks"][0]["verify"] = ""
    paths["tasks_yaml"].write_text(yaml.safe_dump(data), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode != 0
    assert "verify" in result.stderr.lower()


def test_spec_consistency_distinguishes_archived_capsules(tmp_path: Path) -> None:
    paths = _create_minimal_spec_tree(tmp_path)
    archive_capsule = tmp_path / "specs" / "epics" / "archive" / "e00-hist"
    archive_capsule.mkdir(parents=True, exist_ok=True)
    hist_epic = {
        "id": "e00",
        "slug": "hist",
        "title": "Historical Epic",
        "status": "completed",
        "target_version": "0.5.0",
        "total_bcps": 2,
        "depends_on": [],
        "stories": [
            {
                "id": "e00s01",
                "title": "Hist Story",
                "status": "completed",
                "bcps": 2,
                "tasks_file": "e00s01-tasks.yaml",
                "spec_file": "e00s01-hist.md",
            }
        ],
    }
    (archive_capsule / "epic.yaml").write_text(yaml.safe_dump(hist_epic), encoding="utf-8")
    (archive_capsule / "e00s01-tasks.yaml").write_text(
        yaml.safe_dump(
            {
                "story_id": "e00s01",
                "title": "Hist Story",
                "status": "passing",
                "bcps": 2,
                "tasks": [
                    {"id": "e00s01t01", "title": "T1", "status": "passing", "verify": "echo 1"}
                ],
            }
        ),
        encoding="utf-8",
    )
    (archive_capsule / "e00s01-hist.md").write_text("# hist\n", encoding="utf-8")

    rp = yaml.safe_load(paths["release_plan"].read_text(encoding="utf-8"))
    rp["epics"].insert(
        0,
        {
            "id": "e00",
            "slug": "hist",
            "title": "Historical Epic",
            "status": "completed",
            "capsule_dir": "specs/epics/archive/e00-hist",
            "depends_on": [],
            "bcps": 2,
        },
    )
    rp["epics"][1]["depends_on"] = ["e00"]
    paths["release_plan"].write_text(yaml.safe_dump(rp), encoding="utf-8")

    es = yaml.safe_load(paths["execution_status"].read_text(encoding="utf-8"))
    es["epics"]["e00"] = {
        "title": "Historical Epic",
        "status": "completed",
        "bcps": 2,
        "stories": {"e00s01": {"title": "Hist Story", "status": "completed", "bcps": 2}},
    }
    paths["execution_status"].write_text(yaml.safe_dump(es), encoding="utf-8")

    result = _run_spec_checker(tmp_path)
    assert result.returncode == 0, f"Failed on valid archive: {result.stderr}"
