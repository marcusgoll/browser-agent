#!/usr/bin/env python3
"""Collect visible X timeline/notification posts for reply drafting.

Read-only: uses visible page state from x-profile, does not inspect cookies,
localStorage, sessionStorage, tokens, or browser databases.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

from social_auth_check import (
    AUTHENTICATED,
    PROFILE_DIR,
    build_launch_args,
    classify_x_state,
    sanitize_url,
    stealth_init_script,
)


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def post_id_from_href(href: str | None) -> str | None:
    if not href:
        return None
    m = re.search(r"/status/(\d+)", href)
    return m.group(1) if m else None


async def collect_from_page(page: Any, url: str, label: str, max_items: int, scrolls: int) -> list[dict[str, Any]]:
    await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(4500)
    items: dict[str, dict[str, Any]] = {}
    for _ in range(scrolls + 1):
        articles = await page.locator('article[data-testid="tweet"]').all()
        for article in articles:
            try:
                text = norm(await article.inner_text(timeout=2500))
                if not text or len(text) < 30:
                    continue
                links = await article.locator('a[href*="/status/"]').all()
                hrefs = []
                for link in links:
                    href = await link.get_attribute("href")
                    if href and "/status/" in href:
                        hrefs.append(href.split("?")[0])
                if not hrefs:
                    continue
                # Shortest status link is usually the canonical post URL.
                href = sorted(set(hrefs), key=len)[0]
                post_id = post_id_from_href(href)
                if not post_id:
                    continue
                full_url = href if href.startswith("http") else f"https://x.com{href}"
                if post_id in items:
                    continue
                handle_match = re.search(r"@([A-Za-z0-9_]{1,15})", text)
                items[post_id] = {
                    "source": label,
                    "post_id": post_id,
                    "url": full_url,
                    "handle": handle_match.group(1) if handle_match else None,
                    "text": text[:900],
                }
                if len(items) >= max_items:
                    return list(items.values())
            except Exception:
                continue
        await page.mouse.wheel(0, 1600)
        await page.wait_for_timeout(1800)
    return list(items.values())


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="x-profile")
    parser.add_argument("--json-out", default="/app/output/x-reply-opportunities-latest.json")
    parser.add_argument("--max-items", type=int, default=18)
    parser.add_argument("--scrolls", type=int, default=4)
    args = parser.parse_args()

    from playwright.async_api import async_playwright

    profile_path = Path(PROFILE_DIR) / args.profile
    out_path = Path(args.json_out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=True,
            args=build_launch_args(),
            bypass_csp=False,
            java_script_enabled=True,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(stealth_init_script())
            await page.goto("https://x.com/home", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(3500)
            title = await page.title()
            body = (await page.locator("body").inner_text(timeout=5000))[:3000]
            state = classify_x_state(page.url, title, body)
            if state["status"] != AUTHENTICATED:
                result = {
                    "ok": False,
                    "status": "blocked",
                    "reason": state["reason"],
                    "url": sanitize_url(page.url),
                    "checked_at": int(time.time()),
                }
                out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                print(json.dumps(result, indent=2, sort_keys=True))
                return 1

            home = await collect_from_page(page, "https://x.com/home", "home", args.max_items, args.scrolls)
            notifications = await collect_from_page(page, "https://x.com/notifications", "notifications", max(6, args.max_items // 2), 2)
            merged: dict[str, dict[str, Any]] = {}
            for item in home + notifications:
                merged.setdefault(item["post_id"], item)
            result = {
                "ok": True,
                "status": "collected",
                "checked_at": int(time.time()),
                "count": len(merged),
                "items": list(merged.values())[: args.max_items],
            }
            out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        finally:
            await context.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
