#!/usr/bin/env python3
"""Publish one explicitly approved X post using the persistent x-profile.

Safety boundaries:
- Uses visible page state only for auth checks.
- Does not read/print/export cookies, localStorage, sessionStorage, tokens, or browser DBs.
- Publishes exactly the supplied text after caller approval.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from social_auth_check import (
    AUTHENTICATED,
    PROFILE_DIR,
    build_launch_args,
    classify_x_state,
    normalize_status,
    sanitize_url,
    stealth_init_script,
)
from account_context import publisher_preflight_result
from proof_bundle import SECRETS_POLICY, build_metadata, write_metadata

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


async def safe_body_text(page: Any, max_chars: int = 3000) -> str:
    try:
        return (await page.locator("body").inner_text(timeout=5000))[:max_chars]
    except Exception:
        return ""


async def extract_handle(page: Any) -> Optional[str]:
    selectors = [
        '[data-testid="SideNav_AccountSwitcher_Button"]',
        '[data-testid="AppTabBar_Profile_Link"]',
        'a[aria-label*="Profile"]',
    ]
    for selector in selectors:
        try:
            loc = page.locator(selector).first
            if await loc.count() == 0:
                continue
            text = await loc.inner_text(timeout=3000)
            match = re.search(r"@([A-Za-z0-9_]{1,15})", text or "")
            if match:
                return match.group(1)
            href = await loc.get_attribute("href", timeout=3000)
            if href:
                parts = [p for p in href.split("?")[0].split("/") if p]
                if parts and re.match(r"^[A-Za-z0-9_]{1,15}$", parts[-1]) and parts[-1] not in {"home", "explore", "notifications", "messages", "i"}:
                    return parts[-1]
        except Exception:
            continue
    return None


async def find_post_url(page: Any, approved_text: str, handle: Optional[str]) -> Optional[str]:
    needle = normalize_text(approved_text)[:120]
    urls = []
    candidate_pages = ["https://x.com/home"]
    if handle:
        # Replies may not appear on the default profile timeline; check the
        # replies tab before home so reply publishers can recover the public URL
        # after X redirects back to the home timeline post-submit.
        candidate_pages.insert(0, f"https://x.com/{handle}/with_replies")
        candidate_pages.insert(0, f"https://x.com/{handle}")

    for url in candidate_pages:
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(5000)
            for _ in range(4):
                articles = await page.locator('article[data-testid="tweet"]').all()
                for article in articles:
                    try:
                        text = await article.inner_text(timeout=3000)
                        if needle and needle in normalize_text(text):
                            links = await article.locator('a[href*="/status/"]').all()
                            for link in links:
                                href = await link.get_attribute("href")
                                if href and "/status/" in href:
                                    full = href if href.startswith("http") else f"https://x.com{href}"
                                    urls.append(full.split("?")[0])
                    except Exception:
                        continue
                if urls:
                    return sorted(set(urls), key=len)[0]
                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(1500)
        except Exception:
            continue
    return None


async def publish_x(
    text: str,
    profile: str,
    headless: bool,
    output_dir: Path,
    item_id: str,
    expected_handle: Optional[str] = None,
) -> dict[str, Any]:
    from playwright.async_api import async_playwright

    profile_path = Path(PROFILE_DIR) / profile
    profile_path.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

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
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4000)

            title = await page.title()
            visible_text = await safe_body_text(page)
            state = classify_x_state(page.url, title, visible_text)
            if state["status"] != AUTHENTICATED:
                screenshot = output_dir / f"publish_x_{item_id}_blocked_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {
                    "ok": False,
                    "item_id": item_id,
                    "status": "blocked",
                    "reason": state["reason"],
                    "url": sanitize_url(page.url),
                    "screenshot": str(screenshot),
                }

            handle = await extract_handle(page)
            preflight = publisher_preflight_result(
                platform="x",
                url=page.url,
                authenticated=True,
                visible_text=visible_text,
                handle=handle,
                expected_handle=expected_handle,
                allowed_domains=["x.com", "twitter.com"],
                action_type="approved_write",
            )
            if not preflight["ok"]:
                screenshot = output_dir / f"publish_x_{item_id}_preflight_blocked_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                proof = build_metadata(
                    workflow="publish_x_approved",
                    platform="x",
                    profile=profile,
                    normalized_status="blocked",
                    reason=preflight["reason"],
                    url=page.url,
                    title=title,
                    action_type="blocked",
                    next_action="Review expected account context before publishing.",
                    screenshots={"blocked": str(screenshot)},
                    account_context=preflight.get("context") or {},
                    item_id=item_id,
                )
                proof_path = write_metadata(output_dir, proof)
                return {
                    "ok": False,
                    "item_id": item_id,
                    "status": "blocked",
                    "reason": preflight["reason"],
                    "url": sanitize_url(page.url),
                    "screenshot": str(screenshot),
                    "preflight": preflight,
                    "proof_bundle": str(proof_path),
                    "secrets_policy": SECRETS_POLICY,
                }

            compose = page.locator('[data-testid="SideNav_NewTweet_Button"]').first
            if await compose.count() > 0:
                await compose.click(timeout=10000)
                await page.wait_for_timeout(1500)

            editor = page.locator('[data-testid="tweetTextarea_0"]').first
            if await editor.count() == 0:
                # Inline composer fallback on home.
                editor = page.get_by_role("textbox").first
            await editor.click(timeout=10000)
            await editor.fill(text, timeout=10000)
            await page.wait_for_timeout(1000)

            entered = await editor.inner_text(timeout=5000)
            if normalize_text(entered) != normalize_text(text):
                screenshot = output_dir / f"publish_x_{item_id}_text_mismatch_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {
                    "ok": False,
                    "item_id": item_id,
                    "status": "text_mismatch",
                    "expected": normalize_text(text),
                    "actual": normalize_text(entered),
                    "screenshot": str(screenshot),
                }

            # Prefer modal post button, fallback to inline post button.
            buttons = [
                page.locator('div[role="dialog"] [data-testid="tweetButton"]').first,
                page.locator('[data-testid="tweetButton"]').first,
                page.locator('[data-testid="tweetButtonInline"]').first,
            ]
            post_button = None
            for button in buttons:
                try:
                    if await button.count() > 0 and await button.is_enabled(timeout=3000):
                        post_button = button
                        break
                except Exception:
                    continue
            if post_button is None:
                screenshot = output_dir / f"publish_x_{item_id}_no_button_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {
                    "ok": False,
                    "item_id": item_id,
                    "status": "post_button_unavailable",
                    "screenshot": str(screenshot),
                }

            await post_button.click(timeout=10000)
            await page.wait_for_timeout(7000)

            post_url = await find_post_url(page, text, handle)
            screenshot = output_dir / f"publish_x_{item_id}_after_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot), full_page=False)
            proof = build_metadata(
                workflow="publish_x_approved",
                platform="x",
                profile=profile,
                normalized_status="published" if post_url else "ambiguous",
                reason="published" if post_url else "published_url_not_found",
                url=post_url or page.url,
                title=await page.title(),
                action_type="approved_write",
                next_action="Record published URL." if post_url else "Manually verify whether the post published.",
                screenshots={"after": str(screenshot)},
                account_context=preflight.get("context") or {},
                item_id=item_id,
            )
            proof_path = write_metadata(output_dir, proof)
            return {
                "ok": bool(post_url),
                "item_id": item_id,
                "status": "published" if post_url else "published_url_not_found",
                "post_url": post_url,
                "profile": profile,
                "handle": handle,
                "screenshot": str(screenshot),
                "preflight": preflight,
                "proof_bundle": str(proof_path),
                "secrets_policy": SECRETS_POLICY,
                "checked_at": int(time.time()),
            }
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one approved X item")
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--text", help="Exact approved post text")
    parser.add_argument("--text-file", help="File containing exact approved post text")
    parser.add_argument("--profile", default="x-profile")
    parser.add_argument("--expected-handle", help="Expected visible X handle before publishing, without or with @")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json-out")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    if args.text_file:
        text = Path(args.text_file).read_text().strip()
    elif args.text:
        text = args.text.strip()
    else:
        raise SystemExit("--text or --text-file required")

    result = await publish_x(
        text=text,
        profile=args.profile,
        headless=not args.headed,
        output_dir=Path(OUTPUT_DIR),
        item_id=args.item_id,
        expected_handle=args.expected_handle,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
