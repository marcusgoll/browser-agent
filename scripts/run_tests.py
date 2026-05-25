#!/usr/bin/env python3
"""Canonical browser-agent test runner.

Run from the host with:
    docker compose run --rm browser-agent scripts/run_tests.py

This keeps dependency resolution inside the Docker image instead of relying on
host Python packages.
"""
from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tasks",
        "-q",
    ]
    print("Running canonical browser-agent tests:", " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
