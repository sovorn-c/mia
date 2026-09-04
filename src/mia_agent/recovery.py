"""Read-only recovery verification, corruption detection, and safe operator guidance."""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from mia_agent.agents.manager import AgentManager
from mia_agent.agents.model import Agent

RecoveryStatus = Literal["clean", "attention", "blocked"]
FindingStatus = Literal["attention", "blocked"]


class RecoveryFinding(BaseModel):
    """Sanitized diagnostic report of an interrupted, corrupt, or unsupported file."""

    category: str
    status: FindingStatus
    path: str
    evidence: str
    action: str


class RecoveryReport(BaseModel):
    """Overall report summarizing local data integrity and findings."""

    status: RecoveryStatus
    findings: list[RecoveryFinding] = Field(default_factory=list)
    files_scanned: int = 0
    clean_files: int = 0


class RecoveryVerifier:
    """Deterministic, read-only verifier of supported local Agent, Session, and Diagnostic data."""

    def __init__(self, manager: AgentManager | None = None) -> None:
        self.manager = manager or AgentManager()

    def _relative_path(self, path: Path) -> str:
        agents_root = self.manager.agents_dir.resolve()
        diag_root = self.manager.get_diagnostics_dir().resolve()
        resolved = path.resolve()

        with contextlib.suppress(ValueError):
            return f"agents/{resolved.relative_to(agents_root).as_posix()}"
        with contextlib.suppress(ValueError):
            return f"diagnostics/{resolved.relative_to(diag_root).as_posix()}"
        return path.name

    def verify(self) -> RecoveryReport:
        """Scan supported local data boundaries without modifying any files."""
        findings: list[RecoveryFinding] = []
        scanned_count = 0
        agents_root = self.manager.agents_dir
        diag_root = self.manager.get_diagnostics_dir()

        def _check_file(file_path: Path) -> None:
            nonlocal scanned_count
            scanned_count += 1
            rel = self._relative_path(file_path)

            # 1. Check if file is a symlink
            if file_path.is_symlink():
                findings.append(
                    RecoveryFinding(
                        category="path",
                        status="blocked",
                        path=rel,
                        evidence=f"Symlink detected inside data root: {file_path.name}",
                        action="Remove symlink and restore authentic data from backup",
                    )
                )
                return

            # 2. Check for orphan atomic-write artifacts or temporary files
            name = file_path.name
            if name.startswith(".atomic_tmp") or name.endswith(".tmp") or name.endswith("~"):
                findings.append(
                    RecoveryFinding(
                        category="atomic_write",
                        status="attention",
                        path=rel,
                        evidence=f"Orphan atomic-write temporary artifact: {name}",
                        action="Inspect orphan temporary file and restore from verified backup if needed",
                    )
                )
                return

            # 3. Check agent.json
            if name == "agent.json":
                try:
                    content = file_path.read_text(encoding="utf-8")
                    Agent.model_validate_json(content)
                except Exception as exc:
                    findings.append(
                        RecoveryFinding(
                            category="schema",
                            status="blocked",
                            path=rel,
                            evidence=f"Malformed agent definition: {exc}",
                            action="Restore agent definition from verified backup using 'mia data restore'",
                        )
                    )
                return

            # 4. Check JSONL files (session or diagnostics)
            if name.endswith(".jsonl"):
                is_diag = name == "diagnostics.jsonl" or rel.startswith("diagnostics/")
                cat = "diagnostics" if is_diag else "session"
                target_label = "diagnostic record" if is_diag else "session append"
                try:
                    raw_lines = file_path.read_bytes().split(b"\n")
                    non_empty_indices = [i for i, line in enumerate(raw_lines) if line.strip()]
                    for pos, idx in enumerate(non_empty_indices):
                        line_bytes = raw_lines[idx]
                        is_last_item = pos == len(non_empty_indices) - 1
                        try:
                            json.loads(line_bytes.decode("utf-8"))
                        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                            if is_last_item:
                                findings.append(
                                    RecoveryFinding(
                                        category=cat,
                                        status="attention",
                                        path=rel,
                                        evidence=f"Truncated final {target_label} detected at line {idx + 1}: {exc}",
                                        action=f"Preserve {cat} file and restore from verified backup if needed",
                                    )
                                )
                            else:
                                findings.append(
                                    RecoveryFinding(
                                        category=cat,
                                        status="blocked",
                                        path=rel,
                                        evidence=f"Interior corruption detected in {cat} at line {idx + 1}: {exc}",
                                        action=f"Restore {cat} from verified backup using 'mia data restore'",
                                    )
                                )
                except OSError as exc:
                    findings.append(
                        RecoveryFinding(
                            category=cat,
                            status="blocked",
                            path=rel,
                            evidence=f"Failed to read {cat} file: {exc}",
                            action="Check disk permissions or restore from backup",
                        )
                    )
                return

        def _scan_tree(root: Path) -> None:
            if not root.exists():
                return
            if root.is_symlink():
                findings.append(
                    RecoveryFinding(
                        category="path",
                        status="blocked",
                        path=self._relative_path(root),
                        evidence=f"Root directory is a symlink: {root.name}",
                        action="Replace symlink with genuine directory",
                    )
                )
                return

            for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                # Check for symlink directory escapes
                for d in list(dirnames):
                    d_path = Path(dirpath) / d
                    if d_path.is_symlink():
                        dirnames.remove(d)
                        findings.append(
                            RecoveryFinding(
                                category="path",
                                status="blocked",
                                path=self._relative_path(d_path),
                                evidence=f"Symlink directory detected inside data root: {d}",
                                action="Remove symlink and restore authentic data from backup",
                            )
                        )

                for f in sorted(filenames):
                    _check_file(Path(dirpath) / f)

        _scan_tree(agents_root)
        _scan_tree(diag_root)

        # Calculate overall status based on precedence: blocked > attention > clean
        if any(f.status == "blocked" for f in findings):
            overall_status: RecoveryStatus = "blocked"
        elif any(f.status == "attention" for f in findings):
            overall_status = "attention"
        else:
            overall_status = "clean"

        flagged_paths = {f.path for f in findings}
        clean_count = max(0, scanned_count - len(flagged_paths))

        return RecoveryReport(
            status=overall_status,
            findings=findings,
            files_scanned=scanned_count,
            clean_files=clean_count,
        )


def verify_recovery(manager: AgentManager | None = None) -> RecoveryReport:
    """Run deterministic read-only recovery verification over supported local data."""
    return RecoveryVerifier(manager=manager).verify()
