#!/usr/bin/env python3
"""Authorized release verification, dry-run, publication, and supersession procedure."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).parents[1]


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


def _sanitize_secrets(text: str, extra_secrets: list[str] | None = None) -> str:
    sanitized = text
    secrets = list(extra_secrets or [])
    for env_var in (
        "UV_PUBLISH_TOKEN",
        "PYPI_TOKEN",
        "PYPI_PASSWORD",
        "MIA_RELEASE_TOKEN",
        "GITHUB_TOKEN",
    ):
        val = os.getenv(env_var)
        if val and len(val) >= 4:
            secrets.append(val)

    for sec in set(secrets):
        if sec:
            sanitized = sanitized.replace(sec, "[REDACTED]")

    # Generic token pattern matching
    sanitized = re.sub(r"(pypi-[A-Za-z0-9_-]{20,})", "[REDACTED_PYPI_TOKEN]", sanitized)
    sanitized = re.sub(r"(Bearer\s+[A-Za-z0-9_.-]{16,})", "Bearer [REDACTED]", sanitized)
    return sanitized


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


def verify_candidate(
    dist_dir: Path,
    expected_version: str,
    expected_ref: str | None = None,
    manifest_path: Path | None = None,
    gate_evidence: Path | None = None,
    skip_gate_check: bool = False,
) -> tuple[bool, str, dict[str, Any]]:
    if not dist_dir.is_dir():
        return False, f"Dist directory not found: {dist_dir}", {}

    if manifest_path:
        m_path = manifest_path
    elif (dist_dir / "release-manifest.json").is_file():
        m_path = dist_dir / "release-manifest.json"
    elif (dist_dir / "artifacts-manifest.json").is_file():
        m_path = dist_dir / "artifacts-manifest.json"
    else:
        m_path = dist_dir / "release-manifest.json"
    if not m_path.is_file():
        return False, f"Release manifest not found at {m_path}", {}

    try:
        manifest_data = json.loads(m_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"Failed to parse manifest JSON at {m_path}: {e}", {}

    # Version check
    manifest_version = manifest_data.get("version")
    if manifest_version != expected_version:
        return (
            False,
            f"Version mismatch: requested '{expected_version}' but manifest contains '{manifest_version}'",
            manifest_data,
        )

    # Ref check
    manifest_ref = manifest_data.get("source_ref", "")
    if expected_ref and manifest_ref != expected_ref:
        return (
            False,
            f"Git ref mismatch: requested '{expected_ref}' but manifest source_ref is '{manifest_ref}'",
            manifest_data,
        )

    # Artifact integrity
    manifest_artifacts = manifest_data.get("artifacts", [])
    if not manifest_artifacts:
        return False, "Manifest contains no artifacts", manifest_data

    seen_files: set[str] = set()
    for art in manifest_artifacts:
        name = art.get("name")
        if not name:
            return False, "Manifest artifact entry missing 'name'", manifest_data
        if not _is_confined_artifact_name(name, dist_dir):
            return (
                False,
                f"Artifact path traversal or escape detected: {name!r} is not confined to {dist_dir}",
                manifest_data,
            )
        art_path = dist_dir / name
        if not art_path.is_file():
            return False, f"Artifact file missing from dist: {name}", manifest_data

        seen_files.add(name)
        if expected_version not in name:
            return (
                False,
                f"Artifact version mismatch: {name} does not match expected version {expected_version}",
                manifest_data,
            )

        actual_size = art_path.stat().st_size
        if actual_size != art.get("size"):
            return (
                False,
                f"Artifact size mismatch for {name}: expected {art.get('size')}, got {actual_size}",
                manifest_data,
            )

        actual_hash = _compute_sha256(art_path)
        if actual_hash != art.get("sha256"):
            return (
                False,
                f"Artifact hash mismatch / corrupted payload for {name}: expected {art.get('sha256')}, got {actual_hash}",
                manifest_data,
            )

    # Check for untracked wheels or sdists
    for f in dist_dir.iterdir():
        if (f.name.endswith(".whl") or f.name.endswith(".tar.gz")) and f.name not in seen_files:
            return (
                False,
                f"Dist directory contains untracked artifact not in manifest: {f.name}",
                manifest_data,
            )

    # Gate evidence check
    if not skip_gate_check:
        evidence_file = gate_evidence or (dist_dir / "release-gate-evidence.json")
        if not evidence_file.is_file():
            return (
                False,
                f"Release gate evidence missing at {evidence_file}. Run scripts/check-release-gate.sh or pass --skip-gate-check for testing.",
                manifest_data,
            )
        try:
            g_data = json.loads(evidence_file.read_text(encoding="utf-8"))
        except Exception as e:
            return (
                False,
                f"Failed to read gate evidence JSON at {evidence_file}: {e}",
                manifest_data,
            )

        if g_data.get("status") not in ("passed", "success", "OK") and not g_data.get(
            "success", False
        ):
            return (
                False,
                f"Gate evidence at {evidence_file} indicates failing gate: {g_data}",
                manifest_data,
            )

        ev_version = g_data.get("version")
        if not ev_version or ev_version != expected_version:
            return (
                False,
                f"Gate evidence version mismatch: expected '{expected_version}' but gate evidence recorded '{ev_version}'",
                manifest_data,
            )

        ev_ref = g_data.get("source_ref")
        target_ref = expected_ref or manifest_data.get("source_ref")
        if target_ref and target_ref != "HEAD" and (not ev_ref or ev_ref != target_ref):
            return (
                False,
                f"Gate evidence source_ref mismatch: expected '{target_ref}' but gate evidence recorded '{ev_ref}'",
                manifest_data,
            )

    return True, "Candidate verified successfully", manifest_data


def record_attempt_evidence(
    evidence_dir: Path,
    status: str,
    version: str,
    source_ref: str,
    artifacts: list[str],
    error_type: str | None = None,
    error_message: str | None = None,
    recovery_action: str | None = None,
    recovery_recommendation: str | None = None,
) -> Path:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "release-attempt.json"
    data: dict[str, Any] = {
        "status": status,
        "version": version,
        "source_ref": source_ref,
        "artifacts": artifacts,
    }
    if error_type:
        data["error_type"] = error_type
    if error_message:
        data["error_message"] = _sanitize_secrets(error_message)
    if recovery_action:
        data["recovery_action"] = recovery_action
    if recovery_recommendation:
        data["recovery_recommendation"] = recovery_recommendation

    evidence_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return evidence_path


def classify_failure(failure_type: str, details: str) -> tuple[str, str]:
    lower = (failure_type + " " + details).lower()
    if (
        "network" in lower
        or "timeout" in lower
        or "econnreset" in lower
        or "502" in lower
        or "503" in lower
    ):
        return (
            "RETRY",
            "Transient network or gateway failure before publication completed. "
            "Artifacts and evidence are preserved. Check registry connectivity and retry the publish command.",
        )
    elif "partial" in lower or "corrupt" in lower or "yank" in lower:
        return (
            "WITHDRAW",
            "Partial publication or corrupted release exposed on registry. "
            "Follow the withdrawal runbook in docs/release-guide.md to yank or withdraw the incomplete version on PyPI, "
            "preserve failure evidence, and prepare a superseding release.",
        )
    elif "conflict" in lower or "already exists" in lower or "409" in lower or "duplicate" in lower:
        return (
            "SUPERSEDE",
            "Version conflict on registry. Registries disallow overwriting an existing version release. "
            "Preserve current evidence, bump the version in pyproject.toml to a new release candidate, and re-run.",
        )
    return (
        "RETRY",
        "Publication attempt failed. Preserved local artifacts and failure evidence for operator review.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Authorized release candidate verification, dry-run, and publication.",
    )
    subparsers = parser.add_subparsers(dest="action", help="Action to perform")

    # Common arguments
    def add_common_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--dist-dir",
            type=Path,
            default=REPO_ROOT / "dist",
            help="Directory containing built wheels, sdist, and manifest",
        )
        p.add_argument(
            "--version",
            type=str,
            default=None,
            help="Expected release version (defaults to pyproject.toml version)",
        )
        p.add_argument(
            "--ref",
            type=str,
            default=None,
            help="Expected Git ref (commit SHA or tag)",
        )
        p.add_argument(
            "--manifest",
            type=Path,
            default=None,
            help="Path to release manifest JSON (defaults to <dist-dir>/release-manifest.json)",
        )
        p.add_argument(
            "--gate-evidence",
            type=Path,
            default=None,
            help="Path to release gate evidence JSON",
        )
        p.add_argument(
            "--skip-gate-check",
            action="store_true",
            help="Skip gate check script/evidence verification (dry-run/test mode)",
        )
        p.add_argument(
            "--evidence-dir",
            type=Path,
            default=None,
            help="Directory where release attempt evidence is recorded (defaults to dist-dir)",
        )

    # verify / dry-run parser
    verify_parser = subparsers.add_parser("verify", help="Verify release candidate in dry-run mode")
    add_common_args(verify_parser)

    # publish parser
    publish_parser = subparsers.add_parser("publish", help="Publish verified candidate to registry")
    add_common_args(publish_parser)
    publish_parser.add_argument(
        "--authorized",
        action="store_true",
        help="Explicit authorization to publish. Required unless MIA_RELEASE_AUTHORIZED=1 is set.",
    )
    publish_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform all candidate and authorization checks without uploading artifacts",
    )
    publish_parser.add_argument(
        "--simulate-failure",
        choices=["network", "partial", "conflict"],
        default=None,
        help="Simulate publication failure for testing failure handling and evidence retention",
    )

    args = parser.parse_args(argv)
    if not args.action:
        parser.print_help()
        return 1

    expected_version = args.version or _get_project_version(REPO_ROOT)
    dist_dir = args.dist_dir
    evidence_dir = args.evidence_dir or dist_dir

    # Step 1: Candidate Verification
    ok, msg, manifest = verify_candidate(
        dist_dir=dist_dir,
        expected_version=expected_version,
        expected_ref=args.ref,
        manifest_path=args.manifest,
        gate_evidence=args.gate_evidence,
        skip_gate_check=args.skip_gate_check,
    )
    if not ok:
        print(f"Candidate verification REFUSED: {_sanitize_secrets(msg)}", file=sys.stderr)
        return 1

    source_ref = manifest.get("source_ref", args.ref or "HEAD")
    artifact_names = [a.get("name", "") for a in manifest.get("artifacts", [])]

    if args.action == "verify":
        print(
            f"Candidate verified: version={expected_version}, ref={source_ref}, artifacts={len(artifact_names)}"
        )
        print("Dry run complete: release candidate is ready for authorized publication.")
        return 0

    if args.action == "publish":
        # Check authorization
        env_auth = os.getenv("MIA_RELEASE_AUTHORIZED", "").strip().lower() in ("1", "true", "yes")
        is_authorized = args.authorized or env_auth

        if not is_authorized:
            print(
                "Publication REFUSED: publication requires explicit operator authorization "
                "(--authorized or MIA_RELEASE_AUTHORIZED=1). Ordinary CI, tag, or push events are unauthorized.",
                file=sys.stderr,
            )
            return 1

        if args.dry_run:
            print(
                f"DRY RUN (authorized): candidate version={expected_version} verified. No network calls made."
            )
            return 0

        # Failure simulation (for offline tests)
        if args.simulate_failure:
            action, rec = classify_failure(
                args.simulate_failure, f"Simulated {args.simulate_failure} error"
            )
            ev_path = record_attempt_evidence(
                evidence_dir=evidence_dir,
                status="failed",
                version=expected_version,
                source_ref=source_ref,
                artifacts=artifact_names,
                error_type=args.simulate_failure,
                error_message=f"Simulated publication failure: {args.simulate_failure}",
                recovery_action=action,
                recovery_recommendation=rec,
            )
            print(
                f"Publication failed ({args.simulate_failure}): evidence recorded at {ev_path}. "
                f"Recovery recommendation: {action}",
                file=sys.stderr,
            )
            return 1

        # Real publish invocation via uv publish
        artifacts_to_publish = [str(dist_dir / name) for name in artifact_names if name]
        cmd = ["uv", "publish", *artifacts_to_publish]

        # Restrict environment to secret-safe minimal set
        safe_env = {
            "PATH": os.environ.get("PATH", ""),
            "HOME": os.environ.get("HOME", ""),
        }
        if "UV_PUBLISH_TOKEN" in os.environ:
            safe_env["UV_PUBLISH_TOKEN"] = os.environ["UV_PUBLISH_TOKEN"]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                env=safe_env,
            )
            if res.returncode != 0:
                sanitized_stderr = _sanitize_secrets(res.stderr)
                action, rec = classify_failure("execution", sanitized_stderr)
                ev_path = record_attempt_evidence(
                    evidence_dir=evidence_dir,
                    status="failed",
                    version=expected_version,
                    source_ref=source_ref,
                    artifacts=artifact_names,
                    error_type="PublishError",
                    error_message=sanitized_stderr,
                    recovery_action=action,
                    recovery_recommendation=rec,
                )
                print(f"Publication FAILED: {sanitized_stderr}", file=sys.stderr)
                print(f"Failure evidence recorded at {ev_path}", file=sys.stderr)
                print(f"Recovery action: {action} - {rec}", file=sys.stderr)
                return 1

            record_attempt_evidence(
                evidence_dir=evidence_dir,
                status="succeeded",
                version=expected_version,
                source_ref=source_ref,
                artifacts=artifact_names,
            )
            print(
                f"Successfully published {len(artifacts_to_publish)} artifacts for version {expected_version}."
            )
            return 0
        except Exception as e:
            sanitized_err = _sanitize_secrets(str(e))
            action, rec = classify_failure("exception", sanitized_err)
            record_attempt_evidence(
                evidence_dir=evidence_dir,
                status="failed",
                version=expected_version,
                source_ref=source_ref,
                artifacts=artifact_names,
                error_type=type(e).__name__,
                error_message=sanitized_err,
                recovery_action=action,
                recovery_recommendation=rec,
            )
            print(f"Publication exception: {sanitized_err}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
