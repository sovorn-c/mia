"""Deterministic tests for Mia product, operator, and plugin documentation."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

DOC_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "README.md",
    REPO_ROOT / "docs" / "user-guide.md",
    REPO_ROOT / "docs" / "operator-guide.md",
    REPO_ROOT / "docs" / "plugin-author-guide.md",
]


def test_required_documentation_files_exist() -> None:
    for doc in DOC_FILES:
        assert doc.is_file(), f"Required documentation file missing: {doc}"
        assert doc.stat().st_size > 0, f"Documentation file is empty: {doc}"


def test_markdown_internal_links_resolve() -> None:
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for doc in DOC_FILES:
        if not doc.is_file():
            continue
        text = doc.read_text(encoding="utf-8")
        for match in link_pattern.finditer(text):
            target = match.group(2)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part = target.split("#")[0]
            if not path_part:
                continue
            resolved = (doc.parent / path_part).resolve()
            assert resolved.exists(), f"Broken link in {doc.name}: {target} -> {resolved}"


def test_readme_links_to_all_guides() -> None:
    readme = REPO_ROOT / "README.md"
    assert readme.is_file()
    content = readme.read_text(encoding="utf-8")
    assert "docs/README.md" in content or "docs/" in content
    assert "docs/user-guide.md" in content
    assert "docs/operator-guide.md" in content
    assert "docs/plugin-author-guide.md" in content


def test_user_guide_covers_required_topics() -> None:
    guide = REPO_ROOT / "docs" / "user-guide.md"
    assert guide.is_file()
    content = guide.read_text(encoding="utf-8")
    for keyword in [
        "uv sync",
        "mia run",
        "mia agent",
        "NO_COLOR",
        "--plain",
        "login",
        "access",
        "keyboard",
    ]:
        assert keyword in content, f"Missing required keyword '{keyword}' in {guide.name}"


def test_operator_guide_covers_required_topics() -> None:
    guide = REPO_ROOT / "docs" / "operator-guide.md"
    assert guide.is_file()
    content = guide.read_text(encoding="utf-8")
    for keyword in [
        "diagnostics",
        "data locations",
        "backup",
        "restore",
        "recovery",
        "non-destructive",
        "credential",
    ]:
        assert keyword.lower() in content.lower(), (
            f"Missing required keyword '{keyword}' in {guide.name}"
        )


def test_plugin_author_guide_covers_required_topics() -> None:
    guide = REPO_ROOT / "docs" / "plugin-author-guide.md"
    assert guide.is_file()
    content = guide.read_text(encoding="utf-8")
    for keyword in [
        "trust",
        "provenance",
        "static",
        "contribution",
        "lifecycle",
        "sandbox",
        "Core",
    ]:
        assert keyword.lower() in content.lower(), (
            f"Missing required keyword '{keyword}' in {guide.name}"
        )


def test_documentation_contains_no_real_secret_values() -> None:
    secret_patterns = [
        re.compile(r"sk-ant-api03-[A-Za-z0-9_-]{20,}"),
        re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
        re.compile(r"AIzaSy[A-Za-z0-9_-]{33}"),
        re.compile(r"ghp_[A-Za-z0-9]{36}"),
    ]
    for doc in DOC_FILES:
        if not doc.is_file():
            continue
        content = doc.read_text(encoding="utf-8")
        for pat in secret_patterns:
            assert not pat.search(content), f"Potential credential leak found in {doc.name}"


def test_documented_cli_commands_are_valid() -> None:
    valid_subcmds = {
        "run",
        "login",
        "tui",
        "agent",
        "sessions",
        "plugin",
        "template",
        "diagnostics",
        "data",
    }
    command_line_pattern = re.compile(r"^[ \t]*mia[ \t]+([a-z0-9_-]+)", re.MULTILINE)
    for doc in DOC_FILES:
        if not doc.is_file():
            continue
        content = doc.read_text(encoding="utf-8")
        for match in command_line_pattern.finditer(content):
            subcmd = match.group(1)
            if subcmd.startswith("-"):
                continue
            assert subcmd in valid_subcmds, (
                f"Unknown CLI command 'mia {subcmd}' found in {doc.name}"
            )
