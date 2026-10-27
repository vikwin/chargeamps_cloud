#!/usr/bin/env python3
"""Copy the library into the integration so HACS installs stay self-contained."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "lib" / "src" / "chargeamps_cloud"
TARGET = ROOT / "custom_components" / "chargeamps_cloud" / "chargeamps_cloud"


def _files(root: Path) -> dict[Path, str]:
    result: dict[Path, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        result[path.relative_to(root)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check() -> int:
    if not TARGET.is_dir():
        print(f"Missing vendored copy at {TARGET}", file=sys.stderr)
        return 1
    source_files = _files(SOURCE)
    target_files = _files(TARGET)
    missing = sorted(source_files.keys() - target_files.keys())
    extra = sorted(target_files.keys() - source_files.keys())
    changed = sorted(
        name for name in source_files.keys() & target_files.keys() if source_files[name] != target_files[name]
    )
    if missing or extra or changed:
        for name in missing:
            print(f"missing in integration: {name}", file=sys.stderr)
        for name in extra:
            print(f"only in integration: {name}", file=sys.stderr)
        for name in changed:
            print(f"out of date: {name}", file=sys.stderr)
        print("Run scripts/sync_lib.py to update the vendored copy.", file=sys.stderr)
        return 1
    print(f"Vendored library is up to date ({len(source_files)} files)")
    return 0


def sync() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    shutil.copytree(
        SOURCE,
        TARGET,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    print(f"Copied {SOURCE} -> {TARGET}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Only verify that the vendored copy is current")
    args = parser.parse_args()
    return check() if args.check else sync()


if __name__ == "__main__":
    raise SystemExit(main())
