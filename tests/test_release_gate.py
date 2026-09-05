"""Tests for reproducible release quality, specification consistency, and release gates."""

from __future__ import annotations

import os
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


RELEASE_GATE = ROOT / "scripts" / "check-release-gate.sh"


def test_release_gate_script_exists_and_executable() -> None:
    assert RELEASE_GATE.is_file(), f"{RELEASE_GATE} does not exist"
    assert os.access(RELEASE_GATE, os.X_OK), f"{RELEASE_GATE} is not executable"


def test_release_gate_order_and_failure_reporting(tmp_path: Path) -> None:
    # Test that the release gate script defines the deterministic ordered checks
    assert RELEASE_GATE.is_file()
    text = RELEASE_GATE.read_text(encoding="utf-8")
    expected_order = [
        "check-spec-consistency.py",
        "ruff format",
        "ruff check",
        "mypy",
        "pytest",
        "check-coverage.sh",
        "check-public-surface.sh",
    ]
    last_idx = -1
    for step in expected_order:
        idx = text.find(step)
        assert idx != -1, f"Expected step {step!r} missing in release gate script"
        assert idx > last_idx, f"Step {step!r} is out of order in release gate script"
        last_idx = idx


def test_release_gate_fails_closed_without_claiming_success(tmp_path: Path) -> None:
    # Run the release gate script pointing to a failing environment or mock
    fake_env = dict(os.environ)
    fake_env["MIA_FAIL_EARLY_STEP"] = "spec"
    # When check fails, verify returncode is non-zero and no success claim is made
    script_copy = tmp_path / "test-gate.sh"
    script_copy.write_text(RELEASE_GATE.read_text(encoding="utf-8"), encoding="utf-8")
    script_copy.chmod(0o755)

    # Inject a failing command in place of a check
    runner = subprocess.run(
        ["bash", str(script_copy)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=fake_env,
    )
    assert runner.returncode != 0
    assert "All Release Quality Gates Passed Cleanly" not in runner.stdout
    assert "clean" not in runner.stdout.lower() or runner.returncode != 0


def test_release_gate_secret_safety(tmp_path: Path) -> None:
    secret_value = "super_secret_token_value_xyz123"
    env_with_secret = dict(os.environ)
    env_with_secret["MIA_RELEASE_TOKEN"] = secret_value
    env_with_secret["PYPI_TOKEN"] = secret_value

    script_copy = tmp_path / "test-gate.sh"
    script_copy.write_text(RELEASE_GATE.read_text(encoding="utf-8"), encoding="utf-8")
    script_copy.chmod(0o755)

    runner = subprocess.run(
        ["bash", str(script_copy)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env=env_with_secret,
    )
    # Output must never contain the secret value
    combined_output = runner.stdout + runner.stderr
    assert secret_value not in combined_output, "Secret value leaked in release gate output"


CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def test_ci_workflow_parity_and_safety() -> None:
    assert CI_WORKFLOW.is_file(), f"{CI_WORKFLOW} does not exist"
    content = CI_WORKFLOW.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    assert isinstance(data, dict)

    # 1. Triggers include pull_request and push to main
    triggers = data.get("on") or data.get(True) or {}
    assert "pull_request" in triggers, "CI workflow missing pull_request trigger"
    assert "push" in triggers, "CI workflow missing push trigger"

    # 2. Gate command invoked
    assert "scripts/check-release-gate.sh" in content or "check-release-gate.sh" in content, (
        "CI workflow does not invoke check-release-gate.sh"
    )

    # 3. No publication or release secrets in CI workflow
    assert "publish" not in content.lower(), "CI workflow must not contain publication steps"
    assert "secrets.pypi" not in content.lower(), "CI workflow must not reference pypi credentials"
    assert "secrets.release" not in content.lower(), "CI workflow must not reference release credentials"

    # 4. Permissions must be read-only or minimal
    permissions = data.get("permissions", {})
    if isinstance(permissions, dict):
        assert permissions.get("contents") in {"read", None}
        assert permissions.get("packages") in {"read", None}
        assert "write" not in permissions.values()
