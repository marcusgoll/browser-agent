#!/usr/bin/env python3
"""
Interactive login helper.
Runs a headed browser so you can log in manually.
Saves cookies/localStorage to a named profile for later headless use.
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")


async def interactive_login(site: str, profile_name: str):
    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)

    print(f"[login-helper] Launching headed browser for: {site}")
    print(f"[login-helper] Profile will be saved to: {profile_path}")
    print("[login-helper] Log in manually, then close the browser window.")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            args=["--start-maximized"],
        )
        page = await browser.new_page()
        await page.goto(site)

        # Wait for user to close browser
        try:
            while len(browser.pages) > 0:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            pass

        await browser.close()

    print(f"[login-helper] Profile saved: {profile_path}")
    print(f"[login-helper] You can now run headless tasks with --profile {profile_name}")


async def main():
    parser = argparse.ArgumentParser(description="Interactive login to save session")
    parser.add_argument("site", help="URL to open (e.g. https://x.com)")
    parser.add_argument("--profile", default="default", help="Profile name")
    args = parser.parse_args()

    await interactive_login(args.site, args.profile)


if __name__ == "__main__":
    asyncio.run(main())
