#!/usr/bin/env python3
"""Check distribution artifact integrity, manifest provenance, and package surface."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

_surface_spec = importlib.util.spec_from_file_location(
    "check_wheel_surface", Path(__file__).parent / "check-wheel-surface.py"
)
if _surface_spec and _surface_spec.loader:
    _surface_mod = importlib.util.module_from_spec(_surface_spec)
    _surface_spec.loader.exec_module(_surface_mod)
    REQUIRED_WHEEL_PREFIXES = _surface_mod.REQUIRED_PREFIXES
    FORBIDDEN_WHEEL_PREFIXES = _surface_mod.FORBIDDEN_PREFIXES
    FORBIDDEN_TEXT = _surface_mod.FORBIDDEN_TEXT
else:
    REQUIRED_WHEEL_PREFIXES = ("mia_cli/tui/",)
    FORBIDDEN_WHEEL_PREFIXES = ()
    FORBIDDEN_TEXT = re.compile(r"^$")


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


def _is_confined_artifact_name(name: str, base_dir: Path) -> bool:
    if not name or not isinstance(name, str):
        return False
    # Artifact name must be a single filename, not a path
    if "/" in name or "\\" in name or ".." in name:
        return False
    p = Path(name)
    if p.is_absolute() or p.name != name:
        return False
    try:
        resolved = (base_dir / name).resolve()
        return resolved.is_relative_to(base_dir.resolve()) and resolved.parent == base_dir.resolve()
    except Exception:
        return False


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

    seen_files: set[str] = set()
    for art in artifacts:
        name = art.get("name")
        if not name:
            print(f"Manifest artifact entry missing 'name': {art}", file=sys.stderr)
            return 1

        if not _is_confined_artifact_name(name, dist_dir):
            print(
                f"Artifact path traversal or escape detected: {name!r} is not confined to {dist_dir}",
                file=sys.stderr,
            )
            return 1

        file_path = dist_dir / name
        if not file_path.is_file():
            print(f"Artifact file missing on disk: {file_path}", file=sys.stderr)
            return 1

        seen_files.add(name)

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

    # Check for untracked wheels or sdists
    if dist_dir.is_dir():
        for f in dist_dir.iterdir():
            if (f.name.endswith(".whl") or f.name.endswith(".tar.gz")) and f.name not in seen_files:
                print(
                    f"Dist directory contains untracked artifact not in manifest: {f.name}",
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

        # Check duplicate archive members
        if len(names) != len(set(names)):
            seen: set[str] = set()
            duplicates: list[str] = []
            for n in names:
                if n in seen and n not in duplicates:
                    duplicates.append(n)
                seen.add(n)
            print(
                f"Wheel contains duplicate archive members: {', '.join(duplicates)}",
                file=sys.stderr,
            )
            return 1

        # Check directory-traversing archive entries
        for name in names:
            if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                print(
                    f"Wheel contains directory-traversing archive entry: {name!r}",
                    file=sys.stderr,
                )
                return 1

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


def smoke_clean_install(wheel_path: Path, repo_root: Path) -> int:
    wheel_path = wheel_path.resolve()
    repo_root = repo_root.resolve()
    if not wheel_path.is_file():
        print(f"Wheel file not found: {wheel_path}", file=sys.stderr)
        return 2

    import tempfile

    repo_site_packages = [p for p in sys.path if "site-packages" in p and str(repo_root) in p]
    fallback_site_packages = [p for p in sys.path if "site-packages" in p]
    site_packages = (
        repo_site_packages[0]
        if repo_site_packages
        else (fallback_site_packages[0] if fallback_site_packages else "")
    )

    with tempfile.TemporaryDirectory() as td:
        venv_dir = Path(td) / "venv"
        # 1. Create isolated virtual environment using uv venv
        venv_res = subprocess.run(
            ["uv", "venv", "--python", sys.executable, str(venv_dir)],
            cwd=td,
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if venv_res.returncode != 0:
            print(
                f"Failed to create virtual environment via uv:\n{venv_res.stderr}",
                file=sys.stderr,
            )
            return 1

        # Determine venv layout
        venv_bin = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
        python_bin = venv_bin / ("python.exe" if sys.platform == "win32" else "python")
        mia_bin = venv_bin / ("mia.exe" if sys.platform == "win32" else "mia")

        # Provide installed runtime dependencies to isolated venv via .pth without contaminating wheel under test
        venv_site_pkgs = list(venv_dir.glob("lib/python*/site-packages"))
        if not venv_site_pkgs:
            venv_site_pkgs = list(venv_dir.glob("Lib/site-packages"))
        if venv_site_pkgs and site_packages:
            (venv_site_pkgs[0] / "_repo_deps.pth").write_text(
                site_packages + "\n", encoding="utf-8"
            )

        # 2. Install the wheel using uv pip install --offline --no-deps into the isolated venv
        install_res = subprocess.run(
            [
                "uv",
                "pip",
                "install",
                "--offline",
                "--no-deps",
                str(wheel_path),
                "--python",
                str(python_bin),
            ],
            cwd=td,
            capture_output=True,
            text=True,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
        if install_res.returncode != 0:
            print(
                f"Failed to install wheel into isolated venv:\n{install_res.stderr}",
                file=sys.stderr,
            )
            return 1

        # 3. Verify entry point binary was generated
        if not mia_bin.is_file():
            print(
                f"Installed CLI entry point not found at {mia_bin}",
                file=sys.stderr,
            )
            return 1

        # 4. Invoke the installed CLI entry point for non-mutating surface commands
        test_env = {
            "PATH": f"{venv_bin}:{os.environ.get('PATH', '')}",
            "HOME": td,
        }
        for subcmd in [
            ["--help"],
            ["agent", "list"],
            ["template", "list"],
            ["plugin", "list"],
            ["sessions", "list"],
        ]:
            cmd = [str(mia_bin), *subcmd]
            res = subprocess.run(cmd, cwd=td, env=test_env, capture_output=True, text=True)
            if res.returncode != 0:
                print(
                    f"CLI invocation '{' '.join(cmd)}' failed with exit code {res.returncode}:\n{res.stderr}\n{res.stdout}",
                    file=sys.stderr,
                )
                return 1

        # 5. Verify package provenance: mia_agent must import from the isolated venv, not repo src/
        provenance_script = (
            "import sys, pathlib, mia_agent; "
            "agent_path = pathlib.Path(mia_agent.__file__).resolve(); "
            f"venv_path = pathlib.Path({repr(str(venv_dir))}).resolve(); "
            "assert agent_path.is_relative_to(venv_path), f'Imported from {agent_path}, not venv {venv_path}'; "
            f"repo_src = pathlib.Path({repr(str(repo_root))}).resolve() / 'src'; "
            "assert not agent_path.is_relative_to(repo_src), f'Source checkout not excluded: {agent_path}'"
        )
        prov_res = subprocess.run(
            [str(python_bin), "-c", provenance_script],
            cwd=td,
            env=test_env,
            capture_output=True,
            text=True,
        )
        if prov_res.returncode != 0:
            print(
                f"Clean install provenance check failed:\n{prov_res.stderr}",
                file=sys.stderr,
            )
            return 1

        print("clean install smoke: clean")
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
    gen_parser.add_argument(
        "--dist", "--dist-dir", dest="dist", type=Path, default=repo_root / "dist"
    )
    gen_parser.add_argument("--manifest", type=Path, default=None)
    gen_parser.add_argument("--version", type=str, default=default_version)

    # verify
    ver_parser = subparsers.add_parser("verify", help="Verify artifact manifest and integrity")
    ver_parser.add_argument(
        "--dist", "--dist-dir", dest="dist", type=Path, default=repo_root / "dist"
    )
    ver_parser.add_argument("--manifest", type=Path, default=None)
    ver_parser.add_argument("--version", type=str, default=default_version)

    # check-surface
    surf_parser = subparsers.add_parser("check-surface", help="Check wheel package surface")
    surf_parser.add_argument("--wheel", type=Path, default=None)
    surf_parser.add_argument("--dist", "--dist-dir", dest="dist", type=Path, default=None)

    # smoke
    smoke_parser = subparsers.add_parser("smoke", help="Clean install and non-mutating smoke test")
    smoke_parser.add_argument("--wheel", type=Path, default=None)
    smoke_parser.add_argument("--dist", "--dist-dir", dest="dist", type=Path, default=None)

    args = parser.parse_args()

    if args.command == "generate":
        manifest_path = args.manifest or (args.dist / "release-manifest.json")
        return generate_manifest(args.dist, manifest_path, args.version, repo_root)
    elif args.command == "verify":
        manifest_path = args.manifest
        if not manifest_path:
            if (args.dist / "release-manifest.json").is_file():
                manifest_path = args.dist / "release-manifest.json"
            else:
                manifest_path = args.dist / "artifacts-manifest.json"
        return verify_manifest(args.dist, manifest_path, args.version)
    elif args.command == "check-surface":
        wheel = args.wheel
        if not wheel and args.dist:
            wheels = sorted(args.dist.glob("*.whl"))
            if wheels:
                wheel = wheels[0]
        if not wheel:
            print("check-surface requires --wheel or --dist", file=sys.stderr)
            return 2
        return check_wheel_surface(wheel)
    elif args.command == "smoke":
        wheel = args.wheel
        if not wheel and args.dist:
            wheels = sorted(args.dist.glob("*.whl"))
            if wheels:
                wheel = wheels[0]
        if not wheel:
            print("smoke requires --wheel or --dist", file=sys.stderr)
            return 2
        return smoke_clean_install(wheel, repo_root)
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
