"""Tests for the release notes generator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "chargeamps_cloud" / "manifest.json"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/release_notes.py", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_current_version_has_release_notes() -> None:
    result = run("--check")
    assert result.returncode == 0, result.stderr
    assert "### Added" in result.stdout


def test_release_notes_include_compare_link() -> None:
    version = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    result = run(f"v{version}")
    assert result.returncode == 0, result.stderr
    assert "Full changelog:" in result.stdout
    assert "compare/v" in result.stdout


def test_unknown_tag_is_rejected() -> None:
    result = run("v9.9.9")
    assert result.returncode != 0
    assert "does not match" in result.stderr
