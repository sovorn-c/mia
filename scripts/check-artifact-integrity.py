#!/usr/bin/env python3
"""Check distribution artifact integrity, manifest provenance, and package surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

REQUIRED_WHEEL_PREFIXES = ("mia_cli/tui/",)
FORBIDDEN_WHEEL_PREFIXES = (
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


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def _get_project_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        match = re.search(r'version\s*=\s*"([^"]+)"', text)
        if match:
            return match.group(1)
    return "0.6.0"


def _get_git_ref(root: Path) -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return "HEAD"


def _get_lock_hash(root: Path) -> str:
    lockfile = root / "uv.lock"
    if lockfile.is_file():
        return _compute_sha256(lockfile)
    return ""


def generate_manifest(
    dist_dir: Path, manifest_path: Path, expected_version: str, repo_root: Path
) -> int:
    if not dist_dir.is_dir():
        print(f"dist directory not found: {dist_dir}", file=sys.stderr)
        return 1

    wheels = sorted(dist_dir.glob(f"*{expected_version}*.whl"))
    sdists = sorted(dist_dir.glob(f"*{expected_version}*.tar.gz"))

    # Also search for all whl and tar.gz in dist_dir if version-specific not found directly
    if not wheels:
        wheels = sorted(dist_dir.glob("*.whl"))
    if not sdists:
        sdists = sorted(dist_dir.glob("*.tar.gz"))

    if not wheels or not sdists:
        print(
            f"Missing required distribution artifacts in {dist_dir}: found {len(wheels)} wheels and {len(sdists)} sdists",
            file=sys.stderr,
        )
        return 1

    artifacts_info: list[dict[str, Any]] = []
    for whl in wheels:
        # Check version in filename
        if expected_version not in whl.name:
            print(
                f"Artifact version mismatch: {whl.name} does not match expected version {expected_version}",
                file=sys.stderr,
            )
            return 1
        artifacts_info.append(
            {
                "name": whl.name,
                "type": "wheel",
                "version": expected_version,
                "size": whl.stat().st_size,
                "sha256": _compute_sha256(whl),
            }
        )

    for sdist in sdists:
        if expected_version not in sdist.name:
            print(
                f"Artifact version mismatch: {sdist.name} does not match expected version {expected_version}",
                file=sys.stderr,
            )
            return 1
        artifacts_info.append(
            {
                "name": sdist.name,
                "type": "sdist",
                "version": expected_version,
                "size": sdist.stat().st_size,
                "sha256": _compute_sha256(sdist),
            }
        )

    manifest_data = {
        "version": expected_version,
        "source_ref": _get_git_ref(repo_root),
        "lock_hash": _get_lock_hash(repo_root),
        "artifacts": artifacts_info,
    }

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    print(f"Generated manifest at {manifest_path}")
    return 0


def verify_manifest(dist_dir: Path, manifest_path: Path, expected_version: str) -> int:
    if not manifest_path.is_file():
        print(f"Manifest file not found: {manifest_path}", file=sys.stderr)
        return 1

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to parse manifest {manifest_path}: {exc}", file=sys.stderr)
        return 1

    manifest_ver = manifest.get("version")
    if manifest_ver != expected_version:
        print(
            f"Manifest version mismatch: manifest declares {manifest_ver!r} but expected {expected_version!r}",
            file=sys.stderr,
        )
        return 1

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        print(f"Manifest contains no artifacts list: {manifest}", file=sys.stderr)
        return 1

    for art in artifacts:
        name = art.get("name")
        if not name:
            print(f"Manifest artifact entry missing 'name': {art}", file=sys.stderr)
            return 1

        file_path = dist_dir / name
        if not file_path.is_file():
            print(f"Artifact file missing on disk: {file_path}", file=sys.stderr)
            return 1

        expected_size = art.get("size")
        actual_size = file_path.stat().st_size
        if expected_size is not None and actual_size != expected_size:
            print(
                f"Artifact size mismatch for {name}: expected {expected_size} bytes, got {actual_size} bytes (tamper detected)",
                file=sys.stderr,
            )
            return 1

        expected_hash = art.get("sha256")
        actual_hash = _compute_sha256(file_path)
        if expected_hash and actual_hash.lower() != expected_hash.lower():
            print(
                f"Artifact hash mismatch for {name}: expected {expected_hash}, got {actual_hash} (tamper detected)",
                file=sys.stderr,
            )
            return 1

    print("artifact integrity: clean")
    return 0


def check_wheel_surface(wheel_path: Path) -> int:
    if not wheel_path.is_file():
        print(f"Wheel file not found: {wheel_path}", file=sys.stderr)
        return 2

    with zipfile.ZipFile(wheel_path) as zf:
        names = zf.namelist()

        # Check required prefixes
        missing = [
            prefix
            for prefix in REQUIRED_WHEEL_PREFIXES
            if not any(name.startswith(prefix) for name in names)
        ]
        if missing:
            print(f"required wheel paths missing: {', '.join(missing)}", file=sys.stderr)
            return 1

        # Check forbidden prefixes
        forbidden = [
            prefix
            for prefix in FORBIDDEN_WHEEL_PREFIXES
            if any(name.startswith(prefix) for name in names)
        ]
        if forbidden:
            print(f"forbidden wheel paths found: {', '.join(forbidden)}", file=sys.stderr)
            return 1

        # Check content text
        for name in names:
            if name.endswith((".py", "entry_points.txt")):
                text = zf.read(name).decode("utf-8", errors="replace")
                if FORBIDDEN_TEXT.search(text):
                    print(f"retired public surface found in: {name}", file=sys.stderr)
                    return 1

        # Verify Plugin API version in wheel if present
        if "mia_agent/plugin_models.py" in names:
            text = zf.read("mia_agent/plugin_models.py").decode("utf-8", errors="replace")
            if "CORE_PLUGIN_API_VERSION = 1" not in text:
                print(
                    "wheel plugin API version mismatch: CORE_PLUGIN_API_VERSION != 1",
                    file=sys.stderr,
                )
                return 1

    print("wheel surface: clean")
    return 0


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    default_version = _get_project_version(repo_root)

    parser = argparse.ArgumentParser(
        description="Check distribution artifact integrity and surface"
    )
    subparsers = parser.add_subparsers(dest="command")

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate artifact manifest")
    gen_parser.add_argument("--dist", type=Path, default=repo_root / "dist")
    gen_parser.add_argument("--manifest", type=Path, default=None)
    gen_parser.add_argument("--version", type=str, default=default_version)

    # verify
    ver_parser = subparsers.add_parser("verify", help="Verify artifact manifest and integrity")
    ver_parser.add_argument("--dist", type=Path, default=repo_root / "dist")
    ver_parser.add_argument("--manifest", type=Path, default=None)
    ver_parser.add_argument("--version", type=str, default=default_version)

    # check-surface
    surf_parser = subparsers.add_parser("check-surface", help="Check wheel package surface")
    surf_parser.add_argument("--wheel", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "generate":
        manifest_path = args.manifest or (args.dist / "artifacts-manifest.json")
        return generate_manifest(args.dist, manifest_path, args.version, repo_root)
    elif args.command == "verify":
        manifest_path = args.manifest or (args.dist / "artifacts-manifest.json")
        return verify_manifest(args.dist, manifest_path, args.version)
    elif args.command == "check-surface":
        return check_wheel_surface(args.wheel)
    else:
        # Default: verify dist/
        dist_dir = repo_root / "dist"
        manifest_path = dist_dir / "artifacts-manifest.json"
        if not manifest_path.is_file():
            rc = generate_manifest(dist_dir, manifest_path, default_version, repo_root)
            if rc != 0:
                return rc
        vrc = verify_manifest(dist_dir, manifest_path, default_version)
        if vrc != 0:
            return vrc
        for whl in dist_dir.glob("*.whl"):
            src = check_wheel_surface(whl)
            if src != 0:
                return src
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
