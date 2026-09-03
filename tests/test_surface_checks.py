"""Regression tests for public package-surface gates."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).parents[1]


def test_public_surface_rejects_removed_module_filename(tmp_path: Path) -> None:
    script = tmp_path / "check-public-surface.sh"
    script.write_bytes((ROOT / "scripts/check-public-surface.sh").read_bytes())
    removed_module = "orchestration" + ".py"
    (tmp_path / "src" / "mia_agent").mkdir(parents=True)
    (tmp_path / "src" / "mia_agent" / removed_module).write_text("", encoding="utf-8")

    result = subprocess.run(["bash", str(script)], cwd=tmp_path, capture_output=True, text=True)

    assert result.returncode == 1
    assert "retired public surface" in result.stderr


def test_wheel_surface_rejects_flattened_removed_module(tmp_path: Path) -> None:
    wheel = tmp_path / "fixture.whl"
    removed_module = "profiles" + ".py"
    with ZipFile(wheel, "w", ZIP_DEFLATED) as archive:
        archive.writestr("mia_cli/tui/__init__.py", "")
        archive.writestr("mia_agent/" + removed_module, "")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-wheel-surface.py"), str(wheel)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "forbidden wheel paths" in result.stderr


def test_wheel_surface_rejects_removed_symbol(tmp_path: Path) -> None:
    wheel = tmp_path / "fixture.whl"
    removed_symbol = "Mode" + "Runtime"
    with ZipFile(wheel, "w", ZIP_DEFLATED) as archive:
        archive.writestr("mia_cli/tui/reintroduced.py", f"class {removed_symbol}: pass")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-wheel-surface.py"), str(wheel)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "retired public surface" in result.stderr


def test_wheel_surface_rejects_removed_module(tmp_path: Path) -> None:
    wheel = tmp_path / "fixture.whl"
    removed_module = "mia_agent/" + "orchestration.py"
    with ZipFile(wheel, "w", ZIP_DEFLATED) as archive:
        archive.writestr("mia_cli/tui/__init__.py", "")
        archive.writestr(removed_module, "")

    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/check-wheel-surface.py"), str(wheel)],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "forbidden wheel paths" in result.stderr
