#!/usr/bin/env python3
"""Publish one explicitly approved X reply using the persistent x-profile.

Safety boundaries:
- Uses visible page state only for auth checks.
- Does not read/print/export cookies, localStorage, sessionStorage, tokens, or browser DBs.
- Replies exactly with the supplied text to the supplied target URL after caller approval.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

from publish_x_approved import extract_handle, find_post_url, normalize_text, safe_body_text
from social_auth_check import (
    AUTHENTICATED,
    PROFILE_DIR,
    build_launch_args,
    classify_x_state,
    sanitize_url,
    stealth_init_script,
)

OUTPUT_DIR = "/app/output"


def read_text_arg(args: argparse.Namespace) -> str:
    if args.text_file:
        return Path(args.text_file).read_text(encoding="utf-8").strip()
    if args.text:
        return args.text.strip()
    raise SystemExit("--text or --text-file required")


def valid_x_status_url(url: str) -> bool:
    return bool(re.match(r"^https://(x|twitter)\.com/[A-Za-z0-9_]{1,15}/status/\d+", url))


async def publish_reply(text: str, target_url: str, profile: str, headless: bool, output_dir: Path, item_id: str) -> dict[str, Any]:
    if not valid_x_status_url(target_url):
        return {"ok": False, "item_id": item_id, "status": "blocked", "reason": "invalid_x_target_url"}

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
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(4500)

            title = await page.title()
            visible_text = await safe_body_text(page)
            state = classify_x_state(page.url, title, visible_text)
            if state["status"] != AUTHENTICATED:
                screenshot = output_dir / f"publish_x_reply_{item_id}_blocked_{int(time.time())}.png"
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
            article = page.locator('article[data-testid="tweet"]').first
            if await article.count() == 0:
                return {"ok": False, "item_id": item_id, "status": "blocked", "reason": "target_tweet_not_visible"}

            reply_button = article.locator('[data-testid="reply"]').first
            if await reply_button.count() == 0:
                screenshot = output_dir / f"publish_x_reply_{item_id}_no_reply_button_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {"ok": False, "item_id": item_id, "status": "reply_button_unavailable", "screenshot": str(screenshot)}
            await reply_button.click(timeout=10000)
            await page.wait_for_timeout(1500)

            editor = page.locator('[data-testid="tweetTextarea_0"]').first
            if await editor.count() == 0:
                editor = page.get_by_role("textbox").first
            await editor.click(timeout=10000)
            await editor.fill(text, timeout=10000)
            await page.wait_for_timeout(1000)

            entered = await editor.inner_text(timeout=5000)
            if normalize_text(entered) != normalize_text(text):
                screenshot = output_dir / f"publish_x_reply_{item_id}_text_mismatch_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {
                    "ok": False,
                    "item_id": item_id,
                    "status": "text_mismatch",
                    "expected": normalize_text(text),
                    "actual": normalize_text(entered),
                    "screenshot": str(screenshot),
                }

            buttons = [
                page.locator('div[role="dialog"] [data-testid="tweetButton"]').first,
                page.locator('[data-testid="tweetButton"]').first,
                page.locator('[data-testid="tweetButtonInline"]').first,
            ]
            post_button: Optional[Any] = None
            for button in buttons:
                try:
                    if await button.count() > 0 and await button.is_enabled(timeout=3000):
                        post_button = button
                        break
                except Exception:
                    continue
            if post_button is None:
                screenshot = output_dir / f"publish_x_reply_{item_id}_no_button_{int(time.time())}.png"
                await page.screenshot(path=str(screenshot), full_page=False)
                return {"ok": False, "item_id": item_id, "status": "reply_submit_button_unavailable", "screenshot": str(screenshot)}

            await post_button.click(timeout=10000)
            await page.wait_for_timeout(7000)

            reply_url = await find_post_url(page, text, handle)
            screenshot = output_dir / f"publish_x_reply_{item_id}_after_{int(time.time())}.png"
            await page.screenshot(path=str(screenshot), full_page=False)
            return {
                "ok": bool(reply_url),
                "item_id": item_id,
                "status": "published" if reply_url else "published_url_not_found",
                "post_url": reply_url,
                "target_url": target_url,
                "profile": profile,
                "handle": handle,
                "screenshot": str(screenshot),
                "checked_at": int(time.time()),
            }
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish one approved X reply")
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--target-url", required=True)
    parser.add_argument("--text", help="Exact approved reply text")
    parser.add_argument("--text-file", help="File containing exact approved reply text")
    parser.add_argument("--profile", default="x-profile")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--json-out")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    output_dir = Path(OUTPUT_DIR)
    result = await publish_reply(
        read_text_arg(args),
        args.target_url.strip(),
        args.profile,
        not args.headed,
        output_dir,
        args.item_id,
    )
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
