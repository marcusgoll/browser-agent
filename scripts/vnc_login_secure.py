#!/usr/bin/env python3
"""
Interactive login helper with Google OAuth compatibility.
Uses a realistic user agent and disables automation flags.
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")

# Realistic Chrome user agent to avoid "browser not secure" errors
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


async def interactive_login(site: str, profile_name: str):
    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)

    print(f"[login-helper] Launching secure browser for: {site}")
    print(f"[login-helper] Profile will be saved to: {profile_path}")
    print("[login-helper] Log in manually, then press Ctrl+C to save and exit.")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            args=[
                "--start-maximized",
                "--no-sandbox",
                # Disable automation flags
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
                # Spoof as real Chrome
                f"--user-agent={USER_AGENT}",
            ],
            bypass_csp=True,
            java_script_enabled=True,
        )
        # Remove webdriver property
        page = await browser.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            window.chrome = { runtime: {} };
        """)
        await page.goto(site)

        # Wait for user to signal done
        try:
            while True:
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
