#!/usr/bin/env python3
"""Safe X.com Google OAuth login probe for the browser-agent stack.

This script drives X.com only up to the attended Google OAuth boundary.
It never enters passwords, MFA codes, recovery details, or clicks through
OAuth consent. Marcus handles those steps manually in the VNC browser.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

X_LOGIN_URL = "https://x.com/i/flow/login"
GOOGLE_HOST_RE = re.compile(r"(^|\.)accounts\.google\.com$", re.I)


def sanitize_url(url: str) -> str:
    """Redact query/fragment values before logging OAuth URLs."""
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url or "")
        query = "[redacted]" if parsed.query or parsed.fragment else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))
    except Exception:
        return "[unparseable-url]"


def build_launch_args(user_agent: str = DEFAULT_USER_AGENT) -> List[str]:
    """Return Chromium launch args suitable for attended Google OAuth."""
    return [
        "--start-maximized",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        f"--user-agent={user_agent}",
    ]


def stealth_init_script() -> str:
    """Return browser init JavaScript that removes common automation flags."""
    return """
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en']
        });
        window.chrome = window.chrome || { runtime: {} };
        if (!window.chrome.runtime) {
            window.chrome.runtime = {};
        }
    """


def _is_google_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).hostname or ""
        return bool(GOOGLE_HOST_RE.search(host))
    except Exception:
        return False


def is_google_oauth_iframe_url(url: str) -> bool:
    """Return True for Google Identity Services OAuth button iframes."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url or "")
        host = parsed.hostname or ""
        return bool(GOOGLE_HOST_RE.search(host)) and parsed.path.startswith("/gsi/button")
    except Exception:
        return False


def classify_login_state(url: str, title: str = "", visible_text: str = "") -> Dict[str, Any]:
    """Classify the current X/Google OAuth login state without secrets."""
    text = " ".join((title or "", visible_text or "")).strip()
    lowered = text.lower()
    url_lower = (url or "").lower()

    if "x.com/home" in url_lower or "twitter.com/home" in url_lower:
        return {
            "status": "logged_in",
            "requires_user": False,
            "next_action": "X home loaded. The saved browser profile appears authenticated.",
        }

    if "single_sign_on" in url_lower or "oops, something went wrong" in lowered:
        return {
            "status": "x_single_sign_on_blocked",
            "requires_user": True,
            "next_action": "X blocked the OAuth callback. Use a real-browser cookie import or attended browser refresh instead of retrying blindly.",
        }

    if "couldn't sign you in" in lowered and "browser or app may not be secure" in lowered:
        return {
            "status": "google_insecure_browser_blocked",
            "requires_user": True,
            "next_action": "Google rejected the automated browser. Use the VNC secure login helper or a real desktop browser session.",
        }

    if _is_google_url(url) or "use your google account" in lowered:
        return {
            "status": "google_oauth_boundary",
            "requires_user": True,
            "next_action": "Marcus must complete Google account selection, password/MFA, and consent manually. The agent stops here.",
        }

    if "continue with google" in lowered or "sign in with google" in lowered:
        return {
            "status": "x_login_google_option",
            "requires_user": False,
            "next_action": "X login screen loaded with Google OAuth option; click Google and stop at the attended Google boundary.",
        }

    if "see what's happening" in lowered and "email or username" in lowered:
        return {
            "status": "x_login_no_google_option",
            "requires_user": True,
            "next_action": "X login screen loaded, but Google OAuth is not currently offered in this browser/session. Try an attended VNC session or use the real-browser cookie import path.",
        }

    if "sign in to x" in lowered or "log in to x" in lowered or "/i/flow/login" in url_lower:
        return {
            "status": "x_login_screen",
            "requires_user": False,
            "next_action": "X login screen loaded; continue by clicking the Google OAuth button if present.",
        }

    return {
        "status": "unknown",
        "requires_user": True,
        "next_action": "Review the visible browser state manually before proceeding.",
    }


async def _safe_visible_text(page: Any, max_chars: int = 4000) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""
    return text[:max_chars]


async def _page_has_google_oauth_iframe(page: Any) -> bool:
    for frame in page.frames:
        if is_google_oauth_iframe_url(getattr(frame, "url", "")):
            return True
    try:
        return await page.locator("iframe[src*='accounts.google.com/gsi/button']").count() > 0
    except Exception:
        return False


async def _classify_page_state(page: Any) -> Dict[str, Any]:
    state = classify_login_state(
        page.url,
        await page.title(),
        await _safe_visible_text(page),
    )
    if state["status"] == "x_login_no_google_option" and await _page_has_google_oauth_iframe(page):
        return {
            "status": "x_login_google_option",
            "requires_user": False,
            "next_action": "X login screen loaded with a Google OAuth iframe; click Google and stop at the attended Google boundary.",
        }
    return state


async def _click_google_login_button(page: Any, timeout_ms: int = 12000) -> bool:
    before_url = page.url

    # Google Identity Services renders the visible button inside a cross-origin
    # iframe, so body text often omits "Continue with Google". Click the iframe
    # center first when present.
    try:
        iframe = page.locator("iframe[src*='accounts.google.com/gsi/button']").first
        box = await iframe.bounding_box(timeout=3000)
        if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
            async with page.expect_popup(timeout=5000) as popup_info:
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            popup = await popup_info.value
            await popup.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
            await popup.bring_to_front()
            return True
    except Exception:
        try:
            iframe = page.locator("iframe[src*='accounts.google.com/gsi/button']").first
            box = await iframe.bounding_box(timeout=1000)
            if box and box.get("width", 0) > 0 and box.get("height", 0) > 0:
                await page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                await page.wait_for_timeout(5000)
                return page.url != before_url or await _page_has_google_oauth_iframe(page)
        except Exception:
            pass

    candidates = [
        page.get_by_text(re.compile(r"sign in with google", re.I)),
        page.get_by_text(re.compile(r"continue with google", re.I)),
        page.locator("[data-testid='google_sign_in_container']"),
    ]

    deadline = time.monotonic() + (timeout_ms / 1000)
    last_error: Optional[Exception] = None
    for locator in candidates:
        remaining_ms = max(1000, int((deadline - time.monotonic()) * 1000))
        if remaining_ms <= 0:
            break
        try:
            await locator.first.click(timeout=remaining_ms)
            return True
        except Exception as exc:  # Playwright timeout/strictness variants
            last_error = exc
            continue

    if last_error:
        print(f"[x-google-oauth] Google button not clicked: {type(last_error).__name__}: {last_error}", file=sys.stderr)
    return False


async def probe_x_google_oauth(
    profile_name: str,
    headless: bool,
    timeout_seconds: int,
    output_dir: str = OUTPUT_DIR,
    user_agent: str = DEFAULT_USER_AGENT,
    hold_seconds: int = 0,
) -> Dict[str, Any]:
    """Open X login, click Google OAuth if possible, and stop at safe boundary."""
    from playwright.async_api import async_playwright

    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)
    try:
        profile_path.chmod(0o700)
    except PermissionError:
        pass

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            args=build_launch_args(user_agent),
            bypass_csp=True,
            java_script_enabled=True,
            viewport={"width": 1440, "height": 1000},
        )
        page = await browser.new_page()
        await page.add_init_script(stealth_init_script())

        try:
            await page.goto(X_LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_seconds * 1000)
            await page.wait_for_timeout(4000)

            initial = await _classify_page_state(page)

            clicked_google = False
            active_page = page
            if initial["status"] in {"x_login_screen", "x_login_google_option", "unknown"}:
                clicked_google = await _click_google_login_button(page)
                if clicked_google:
                    await page.wait_for_timeout(8000)
                    if page.context.pages:
                        active_page = page.context.pages[-1]

            final = await _classify_page_state(active_page)
            final_title = await active_page.title()

            screenshot_path = output_path / f"x_google_oauth_{profile_name}_{int(time.time())}.png"
            await active_page.screenshot(path=str(screenshot_path), full_page=True)

            result = {
                "target": "x.com_google_oauth",
                "profile": profile_name,
                "profile_path": str(profile_path),
                "headless": headless,
                "initial_status": initial["status"],
                "clicked_google": clicked_google,
                "final_url": sanitize_url(active_page.url),
                "final_title": final_title,
                "final_status": final["status"],
                "requires_user": final["requires_user"],
                "next_action": final["next_action"],
                "screenshot_path": str(screenshot_path),
            }
            if hold_seconds > 0 and not headless and result["requires_user"]:
                print(
                    f"[x-google-oauth] Holding attended browser open for {hold_seconds}s. "
                    "Complete login in VNC; close the browser when done.",
                    flush=True,
                )
                await active_page.wait_for_timeout(hold_seconds * 1000)
        finally:
            await browser.close()

    result_path = output_path / f"x_google_oauth_{profile_name}_{int(time.time())}.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True))
    result["result_path"] = str(result_path)
    return result


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Probe X.com Google OAuth login safely")
    parser.add_argument("--profile", default="x-google-oauth", help="Persistent browser profile name")
    parser.add_argument("--headless", action="store_true", help="Run headless; default is headed for VNC")
    parser.add_argument("--timeout", type=int, default=45, help="Navigation timeout seconds")
    parser.add_argument(
        "--hold-seconds",
        type=int,
        default=0,
        help="In headed/VNC mode, keep browser open this many seconds at a user-action boundary",
    )
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="Output directory for result/screenshot")
    args = parser.parse_args()

    result = await probe_x_google_oauth(
        profile_name=args.profile,
        headless=args.headless,
        timeout_seconds=args.timeout,
        output_dir=args.output_dir,
        hold_seconds=args.hold_seconds,
    )
    print(json.dumps(result, indent=2, sort_keys=True))

    # Expected safe outcomes for unattended test runs. Actual credential/MFA
    # completion remains attended and is not automated by this script.
    if result["final_status"] in {
        "google_oauth_boundary",
        "logged_in",
        "x_single_sign_on_blocked",
        "google_insecure_browser_blocked",
        "x_login_screen",
        "x_login_google_option",
        "x_login_no_google_option",
    }:
        return 0
    return 2


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
