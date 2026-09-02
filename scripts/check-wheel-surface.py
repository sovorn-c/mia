"""Check the built wheel keeps the supported TUI and omits removed packages."""

from __future__ import annotations

import glob
import zipfile

wheels = sorted(glob.glob("dist/*.whl"))
assert wheels, "no wheel found"
with zipfile.ZipFile(wheels[-1]) as wheel:
    names = set(wheel.namelist())
    assert any(name.startswith("mia_cli/tui/") for name in names)
    assert not any(
        name.startswith(("mia_agent/profiles/", "mia_agent/herd/", "mia_agent/mode_runtime"))
        for name in names
    )
print("wheel surface is clean and TUI is retained")
