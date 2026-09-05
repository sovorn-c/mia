"""Tests for authorized publication, dry-run, failure evidence, and supersession procedure."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).parents[1]
RELEASE_SCRIPT = ROOT / "scripts" / "release.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
RELEASE_GUIDE = ROOT / "docs" / "release-guide.md"
RELEASE_NOTES = ROOT / "RELEASE_NOTES.md"


def _create_synthetic_dist(dist_dir: Path, version: str = "0.6.0") -> tuple[Path, Path]:
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = dist_dir / f"mia_ai-{version}-py3-none-any.whl"
    sdist_path = dist_dir / f"mia_ai-{version}.tar.gz"

    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mia_cli/tui/__init__.py", "# tui\n")
        zf.writestr("mia_agent/__init__.py", f"__version__ = '{version}'\n")
        zf.writestr("mia_agent/plugin_models.py", "CORE_PLUGIN_API_VERSION = 1\n")
        zf.writestr(
            f"mia_ai-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: mia-ai\nVersion: {version}\n",
        )
        zf.writestr(
            f"mia_ai-{version}.dist-info/entry_points.txt",
            "[console_scripts]\nmia = mia_cli.main:app\n",
        )

    with tarfile.open(sdist_path, "w:gz") as tf:
        info = tarfile.TarInfo(f"mia_ai-{version}/pyproject.toml")
        data = f'[project]\nname = "mia-ai"\nversion = "{version}"\n'.encode()
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

    return sdist_path, wheel_path


def _generate_manifest_for(dist_dir: Path, version: str = "0.6.0", ref: str = "abc1234") -> Path:
    import hashlib

    def _h(p: Path) -> str:
        return hashlib.sha256(p.read_bytes()).hexdigest()

    artifacts: list[dict[str, Any]] = []
    for f in sorted(dist_dir.iterdir()):
        if f.name.endswith(".whl"):
            artifacts.append(
                {
                    "name": f.name,
                    "type": "wheel",
                    "version": version,
                    "size": f.stat().st_size,
                    "sha256": _h(f),
                }
            )
        elif f.name.endswith(".tar.gz"):
            artifacts.append(
                {
                    "name": f.name,
                    "type": "sdist",
                    "version": version,
                    "size": f.stat().st_size,
                    "sha256": _h(f),
                }
            )

    manifest = {
        "version": version,
        "source_ref": ref,
        "lock_hash": "deadbeef1234",
        "artifacts": artifacts,
    }
    manifest_path = dist_dir / "release-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path


def _run_release(
    args: list[str],
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    base_env = os.environ.copy()
    if env:
        base_env.update(env)
    return subprocess.run(
        [sys.executable, str(RELEASE_SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=str(cwd or ROOT),
        env=base_env,
    )


def test_release_script_exists_and_executable() -> None:
    assert RELEASE_SCRIPT.is_file(), f"{RELEASE_SCRIPT} does not exist"
    assert os.access(RELEASE_SCRIPT, os.X_OK), f"{RELEASE_SCRIPT} is not executable"


def test_dry_run_success_with_valid_candidate(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--skip-gate-check",
        ]
    )
    assert res.returncode == 0, f"STDOUT: {res.stdout}\nSTDERR: {res.stderr}"
    assert "candidate verified" in res.stdout.lower() or "dry run" in res.stdout.lower()


def test_refusal_when_unauthorized(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    clean_env = {k: v for k, v in os.environ.items() if not k.startswith("MIA_RELEASE_")}
    clean_env["MIA_RELEASE_AUTHORIZED"] = ""
    res = _run_release(
        [
            "publish",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--skip-gate-check",
        ],
        env=clean_env,
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "authorization" in combined or "unauthorized" in combined or "refused" in combined


def test_refusal_on_version_mismatch(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.7.0",
            "--ref",
            "mockref123",
            "--skip-gate-check",
        ]
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "version mismatch" in combined or "mismatch" in combined


def test_refusal_on_ref_mismatch(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "different_ref_456",
            "--skip-gate-check",
        ]
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "ref mismatch" in combined or "mismatch" in combined


def test_refusal_on_stale_or_corrupted_artifact_mismatch(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _, wheel = _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    with wheel.open("ab") as f:
        f.write(b"\n# corrupted payload\n")

    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--skip-gate-check",
        ]
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "mismatch" in combined or "hash" in combined or "integrity" in combined


def test_refusal_on_missing_gate_evidence(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    missing_gate_file = tmp_path / "nonexistent-gate.json"
    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--gate-evidence",
            str(missing_gate_file),
        ]
    )
    assert res.returncode != 0
    combined = (res.stdout + res.stderr).lower()
    assert "gate" in combined or "evidence" in combined


def test_secret_safety_no_tokens_or_credentials_in_output(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    secret_val = "SECRET_PYPI_TOKEN_abc123xyz789"
    env = {
        "UV_PUBLISH_TOKEN": secret_val,
        "PYPI_PASSWORD": secret_val,
        "MIA_RELEASE_AUTHORIZED": "0",
    }
    res = _run_release(
        [
            "publish",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--skip-gate-check",
        ],
        env=env,
    )
    assert secret_val not in res.stdout
    assert secret_val not in res.stderr


def test_publish_failure_preserves_artifacts_and_records_evidence(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    sdist, wheel = _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")
    evidence_dir = tmp_path / "evidence"

    res = _run_release(
        [
            "publish",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--authorized",
            "--skip-gate-check",
            "--evidence-dir",
            str(evidence_dir),
            "--simulate-failure",
            "network",
        ]
    )
    assert res.returncode != 0
    assert sdist.is_file(), "sdist was deleted on failure"
    assert wheel.is_file(), "wheel was deleted on failure"

    evidence_file = evidence_dir / "release-attempt.json"
    assert evidence_file.is_file(), f"Evidence file not found: {evidence_file}"
    data = json.loads(evidence_file.read_text(encoding="utf-8"))
    assert data["status"] == "failed"
    assert data["version"] == "0.6.0"
    assert "recovery_recommendation" in data or "recovery_action" in data


def test_publish_failure_classifies_recovery_retry_withdraw_supersede(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")
    evidence_dir = tmp_path / "evidence"

    for failure_mode, expected_recovery in [
        ("network", "RETRY"),
        ("partial", "WITHDRAW"),
        ("conflict", "SUPERSEDE"),
    ]:
        res = _run_release(
            [
                "publish",
                "--dist-dir",
                str(dist),
                "--version",
                "0.6.0",
                "--ref",
                "mockref123",
                "--authorized",
                "--skip-gate-check",
                "--evidence-dir",
                str(evidence_dir),
                "--simulate-failure",
                failure_mode,
            ]
        )
        assert res.returncode != 0
        evidence_file = evidence_dir / "release-attempt.json"
        data = json.loads(evidence_file.read_text(encoding="utf-8"))
        rec = data.get("recovery_action") or data.get("recovery_recommendation", "")
        assert expected_recovery in rec


def test_failure_handling_never_deletes_tags_or_artifacts(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    sdist, wheel = _create_synthetic_dist(dist, "0.6.0")
    manifest = _generate_manifest_for(dist, "0.6.0", ref="mockref123")
    evidence_dir = tmp_path / "evidence"

    _run_release(
        [
            "publish",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
            "--authorized",
            "--skip-gate-check",
            "--evidence-dir",
            str(evidence_dir),
            "--simulate-failure",
            "partial",
        ]
    )
    assert sdist.exists()
    assert wheel.exists()
    assert manifest.exists()


def test_workflow_release_yml_protected_and_manual() -> None:
    assert WORKFLOW_PATH.is_file(), f"{WORKFLOW_PATH} does not exist"
    content = WORKFLOW_PATH.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    triggers = data.get("on") or data.get(True) or {}
    if isinstance(triggers, (list, dict)):
        assert "workflow_dispatch" in triggers
        assert "push" not in triggers
        assert "pull_request" not in triggers
    else:
        assert triggers == "workflow_dispatch"

    assert "scripts/release.py" in content or "check-release-gate.sh" in content


def test_release_notes_exists_and_documents_scope_and_compatibility() -> None:
    assert RELEASE_NOTES.is_file(), f"{RELEASE_NOTES} does not exist"
    notes = RELEASE_NOTES.read_text(encoding="utf-8")
    assert "0.6.0" in notes
    assert "plugin" in notes.lower()
    assert "unsandboxed" in notes.lower() or "trusted" in notes.lower()


def test_release_documentation_operator_guide_and_links() -> None:
    assert RELEASE_GUIDE.is_file(), f"{RELEASE_GUIDE} does not exist"
    guide = RELEASE_GUIDE.read_text(encoding="utf-8")
    lower = guide.lower()
    assert "authorization" in lower
    assert "dry-run" in lower or "dry run" in lower
    assert "withdraw" in lower
    assert "supersede" in lower or "supersession" in lower
    assert "evidence" in lower
    assert "scripts/release.py" in guide
    assert "scripts/check-release-gate.sh" in guide
    assert "scripts/check-artifact-integrity.py" in guide


def test_verify_candidate_rejects_unconfined_artifact_names(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    manifest_path = dist / "release-manifest.json"

    # Create manifest with path traversal artifact name
    manifest_data = {
        "version": "0.6.0",
        "source_ref": "mockref123",
        "artifacts": [
            {
                "name": "../outside/mia_ai-0.6.0-escaped.whl",
                "type": "wheel",
                "version": "0.6.0",
                "size": 100,
                "sha256": "abcdef",
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--skip-gate-check",
        ]
    )
    assert res.returncode != 0
    assert (
        "traversal" in res.stderr.lower()
        or "escape" in res.stderr.lower()
        or "confined" in res.stderr.lower()
    )


def test_verify_candidate_requires_gate_evidence_when_not_skipped(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")

    # Without --skip-gate-check and without gate-evidence, verify must fail closed
    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
        ]
    )
    assert res.returncode != 0
    assert (
        "gate evidence missing" in res.stderr.lower()
        or "release gate evidence" in res.stderr.lower()
    )


def test_verify_candidate_rejects_failing_or_mismatched_gate_evidence(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    _create_synthetic_dist(dist, "0.6.0")
    _generate_manifest_for(dist, "0.6.0", ref="mockref123")
    evidence_file = dist / "release-gate-evidence.json"

    # 1. Failing status in gate evidence
    evidence_file.write_text(
        json.dumps({"status": "failed", "version": "0.6.0", "source_ref": "mockref123"}),
        encoding="utf-8",
    )
    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
        ]
    )
    assert res.returncode != 0
    assert "failing gate" in res.stderr.lower()

    # 2. Mismatched version in gate evidence
    evidence_file.write_text(
        json.dumps({"status": "passed", "version": "0.5.0", "source_ref": "mockref123"}),
        encoding="utf-8",
    )
    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
        ]
    )
    assert res.returncode != 0
    assert "version mismatch" in res.stderr.lower()

    # 3. Mismatched source_ref in gate evidence
    evidence_file.write_text(
        json.dumps({"status": "passed", "version": "0.6.0", "source_ref": "unmatched_ref"}),
        encoding="utf-8",
    )
    res = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
        ]
    )
    assert res.returncode != 0
    assert "source_ref mismatch" in res.stderr.lower()

    # 4. Valid gate evidence matching version and ref succeeds
    evidence_file.write_text(
        json.dumps({"status": "passed", "version": "0.6.0", "source_ref": "mockref123"}),
        encoding="utf-8",
    )
    res_ok = _run_release(
        [
            "verify",
            "--dist-dir",
            str(dist),
            "--version",
            "0.6.0",
            "--ref",
            "mockref123",
        ]
    )
    assert res_ok.returncode == 0
    assert "candidate verified" in res_ok.stdout.lower()
