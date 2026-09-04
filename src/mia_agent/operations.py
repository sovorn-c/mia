"""Local operations, data layout, backup, and restore service."""

from __future__ import annotations

import contextlib
import hashlib
import os
import time
import zipfile
from pathlib import Path

from pydantic import BaseModel, Field

from mia_agent.agents.manager import AgentManager
from mia_agent.auth.credentials import default_credentials_path


class DataLocation(BaseModel):
    """Descriptor for one category of local Mia data."""

    category: str
    ownership: str
    path: Path
    sensitive: bool = False
    included_in_backup: bool = True
    description: str = ""


class DataLayout(BaseModel):
    """Aggregate layout of all configured local data categories."""

    locations: list[DataLocation] = Field(default_factory=list)


BACKUP_ARCHIVE_VERSION = "1.0"
MANIFEST_FILENAME = "backup_manifest.json"


class ManifestFileEntry(BaseModel):
    """File entry in the backup manifest."""

    path: str
    size: int
    sha256: str


class BackupManifest(BaseModel):
    """Archive manifest documenting version, creation time, and member files."""

    version: str = BACKUP_ARCHIVE_VERSION
    created_at: float = Field(default_factory=time.time)
    files: list[ManifestFileEntry] = Field(default_factory=list)
    total_bytes: int = 0


def get_data_locations(
    manager: AgentManager | None = None,
    credentials_path: Path | None = None,
) -> DataLayout:
    """Return the Core-derived data layout covering all configured boundaries."""
    mgr = manager or AgentManager()
    cred_path = credentials_path or default_credentials_path()

    locations = [
        DataLocation(
            category="agents",
            ownership="agent",
            path=mgr.agents_dir,
            sensitive=False,
            included_in_backup=True,
            description="Agent definitions and local configuration",
        ),
        DataLocation(
            category="sessions",
            ownership="agent",
            path=mgr.agents_dir,
            sensitive=False,
            included_in_backup=True,
            description="Append-only Session event logs",
        ),
        DataLocation(
            category="plugins",
            ownership="plugin",
            path=mgr.agents_dir,
            sensitive=False,
            included_in_backup=True,
            description="Plugin-owned state and persistent storage",
        ),
        DataLocation(
            category="diagnostics",
            ownership="core",
            path=mgr.get_diagnostics_dir(),
            sensitive=False,
            included_in_backup=True,
            description="Operational lifecycle diagnostics and telemetry",
        ),
        DataLocation(
            category="credentials",
            ownership="core",
            path=cred_path,
            sensitive=True,
            included_in_backup=False,
            description="External provider credentials and auth tokens",
        ),
    ]
    return DataLayout(locations=locations)


def _is_temp_file(path: Path) -> bool:
    name = path.name
    return (
        name.endswith(".tmp")
        or name.endswith("~")
        or name.startswith(".atomic_tmp")
        or name.startswith("tmp_")
    )


def is_supported_backup_file(
    path: Path,
    manager: AgentManager,
    credentials_path: Path | None = None,
) -> bool:
    """Determine whether a path is an eligible non-credential backup candidate."""
    try:
        # Must exist and be a regular file, not a symlink
        if not path.is_file() or path.is_symlink():
            return False

        resolved_path = path.resolve()
        cred_path = (credentials_path or default_credentials_path()).resolve()

        # Credentials are never supported for backup
        if resolved_path == cred_path:
            return False

        # Exclude temporary and swap files
        if _is_temp_file(path):
            return False

        # Must be relative to either agents_dir or diagnostics_dir
        agents_root = manager.agents_dir.resolve()
        diag_root = manager.get_diagnostics_dir().resolve()

        is_under_agents = False
        with contextlib.suppress(ValueError):
            resolved_path.relative_to(agents_root)
            is_under_agents = True

        is_under_diag = False
        with contextlib.suppress(ValueError):
            resolved_path.relative_to(diag_root)
            is_under_diag = True

        if not (is_under_agents or is_under_diag):
            return False

        # Verify no component in the relative chain is a symlink
        curr = path
        root = manager.agents_dir if is_under_agents else manager.get_diagnostics_dir()
        while curr != root and curr != curr.parent:
            if curr.is_symlink():
                return False
            curr = curr.parent

        return True
    except (OSError, ValueError):
        return False


def enumerate_supported_files(
    manager: AgentManager,
    credentials_path: Path | None = None,
) -> list[Path]:
    """Deterministically enumerate all supported files eligible for backup."""
    candidates: list[Path] = []

    def _scan_dir(root: Path) -> None:
        if not root.exists() or root.is_symlink():
            return
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = [d for d in sorted(dirnames) if not (Path(dirpath) / d).is_symlink()]
            for fname in sorted(filenames):
                file_path = Path(dirpath) / fname
                if is_supported_backup_file(file_path, manager, credentials_path):
                    candidates.append(file_path)

    _scan_dir(manager.agents_dir)
    _scan_dir(manager.get_diagnostics_dir())

    return sorted(candidates, key=lambda p: str(p))


def _compute_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def _archive_relative_path(file_path: Path, manager: AgentManager) -> str:
    resolved = file_path.resolve()
    agents_root = manager.agents_dir.resolve()
    diag_root = manager.get_diagnostics_dir().resolve()

    with contextlib.suppress(ValueError):
        rel = resolved.relative_to(agents_root)
        return f"agents/{rel.as_posix()}"

    with contextlib.suppress(ValueError):
        rel = resolved.relative_to(diag_root)
        return f"diagnostics/{rel.as_posix()}"

    raise ValueError(f"File '{file_path}' is outside supported roots")


def create_backup(
    manager: AgentManager,
    archive_path: Path,
    credentials_path: Path | None = None,
    overwrite: bool = False,
) -> BackupManifest:
    """Create an integrity-checked, versioned backup of supported local data."""
    if archive_path.is_dir():
        raise IsADirectoryError(f"Target archive path is a directory: {archive_path}")
    if archive_path.exists() and not overwrite:
        raise FileExistsError(f"Backup destination already exists: {archive_path}")

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    supported_files = enumerate_supported_files(manager, credentials_path=credentials_path)
    entries: list[ManifestFileEntry] = []
    total_bytes = 0

    for fp in supported_files:
        arc_rel = _archive_relative_path(fp, manager)
        sz = fp.stat().st_size
        sha = _compute_sha256(fp)
        entries.append(ManifestFileEntry(path=arc_rel, size=sz, sha256=sha))
        total_bytes += sz

    manifest = BackupManifest(
        version=BACKUP_ARCHIVE_VERSION,
        created_at=time.time(),
        files=entries,
        total_bytes=total_bytes,
    )

    tmp_archive = archive_path.parent / f".{archive_path.name}.tmp.{os.getpid()}"
    try:
        with zipfile.ZipFile(tmp_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            manifest_json = manifest.model_dump_json(indent=2)
            zf.writestr(MANIFEST_FILENAME, manifest_json)
            for fp in supported_files:
                arc_rel = _archive_relative_path(fp, manager)
                zf.write(fp, arcname=arc_rel)
        tmp_archive.chmod(0o600)
        tmp_archive.replace(archive_path)
    finally:
        if tmp_archive.exists():
            with contextlib.suppress(OSError):
                tmp_archive.unlink()

    return manifest
