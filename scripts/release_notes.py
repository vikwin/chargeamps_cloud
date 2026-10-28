#!/usr/bin/env python3
"""Build GitHub release notes from a version section in CHANGELOG.md."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
MANIFEST = ROOT / "custom_components" / "chargeamps_cloud" / "manifest.json"
DEFAULT_REPOSITORY = "vikwin/chargeamps_cloud"

_HEADING = re.compile(
    r"^##\s+\[?v?(?P<version>\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\]?"
    r"(?:\s+-\s+.*)?$",
    re.MULTILINE,
)


def manifest_version() -> str:
    return str(json.loads(MANIFEST.read_text(encoding="utf-8"))["version"])


def sections() -> list[tuple[str, str]]:
    text = CHANGELOG.read_text(encoding="utf-8")
    matches = list(_HEADING.finditer(text))
    result: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result.append((match.group("version"), text[start:end].strip()))
    return result


def release_notes(tag: str) -> str:
    version = tag[1:] if tag.startswith("v") else tag
    expected = manifest_version()
    if version != expected:
        raise SystemExit(
            f"Tag {tag} does not match the integration version {expected}. "
            "Bump custom_components/chargeamps_cloud/manifest.json before tagging."
        )
    entries = sections()
    for index, (entry_version, body) in enumerate(entries):
        if entry_version != version:
            continue
        if not body:
            raise SystemExit(f"The CHANGELOG section for {version} is empty")
        previous = entries[index + 1][0] if index + 1 < len(entries) else None
        notes = f"## What changed in {version}\n\n{body}"
        if previous:
            repository = os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY)
            notes += f"\n\n---\n\n**Full changelog:** https://github.com/{repository}/compare/v{previous}...v{version}"
        return notes
    raise SystemExit(f"No CHANGELOG section for {version}. Add '## {version} - YYYY-MM-DD' to CHANGELOG.md.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag", nargs="?", help="Release tag, for example v0.2.0")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that the manifest version has a non-empty CHANGELOG section",
    )
    args = parser.parse_args(argv)
    tag = args.tag or os.environ.get("GITHUB_REF_NAME", "")
    if args.check:
        tag = f"v{manifest_version()}"
    if not tag:
        parser.error("A tag is required (or set GITHUB_REF_NAME)")
    print(release_notes(tag))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
