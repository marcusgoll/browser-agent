#!/usr/bin/env python3
"""Attended headed login helper that auto-closes once auth is detected.

This uses visible page state only. It does not read/export cookies, localStorage,
sessionStorage, saved passwords, or browser profile databases.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

from social_auth_check import (
    AUTHENTICATED,
    PLATFORMS,
    PROFILE_DIR,
    build_launch_args,
    sanitize_url,
    stealth_init_script,
    _safe_visible_text,
)

LOGIN_URLS = {
    "x": "https://x.com/i/flow/login",
    "linkedin": "https://www.linkedin.com/login",
    "reddit": "https://www.reddit.com/login/",
}


async def attended_login_until_auth(platform: str, profile_name: str | None, timeout: int, poll_seconds: int) -> dict:
    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform: {platform}")

    from playwright.async_api import async_playwright

    cfg = PLATFORMS[platform]
    profile = profile_name or cfg["profile"]
    profile_path = Path(PROFILE_DIR) / profile
    profile_path.mkdir(parents=True, exist_ok=True)
    started = time.time()
    deadline = started + timeout
    last_state = None

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=False,
            args=["--start-maximized", *build_launch_args()],
            bypass_csp=True,
            java_script_enabled=True,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(stealth_init_script())
            await page.goto(LOGIN_URLS.get(platform, cfg["url"]), wait_until="domcontentloaded", timeout=30000)
            print(json.dumps({
                "event": "attended_login_started",
                "platform": platform,
                "profile": profile,
                "url": sanitize_url(page.url),
                "deadline_seconds": timeout,
                "instruction": "Complete login in the visible browser. This helper will auto-close when authenticated.",
            }, sort_keys=True), flush=True)

            while time.time() < deadline:
                await page.wait_for_timeout(poll_seconds * 1000)
                try:
                    # Prefer the normal authenticated URL after login, but do not fight the user while they are on MFA/challenge pages.
                    if "login" not in (page.url or "").lower() and platform == "reddit":
                        await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=30000)
                        await page.wait_for_timeout(2000)
                    title = await page.title()
                    visible_text = await _safe_visible_text(page)
                    state = cfg["classifier"](page.url, title, visible_text)
                    state_msg = {
                        "event": "auth_poll",
                        "platform": platform,
                        "profile": profile,
                        "status": state["status"],
                        "reason": state["reason"],
                        "url": sanitize_url(page.url),
                        "elapsed_seconds": int(time.time() - started),
                    }
                    if state_msg != last_state:
                        print(json.dumps(state_msg, sort_keys=True), flush=True)
                        last_state = state_msg
                    if state["status"] == AUTHENTICATED:
                        result = {
                            "platform": platform,
                            "profile": profile,
                            "status": AUTHENTICATED,
                            "reason": state["reason"],
                            "url": sanitize_url(page.url),
                            "elapsed_seconds": int(time.time() - started),
                        }
                        print(json.dumps({"event": "authenticated_closing_browser", **result}, sort_keys=True), flush=True)
                        return result
                except Exception as exc:
                    print(json.dumps({"event": "auth_poll_error", "error": type(exc).__name__}, sort_keys=True), flush=True)

            return {
                "platform": platform,
                "profile": profile,
                "status": "timeout",
                "reason": "attended_login_timeout",
                "url": sanitize_url(page.url),
                "elapsed_seconds": int(time.time() - started),
            }
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Attended login helper that auto-closes after authenticated state is visible")
    parser.add_argument("platform", choices=sorted(PLATFORMS), help="Platform to log into")
    parser.add_argument("--profile", help="Browser profile name. Defaults to platform profile.")
    parser.add_argument("--timeout", type=int, default=900, help="Max seconds to wait for attended login")
    parser.add_argument("--poll-seconds", type=int, default=5, help="Polling interval")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    result = await attended_login_until_auth(args.platform, args.profile, args.timeout, args.poll_seconds)
    print(json.dumps({"event": "result", **result}, indent=2, sort_keys=True), flush=True)
    return 0 if result["status"] == AUTHENTICATED else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
