#!/usr/bin/env python3
"""Safe X auth-state check using the persistent x-profile."""
import asyncio
import sys

from social_auth_check import main

if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
        sys.argv.insert(1, "x")
    raise SystemExit(asyncio.run(main()))
