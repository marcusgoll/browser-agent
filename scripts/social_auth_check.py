#!/usr/bin/env python3
"""Safe browser-profile auth readiness checks for social platforms.

The checks classify visible page state only. They do not read, print, export,
or summarize cookies, localStorage, sessionStorage, tokens, saved passwords, or
browser profile databases.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse, urlunparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from proof_bundle import SECRETS_POLICY, build_metadata, write_metadata

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

AUTHENTICATED = "authenticated"
LOGIN_REQUIRED = "login_required"
MFA_OR_CHALLENGE_REQUIRED = "mfa_or_challenge_required"
UNKNOWN = "unknown"

NORMALIZED_STATUS = {
    AUTHENTICATED: "authenticated",
    LOGIN_REQUIRED: "expired",
    MFA_OR_CHALLENGE_REQUIRED: "requires_user",
    UNKNOWN: "ambiguous",
}

CHALLENGE_PATTERNS = [
    r"two[- ]?factor",
    r"2fa",
    r"multi[- ]?factor",
    r"verification code",
    r"security code",
    r"authenticator",
    r"passkey",
    r"confirm (it'?s )?you",
    r"verify (it'?s )?you",
    r"verify your identity",
    r"suspicious",
    r"unusual activity",
    r"account recovery",
    r"checkpoint",
    r"captcha",
    r"consent",
    r"permissions",
]


def sanitize_url(url: str) -> str:
    """Redact query and fragment values before writing URLs to logs/results."""
    try:
        parsed = urlparse(url or "")
        query = "[redacted]" if parsed.query or parsed.fragment else ""
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, ""))
    except Exception:
        return "[unparseable-url]"


def build_launch_args(user_agent: str = DEFAULT_USER_AGENT) -> List[str]:
    return [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-blink-features=AutomationControlled",
        "--disable-features=IsolateOrigins,site-per-process",
        f"--user-agent={user_agent}",
    ]


def stealth_init_script() -> str:
    return """
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
        Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
        window.chrome = window.chrome || { runtime: {} };
        if (!window.chrome.runtime) { window.chrome.runtime = {}; }
    """


def _has_any(text: str, patterns: List[str]) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, re.I) for pattern in patterns)


def _challenge_reason(text: str, url: str) -> Optional[str]:
    host = (urlparse(url).hostname or "").lower() if url else ""
    if host.endswith("accounts.google.com"):
        return "google_oauth_or_account_challenge"
    if _has_any(text, CHALLENGE_PATTERNS):
        return "mfa_security_or_consent_challenge"
    return None


def _state(status: str, reason: str, next_action: str, screenshot_required: bool = False) -> Dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "screenshot_required": screenshot_required,
    }


def classify_x_state(url: str, title: str = "", visible_text: str = "") -> Dict[str, Any]:
    text = " ".join([title or "", visible_text or ""])
    lowered = text.lower()
    url_lower = (url or "").lower()
    if "/home" in url_lower or "x.com/home" in url_lower or "twitter.com/home" in url_lower:
        return _state(AUTHENTICATED, "x_home_loaded", "Saved X profile appears authenticated.")
    if "what is happening" in lowered and ("for you" in lowered or "following" in lowered):
        return _state(AUTHENTICATED, "x_timeline_markers_visible", "Saved X profile appears authenticated.")
    # Authenticated permalink pages do not show the home timeline markers, but
    # they do show the logged-in shell: left nav, compose button, and account
    # identity. Recognize that shell before falling through to unknown so
    # approved reply publishing can proceed on target tweet URLs.
    logged_in_shell_markers = ["home", "explore", "notifications", "bookmarks", "profile", "post"]
    if sum(1 for marker in logged_in_shell_markers if marker in lowered) >= 5 and not (
        "log in to x" in lowered or "sign in to x" in lowered or "phone, email, or username" in lowered
    ):
        return _state(AUTHENTICATED, "x_logged_in_shell_visible", "Saved X profile appears authenticated.")
    challenge = _challenge_reason(text, url)
    if challenge:
        return _state(MFA_OR_CHALLENGE_REQUIRED, challenge, "Stop and request attended login/verification refresh.", True)
    if "/i/flow/login" in url_lower or "log in to x" in lowered or "sign in to x" in lowered or "phone, email, or username" in lowered:
        return _state(LOGIN_REQUIRED, "x_login_screen", "Use attended VNC login or refresh/import the persistent X profile.", True)
    return _state(UNKNOWN, "x_state_unrecognized", "Review the browser state manually before using this profile.", True)


def classify_linkedin_state(url: str, title: str = "", visible_text: str = "") -> Dict[str, Any]:
    text = " ".join([title or "", visible_text or ""])
    lowered = text.lower()
    url_lower = (url or "").lower()
    if "/feed" in url_lower or "start a post" in lowered or ("messaging" in lowered and "notifications" in lowered and "home" in lowered):
        return _state(AUTHENTICATED, "linkedin_feed_markers_visible", "Saved LinkedIn profile appears authenticated.")
    challenge = _challenge_reason(text, url)
    if challenge:
        return _state(MFA_OR_CHALLENGE_REQUIRED, challenge, "Stop and request attended LinkedIn verification refresh.", True)
    if "/login" in url_lower or "sign in" in lowered and "email or phone" in lowered:
        return _state(LOGIN_REQUIRED, "linkedin_login_screen", "Use attended VNC login with linkedin-profile.", True)
    return _state(UNKNOWN, "linkedin_state_unrecognized", "Review the browser state manually before using this profile.", True)


def classify_reddit_state(url: str, title: str = "", visible_text: str = "") -> Dict[str, Any]:
    text = " ".join([title or "", visible_text or ""])
    lowered = text.lower()
    url_lower = (url or "").lower()
    if "create post" in lowered or "profile" in lowered and "log in" not in lowered:
        return _state(AUTHENTICATED, "reddit_logged_in_markers_visible", "Saved Reddit profile appears authenticated.")
    challenge = _challenge_reason(text, url)
    if challenge:
        return _state(MFA_OR_CHALLENGE_REQUIRED, challenge, "Stop and request attended Reddit verification refresh.", True)
    if "/login" in url_lower or "log in" in lowered and ("sign up" in lowered or "username" in lowered):
        return _state(LOGIN_REQUIRED, "reddit_login_screen", "Use attended VNC login with reddit-profile.", True)
    return _state(UNKNOWN, "reddit_state_unrecognized", "Review the browser state manually before using this profile.", True)


PLATFORMS: Dict[str, Dict[str, Any]] = {
    "x": {
        "url": "https://x.com/home",
        "profile": "x-profile",
        "classifier": classify_x_state,
    },
    "linkedin": {
        "url": "https://www.linkedin.com/feed/",
        "profile": "linkedin-profile",
        "classifier": classify_linkedin_state,
    },
    "reddit": {
        "url": "https://www.reddit.com/",
        "profile": "reddit-profile",
        "classifier": classify_reddit_state,
    },
}


def normalize_status(status: str) -> str:
    return NORMALIZED_STATUS.get(status, "infra_error")


def default_latest_output_path(platform: str) -> Path:
    return Path(OUTPUT_DIR) / f"social-auth-{platform}-latest.json"


def build_auth_result(
    *,
    platform: str,
    profile: str,
    state: Dict[str, Any],
    url: str,
    title: str,
    started_at: int,
    screenshot: Optional[str] = None,
    proof_path: Optional[str] = None,
) -> Dict[str, Any]:
    result = {
        "platform": platform,
        "profile": profile,
        "status": state["status"],
        "normalized_status": normalize_status(state["status"]),
        "reason": state["reason"],
        "next_action": state["next_action"],
        "url": sanitize_url(url),
        "title": (title or "")[:160],
        "screenshot": screenshot,
        "screenshot_required": bool(state.get("screenshot_required")),
        "checked_at": int(time.time()),
        "started_at": started_at,
        "proof_bundle": proof_path,
        "secrets_policy": SECRETS_POLICY,
    }
    return result


async def _safe_visible_text(page: Any, max_chars: int = 3000) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=5000)
    except Exception:
        return ""
    return text[:max_chars]


async def check_platform_auth(
    platform: str,
    profile_name: Optional[str] = None,
    headless: bool = True,
    timeout: int = 30,
    proof_screenshot: bool = False,
) -> Dict[str, Any]:
    if platform not in PLATFORMS:
        raise ValueError(f"unknown platform: {platform}")
    started_at = int(time.time())
    cfg = PLATFORMS[platform]
    profile = profile_name or cfg["profile"]
    profile_path = Path(PROFILE_DIR) / profile
    output_dir = Path(OUTPUT_DIR)
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=headless,
            args=build_launch_args(),
            bypass_csp=False,
            java_script_enabled=True,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(stealth_init_script())
            await page.goto(cfg["url"], wait_until="domcontentloaded", timeout=timeout * 1000)
            await page.wait_for_timeout(3000)
            title = await page.title()
            visible_text = await _safe_visible_text(page)
            state = cfg["classifier"](page.url, title, visible_text)
            screenshot = None
            screenshots: Dict[str, str] = {}
            if state.get("screenshot_required") or proof_screenshot:
                label = "blocked" if state.get("screenshot_required") else "after"
                screenshot_path = output_dir / f"auth_check_{platform}_{profile}_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot_path), full_page=False)
                screenshot = str(screenshot_path)
                screenshots[label] = screenshot
            proof = build_metadata(
                workflow="auth_check",
                platform=platform,
                profile=profile,
                normalized_status=normalize_status(state["status"]),
                reason=state["reason"],
                url=page.url,
                title=title,
                action_type="read_only" if state["status"] == AUTHENTICATED else "blocked",
                next_action=state["next_action"],
                started_at=started_at,
                completed_at=int(time.time()),
                screenshots=screenshots,
            )
            proof_path = write_metadata(output_dir, proof)
            return build_auth_result(
                platform=platform,
                profile=profile,
                state=state,
                url=page.url,
                title=title,
                started_at=started_at,
                screenshot=screenshot,
                proof_path=str(proof_path),
            )
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe social platform auth-state check")
    parser.add_argument("platform", choices=sorted(PLATFORMS), help="Platform to check")
    parser.add_argument("--profile", help="Browser profile name. Defaults to platform profile.")
    parser.add_argument("--headed", action="store_true", help="Run headed instead of headless")
    parser.add_argument("--timeout", type=int, default=30, help="Navigation timeout in seconds")
    parser.add_argument("--json-out", help="Optional path for result JSON. Defaults to /app/output/social-auth-<platform>-latest.json")
    parser.add_argument("--monitor-mode", action="store_true", help="Exit 0 for expected auth/user-action states; non-zero only for infra errors")
    parser.add_argument("--proof-screenshot", action="store_true", help="Capture a viewport screenshot even for authenticated states")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        result = await check_platform_auth(
            platform=args.platform,
            profile_name=args.profile,
            headless=not args.headed,
            timeout=args.timeout,
            proof_screenshot=args.proof_screenshot,
        )
    except Exception as exc:
        now = int(time.time())
        profile = args.profile or PLATFORMS.get(args.platform, {}).get("profile")
        state = _state("infra_error", exc.__class__.__name__, "Investigate browser-agent infrastructure failure.", False)
        result = build_auth_result(
            platform=args.platform,
            profile=profile,
            state=state,
            url="",
            title="",
            started_at=now,
        )
        result["error"] = str(exc)[:500]
    print(json.dumps(result, indent=2, sort_keys=True))
    out = Path(args.json_out) if args.json_out else default_latest_output_path(args.platform)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.monitor_mode:
        return 1 if result["normalized_status"] == "infra_error" else 0
    return 0 if result["status"] == AUTHENTICATED else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
