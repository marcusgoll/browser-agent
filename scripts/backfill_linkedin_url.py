#!/usr/bin/env python3
"""Read-only LinkedIn public URL backfill for approved published posts."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/home/orchestrator/browser-agent/profiles")
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/home/orchestrator/browser-agent/output"))
ACTIVITY_RE = re.compile(r"https://(?:www\.)?linkedin\.com/feed/update/urn:li:activity:[^\s\"'<>]+/?")
SECRETS_POLICY = "visible browser state only; cookies/tokens/storage/passwords/browser databases not inspected"


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def extract_packet_snippet(packet_path: Path, max_chars: int = 180) -> str:
    lines = packet_path.read_text(encoding="utf-8").splitlines()
    body: list[str] = []
    in_exact_content = False
    for raw in lines:
        line = raw.strip()
        if line.lower() == "## exact content":
            in_exact_content = True
            continue
        if in_exact_content and line.startswith("## "):
            break
        if not in_exact_content:
            continue
        if not line:
            if body:
                body.append("")
            continue
        body.append(line)
    if not body:
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#") or re.match(r"^[a-zA-Z_ ]+:\s*", line):
                continue
            body.append(line)
    text = normalize_text(" ".join(body))
    return text[:max_chars].strip()


def sanitize_activity_url(url: str) -> str | None:
    match = ACTIVITY_RE.search(url or "")
    if not match:
        return None
    return match.group(0).rstrip("/") + "/"


def match_terms(snippet: str) -> list[str]:
    text = normalize_text(snippet)
    terms = []
    first_sentence = text.split(". ", 1)[0].strip()
    if len(first_sentence) >= 40:
        terms.append(first_sentence.lower())
    if len(text) >= 80:
        terms.append(text[:80].strip().lower())
    if text:
        terms.append(text.lower())
    return list(dict.fromkeys(terms))


def select_unique_activity_url(snippet: str, candidates: list[dict[str, str]]) -> dict[str, Any]:
    needles = match_terms(snippet)
    matches: list[str] = []
    for candidate in candidates:
        text = normalize_text(candidate.get("text", "")).lower()
        url = sanitize_activity_url(candidate.get("url", ""))
        if needles and any(needle in text for needle in needles) and url:
            matches.append(url)
    unique = sorted(set(matches))
    if len(unique) == 1:
        return {"ok": True, "status": "found", "published_url": unique[0]}
    if not unique:
        return {"ok": False, "status": "blocked", "reason": "no_matching_linkedin_post"}
    return {"ok": False, "status": "blocked", "reason": "multiple_matching_linkedin_posts", "matches": unique}


async def collect_candidates(page: Any) -> list[dict[str, str]]:
    # Read-only DOM scan. No composer actions, no secrets/storage access.
    return await page.evaluate(
        """
        () => {
          const out = [];
          const seen = new Set();
          const anchors = Array.from(document.querySelectorAll('a[href*="/feed/update/urn:li:activity:"]'));
          for (const a of anchors) {
            const href = a.href;
            if (!href || seen.has(href)) continue;
            seen.add(href);
            const card = a.closest('[data-urn], article, div.feed-shared-update-v2, div.update-components-actor') || a.closest('div');
            out.push({url: href, text: (card && card.innerText) || a.innerText || ''});
          }
          return out;
        }
        """
    )


async def screenshot(page: Any, label: str) -> str:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"linkedin_url_backfill_{label}_{int(time.time())}.png"
    await page.screenshot(path=str(path), full_page=False)
    return str(path)


async def run(args: argparse.Namespace) -> dict[str, Any]:
    packet = Path(args.packet)
    snippet = extract_packet_snippet(packet)
    if not snippet:
        return {"ok": False, "status": "blocked", "reason": "empty_packet_snippet", "secrets_policy": SECRETS_POLICY}
    if args.candidates_json:
        candidates = json.loads(Path(args.candidates_json).read_text(encoding="utf-8"))
        result = select_unique_activity_url(snippet, candidates)
        result.update({"item_id": args.item_id, "snippet": snippet, "secrets_policy": SECRETS_POLICY})
        return result
    if args.no_browser:
        return {"ok": False, "status": "blocked", "reason": "browser_lookup_not_requested", "item_id": args.item_id, "snippet": snippet, "secrets_policy": SECRETS_POLICY}

    from playwright.async_api import async_playwright

    profile_path = Path(PROFILE_DIR) / args.profile
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=args.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            for url in ["https://www.linkedin.com/feed/", "https://www.linkedin.com/in/marcusgollahon/recent-activity/all/"]:
                await page.goto(url, wait_until="domcontentloaded", timeout=args.timeout * 1000)
                await page.wait_for_timeout(3000)
                candidates = await collect_candidates(page)
                result = select_unique_activity_url(snippet, candidates)
                if result.get("ok"):
                    result.update({"item_id": args.item_id, "snippet": snippet, "source_url": url, "screenshot": await screenshot(page, "found"), "secrets_policy": SECRETS_POLICY})
                    return result
            result.update({"item_id": args.item_id, "snippet": snippet, "screenshot": await screenshot(page, "blocked"), "secrets_policy": SECRETS_POLICY})
            return result
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only LinkedIn public URL backfill")
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--profile", default="linkedin-profile")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-browser", action="store_true", help="Only parse packet; do not open LinkedIn")
    parser.add_argument("--candidates-json", help="Test/debug candidate JSON; skips browser")
    parser.add_argument("--json-out")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        result = await run(args)
    except Exception as exc:
        result = {"ok": False, "status": "error", "reason": str(exc), "secrets_policy": SECRETS_POLICY}
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result.get("ok") or result.get("status") == "blocked" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
