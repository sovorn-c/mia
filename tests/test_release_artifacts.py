"""Tests for distribution artifact integrity, provenance, package surface, and clean install smoke."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
INTEGRITY_SCRIPT = ROOT / "scripts" / "check-artifact-integrity.py"


def _create_synthetic_dist(dist_dir: Path, version: str = "0.6.0") -> tuple[Path, Path]:
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = dist_dir / f"mia_ai-{version}-py3-none-any.whl"
    sdist_path = dist_dir / f"mia_ai-{version}.tar.gz"

    # Minimal valid wheel
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mia_cli/tui/__init__.py", "# tui\n")
        zf.writestr("mia_agent/__init__.py", "__version__ = '0.6.0'\n")
        zf.writestr("mia_agent/plugin_models.py", "CORE_PLUGIN_API_VERSION = 1\n")
        zf.writestr(
            f"mia_ai-{version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: mia-ai\nVersion: {version}\n",
        )
        zf.writestr(
            f"mia_ai-{version}.dist-info/entry_points.txt",
            "[console_scripts]\nmia = mia_cli.main:app\n",
        )

    # Minimal valid sdist
    with tarfile.open(sdist_path, "w:gz") as tf:
        info = tarfile.TarInfo(f"mia_ai-{version}/pyproject.toml")
        data = b'[project]\nname = "mia-ai"\nversion = "0.6.0"\n'
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data) if "io" in globals() else __import__("io").BytesIO(data))

    return sdist_path, wheel_path


def _run_integrity(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INTEGRITY_SCRIPT), *args],
        capture_output=True,
        text=True,
    )


def test_artifact_integrity_script_exists() -> None:
    assert INTEGRITY_SCRIPT.is_file(), f"{INTEGRITY_SCRIPT} does not exist"
    assert os.access(INTEGRITY_SCRIPT, os.X_OK), f"{INTEGRITY_SCRIPT} is not executable"


def test_artifact_manifest_generation_and_verification(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    sdist_path, wheel_path = _create_synthetic_dist(dist_dir)
    manifest_path = dist_dir / "artifacts-manifest.json"

    # Generate manifest
    gen_result = _run_integrity(
        [
            "generate",
            "--dist",
            str(dist_dir),
            "--manifest",
            str(manifest_path),
            "--version",
            "0.6.0",
        ]
    )
    assert gen_result.returncode == 0, f"Generate failed: {gen_result.stderr}"
    assert manifest_path.is_file()

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["version"] == "0.6.0"
    assert "artifacts" in manifest
    assert len(manifest["artifacts"]) == 2

    # Check each artifact in manifest has required fields: name, type, version, size, sha256
    names = {a["name"] for a in manifest["artifacts"]}
    assert wheel_path.name in names
    assert sdist_path.name in names

    for art in manifest["artifacts"]:
        assert "sha256" in art
        assert "size" in art
        assert "type" in art
        assert art["version"] == "0.6.0"

    # Verify manifest against artifacts
    ver_result = _run_integrity(
        ["verify", "--dist", str(dist_dir), "--manifest", str(manifest_path), "--version", "0.6.0"]
    )
    assert ver_result.returncode == 0, f"Verify failed: {ver_result.stderr}"
    assert "artifact integrity: clean" in ver_result.stdout.lower()


def test_artifact_tampering_rejected(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    sdist_path, wheel_path = _create_synthetic_dist(dist_dir)
    manifest_path = dist_dir / "artifacts-manifest.json"

    _run_integrity(
        [
            "generate",
            "--dist",
            str(dist_dir),
            "--manifest",
            str(manifest_path),
            "--version",
            "0.6.0",
        ]
    )

    # Tamper with the wheel file (append bytes)
    with open(wheel_path, "ab") as f:
        f.write(b"TAMPERED_EXTRA_DATA")

    ver_result = _run_integrity(
        ["verify", "--dist", str(dist_dir), "--manifest", str(manifest_path), "--version", "0.6.0"]
    )
    assert ver_result.returncode != 0
    assert (
        "hash" in ver_result.stderr.lower()
        or "size" in ver_result.stderr.lower()
        or "tamper" in ver_result.stderr.lower()
    )


def test_artifact_hash_mismatch_rejected(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    sdist_path, wheel_path = _create_synthetic_dist(dist_dir)
    manifest_path = dist_dir / "artifacts-manifest.json"

    _run_integrity(
        [
            "generate",
            "--dist",
            str(dist_dir),
            "--manifest",
            str(manifest_path),
            "--version",
            "0.6.0",
        ]
    )

    # Corrupt hash in manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"][0]["sha256"] = (
        "0000000000000000000000000000000000000000000000000000000000000000"
    )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    ver_result = _run_integrity(
        ["verify", "--dist", str(dist_dir), "--manifest", str(manifest_path), "--version", "0.6.0"]
    )
    assert ver_result.returncode != 0
    assert (
        "hash" in ver_result.stderr.lower()
        or "digest" in ver_result.stderr.lower()
        or "mismatch" in ver_result.stderr.lower()
    )


def test_artifact_version_mismatch_rejected(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    _create_synthetic_dist(dist_dir, version="0.5.0")
    manifest_path = dist_dir / "artifacts-manifest.json"

    # Requesting version 0.6.0 when artifacts are 0.5.0
    ver_result = _run_integrity(
        [
            "generate",
            "--dist",
            str(dist_dir),
            "--manifest",
            str(manifest_path),
            "--version",
            "0.6.0",
        ]
    )
    assert ver_result.returncode != 0
    assert "version" in ver_result.stderr.lower()


def test_artifact_missing_file_rejected(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    sdist_path, wheel_path = _create_synthetic_dist(dist_dir)
    manifest_path = dist_dir / "artifacts-manifest.json"

    _run_integrity(
        [
            "generate",
            "--dist",
            str(dist_dir),
            "--manifest",
            str(manifest_path),
            "--version",
            "0.6.0",
        ]
    )
    # Delete wheel
    wheel_path.unlink()

    ver_result = _run_integrity(
        ["verify", "--dist", str(dist_dir), "--manifest", str(manifest_path), "--version", "0.6.0"]
    )
    assert ver_result.returncode != 0
    assert "missing" in ver_result.stderr.lower()


def test_artifact_forbidden_package_member_rejected(tmp_path: Path) -> None:
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir(parents=True, exist_ok=True)
    wheel_path = dist_dir / "mia_ai-0.6.0-py3-none-any.whl"

    # Wheel containing forbidden path
    with zipfile.ZipFile(wheel_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mia_cli/tui/__init__.py", "# tui\n")
        zf.writestr("mia_agent/profiles.py", "# forbidden\n")
        zf.writestr(
            "mia_ai-0.6.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: mia-ai\nVersion: 0.6.0\n",
        )

    check_result = _run_integrity(["check-surface", "--wheel", str(wheel_path)])
    assert check_result.returncode != 0
    assert "forbidden" in check_result.stderr.lower() or "retired" in check_result.stderr.lower()


def test_wheel_surface_plugin_api_check(tmp_path: Path) -> None:
    # 1. Wheel missing required TUI prefix
    wheel_bad_prefix = tmp_path / "bad_prefix.whl"
    with zipfile.ZipFile(wheel_bad_prefix, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mia_agent/__init__.py", "")
    res = _run_integrity(["check-surface", "--wheel", str(wheel_bad_prefix)])
    assert res.returncode != 0
    assert "missing" in res.stderr.lower()

    # 2. Wheel with incompatible Plugin API version
    wheel_bad_api = tmp_path / "bad_api.whl"
    with zipfile.ZipFile(wheel_bad_api, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("mia_cli/tui/__init__.py", "")
        zf.writestr("mia_agent/plugin_models.py", "CORE_PLUGIN_API_VERSION = 99\n")
    res = _run_integrity(["check-surface", "--wheel", str(wheel_bad_api)])
    assert res.returncode != 0
    assert "api" in res.stderr.lower() or "version" in res.stderr.lower()

    # 3. Built wheel in repo dist/ (if present) passes surface check
    dist_wheels = list((ROOT / "dist").glob("*.whl"))
    if dist_wheels:
        res = _run_integrity(["check-surface", "--wheel", str(dist_wheels[0])])
        assert res.returncode == 0, f"Built wheel failed surface check: {res.stderr}"


def test_installed_plugin_entry_point_api_compatibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mia_agent.plugin_models import CORE_PLUGIN_API_VERSION, PluginManifest, PluginToolSpec
    from mia_agent.plugins import MIA_PLUGIN_ENTRY_POINT_GROUP, PluginManager

    assert CORE_PLUGIN_API_VERSION == 1
    assert MIA_PLUGIN_ENTRY_POINT_GROUP == "mia.plugins"

    manifest = PluginManifest(
        plugin_id="test_distribution_plugin",
        version="0.1.0",
        api_version=CORE_PLUGIN_API_VERSION,
        plugin_type="trusted-code",
        display_name="Distribution Test Plugin",
        description="Verifies installed plugin discovery",
        tool_specs=[
            PluginToolSpec(
                name="dist_check",
                description="Test tool",
                effect="non-mutating",
            )
        ],
    )

    class MockDist:
        name = "test-plugin-pkg"
        version = "0.1.0"

    class MockEntryPoint:
        name = "test_distribution_plugin"
        value = "test_plugin_pkg:plugin"
        group = MIA_PLUGIN_ENTRY_POINT_GROUP
        dist = MockDist()

    MockEntryPoint.manifest = manifest

    monkeypatch.setattr(
        "mia_agent.plugins.discover_entry_points",
        lambda: [MockEntryPoint()],
    )

    pm = PluginManager(plugins_dir=tmp_path)
    available = pm.list_available()
    found = [m for m in available if m.plugin_id == "test_distribution_plugin"]
    assert len(found) == 1
    assert found[0].api_version == 1
    assert found[0].provenance is not None
    assert found[0].provenance.source == "installed"
    assert found[0].provenance.package_name == "test-plugin-pkg"


def test_artifact_clean_install_and_smoke() -> None:
    dist_wheels = list((ROOT / "dist").glob("*.whl"))
    if not dist_wheels:
        subprocess.run(["uv", "build", "--offline"], cwd=ROOT, check=True)
        dist_wheels = list((ROOT / "dist").glob("*.whl"))
    assert len(dist_wheels) > 0

    res = _run_integrity(["smoke", "--wheel", str(dist_wheels[0])])
    assert res.returncode == 0, f"Smoke test failed: {res.stderr}\n{res.stdout}"
    assert "clean install smoke: clean" in res.stdout.lower()
