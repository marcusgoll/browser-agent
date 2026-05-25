#!/usr/bin/env python3
"""Safe LinkedIn auth-state check using the persistent linkedin-profile."""
import asyncio
import sys

from social_auth_check import main

if __name__ == "__main__":
    if len(sys.argv) == 1 or sys.argv[1].startswith("-"):
        sys.argv.insert(1, "linkedin")
    raise SystemExit(asyncio.run(main()))
