#!/usr/bin/env python3
"""Run every plugin-local test directory in isolated unittest processes."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_directories() -> list[Path]:
    directories = {
        path
        for pattern in ("plugins/*/tests", "plugins/*/skills/*/tests")
        for path in ROOT.glob(pattern)
        if path.is_dir()
    }
    return sorted(directories)


def main() -> int:
    directories = test_directories()
    if not directories:
        print("No plugin-local tests found.", file=sys.stderr)
        return 1
    for directory in directories:
        print(f"\n== {directory.relative_to(ROOT)} ==", flush=True)
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                "-m",
                "unittest",
                "discover",
                "-s",
                str(directory),
                "-p",
                "test_*.py",
                "-v",
            ],
            cwd=ROOT,
            check=False,
        )
        if result.returncode:
            return result.returncode
    print(f"\nPlugin-local test directories passed: {len(directories)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
