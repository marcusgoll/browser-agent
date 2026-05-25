#!/usr/bin/env python3
"""Publish an approved LinkedIn approval packet using visible browser state only.

Security boundary:
- Does not read/print/export cookies, localStorage, sessionStorage, tokens, saved passwords,
  or browser profile databases.
- Publishes only when the packet is explicitly approved and the visible composer text
  exactly matches the approved content.
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
    build_launch_args,
    classify_linkedin_state,
    sanitize_url,
    stealth_init_script,
)
from account_context import publisher_preflight_result
from proof_bundle import SECRETS_POLICY, build_metadata, write_metadata

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "/app/output")


def extract_packet(packet_path: Path) -> dict[str, str]:
    text = packet_path.read_text()
    status_match = re.search(r"(?im)^Status:\s*(.+?)\s*$", text)
    status = status_match.group(1).strip().lower() if status_match else ""
    if status != "approved":
        raise ValueError(f"packet status is not approved: {status or 'missing'}")
    marker = re.search(
        r"(?s)^## Exact content\s*\n(?P<body>.*?)(?=\n## Links / media / assets\s*$)",
        text,
        flags=re.M,
    )
    if not marker:
        raise ValueError("could not find exact content block")
    body = marker.group("body").strip()
    if not body:
        raise ValueError("exact content block is empty")
    return {"status": status, "content": body}


async def visible_text(page: Any, max_chars: int = 5000) -> str:
    try:
        text = await page.locator("body").inner_text(timeout=5000)
        return text[:max_chars]
    except Exception:
        return ""


async def safe_page_state(page: Any) -> dict[str, Any]:
    title = await page.title()
    text = await visible_text(page)
    state = classify_linkedin_state(page.url, title, text)
    return {
        "url": sanitize_url(page.url),
        "title": title[:160],
        "status": state["status"],
        "reason": state["reason"],
        "next_action": state["next_action"],
    }


async def screenshot(page: Any, name: str) -> str:
    out = Path(OUTPUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"linkedin_publish_{name}_{int(time.time())}.png"
    await page.screenshot(path=str(path), full_page=False)
    return str(path)


async def click_first_visible(page: Any, selectors: list[str], timeout_ms: int = 4000) -> Optional[str]:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout_ms)
            await locator.click(timeout=timeout_ms)
            return selector
        except Exception:
            continue
    return None


async def click_by_text_js(page: Any, texts: list[str]) -> Optional[str]:
    script = """
    (texts) => {
      const wanted = texts.map(t => t.toLowerCase());
      const els = Array.from(document.querySelectorAll('button, [role="button"], a, div'));
      for (const el of els) {
        const txt = (el.innerText || el.getAttribute('aria-label') || '').trim().toLowerCase();
        if (!txt) continue;
        if (wanted.some(w => txt === w || txt.includes(w))) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 0 && rect.height > 0) {
            el.scrollIntoView({block: 'center', inline: 'center'});
            el.click();
            return txt.slice(0, 120);
          }
        }
      }
      return null;
    }
    """
    try:
        return await page.evaluate(script, texts)
    except Exception:
        return None


async def open_composer(page: Any) -> str:
    # Stable selectors first, text/JS fallback second.
    clicked = await click_first_visible(
        page,
        [
            "button[aria-label*='Start a post']",
            "button:has-text('Start a post')",
            "div[role='button']:has-text('Start a post')",
            "span:has-text('Start a post')",
        ],
    )
    if clicked:
        return clicked
    clicked_text = await click_by_text_js(page, ["Start a post", "Share a post"])
    if clicked_text:
        return f"js:{clicked_text}"
    raise RuntimeError("could not open LinkedIn composer from visible page state")


async def fill_composer(page: Any, content: str) -> str:
    candidates = [
        "div[role='textbox'][contenteditable='true']",
        "div[aria-label*='Text editor'][contenteditable='true']",
        ".ql-editor[contenteditable='true']",
        "[contenteditable='true']",
    ]
    for selector in candidates:
        try:
            box = page.locator(selector).first
            await box.wait_for(state="visible", timeout=8000)
            await box.click(timeout=4000)
            # Fill may not work on all contenteditable surfaces; keyboard insert is reliable.
            await page.keyboard.press("Control+A")
            await page.keyboard.type(content, delay=2)
            await page.wait_for_timeout(1500)
            typed = (await box.inner_text(timeout=4000)).strip()
            if normalize(typed) == normalize(content):
                return selector
        except Exception:
            continue
    raise RuntimeError("could not fill composer with exact approved text")


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


async def find_post_button(page: Any) -> Any:
    selectors = [
        "button",
        "button[aria-label='Post']",
        "button[aria-label*='Post']",
    ]
    candidates: list[Any] = []
    for selector in selectors:
        try:
            buttons = page.locator(selector)
            count = await buttons.count()
            for i in range(count):
                btn = buttons.nth(i)
                if not await btn.is_visible(timeout=1000):
                    continue
                disabled = await btn.get_attribute("disabled")
                aria_disabled = await btn.get_attribute("aria-disabled")
                if disabled is not None or aria_disabled in ("true", "True"):
                    continue
                text = ""
                aria = ""
                try:
                    text = (await btn.inner_text(timeout=1000)).strip()
                except Exception:
                    pass
                try:
                    aria = (await btn.get_attribute("aria-label") or "").strip()
                except Exception:
                    pass
                # Critical: exclude the composer audience dropdown, whose text is
                # "Post to Anyone" and also matches :has-text('Post').
                if text == "Post" or aria == "Post":
                    candidates.append(btn)
        except Exception:
            continue
    if candidates:
        return candidates[-1]
    return None


async def click_post_button(page: Any, post_button: Any) -> str:
    """Click the verified LinkedIn Post button.

    LinkedIn can inject an invisible #interop-outlet shadow host that intercepts
    pointer events while the composer is otherwise ready. After exact content
    verification and enabled-button verification, disable pointer events on that
    empty interop layer and retry a real trusted Playwright click on the same
    button. Avoid DOM el.click(): LinkedIn can ignore untrusted synthetic clicks.
    """
    try:
        await post_button.click(timeout=5000)
        return "playwright_click"
    except Exception as exc:
        message = str(exc)
        overlay_count = 0
        try:
            overlay_count = await page.locator("#interop-outlet, [data-testid='interop-shadowdom']").count()
        except Exception:
            overlay_count = 0
        if "intercepts pointer events" not in message and "Timeout" not in message:
            raise
        if overlay_count < 1:
            raise
        await page.evaluate(
            """
            () => {
              for (const el of document.querySelectorAll('#interop-outlet, [data-testid="interop-shadowdom"]')) {
                el.style.pointerEvents = 'none';
              }
            }
            """
        )
        try:
            await post_button.click(timeout=5000)
            return "playwright_click_after_interop_pointer_events_disabled"
        except Exception:
            await post_button.click(timeout=5000, force=True)
            return "force_click_after_interop_pointer_events_disabled"


async def current_composer_text(page: Any) -> str:
    for selector in ["div[role='textbox'][contenteditable='true']", ".ql-editor[contenteditable='true']", "[contenteditable='true']"]:
        try:
            loc = page.locator(selector).first
            if await loc.is_visible(timeout=1000):
                return (await loc.inner_text(timeout=3000)).strip()
        except Exception:
            continue
    return ""


async def click_button_by_mouse(page: Any, button: Any) -> str:
    box = await button.bounding_box()
    if not box:
        raise RuntimeError("post button has no bounding box for mouse retry")
    await page.evaluate(
        """
        () => {
          for (const el of document.querySelectorAll('#interop-outlet, [data-testid="interop-shadowdom"]')) {
            el.style.pointerEvents = 'none';
          }
        }
        """
    )
    await page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    await page.mouse.down()
    await page.wait_for_timeout(150)
    await page.mouse.up()
    return "mouse_bbox_click_after_no_submit"



async def click_button_by_keyboard(page: Any, button: Any) -> str:
    await button.focus()
    await page.wait_for_timeout(150)
    await page.keyboard.press("Enter")
    return "keyboard_enter_after_no_submit"


async def run(args: argparse.Namespace) -> dict[str, Any]:
    packet = extract_packet(Path(args.packet))
    content = packet["content"]
    profile_path = Path(PROFILE_DIR) / args.profile
    profile_path.mkdir(parents=True, exist_ok=True)

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=str(profile_path),
            headless=args.headless,
            args=build_launch_args(),
            bypass_csp=False,
            java_script_enabled=True,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(stealth_init_script())
            await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=args.timeout * 1000)
            await page.wait_for_timeout(4000)
            state = await safe_page_state(page)
            result: dict[str, Any] = {
                "status": "blocked",
                "packet": str(args.packet),
                "profile": args.profile,
                "page_state": state,
                "published_url": None,
                "screenshot": None,
            }
            if state["status"] != AUTHENTICATED:
                result["reason"] = f"linkedin not authenticated or challenged: {state['reason']}"
                result["screenshot"] = await screenshot(page, "blocked_auth")
                proof = build_metadata(
                    workflow="publish_linkedin_approved",
                    platform="linkedin",
                    profile=args.profile,
                    normalized_status="blocked",
                    reason=state["reason"],
                    url=state["url"],
                    title=state["title"],
                    action_type="blocked",
                    next_action=state["next_action"],
                    screenshots={"blocked": result["screenshot"]},
                )
                result["proof_bundle"] = str(write_metadata(Path(OUTPUT_DIR), proof))
                result["secrets_policy"] = SECRETS_POLICY
                return result

            body_text = await visible_text(page)
            preflight = publisher_preflight_result(
                platform="linkedin",
                url=page.url,
                authenticated=True,
                visible_text=body_text,
                account_name=None,
                expected_account_name=args.expected_account_name,
                allowed_domains=["www.linkedin.com", "linkedin.com"],
                action_type="approved_write",
            )
            result["preflight"] = preflight
            if not preflight["ok"]:
                result["reason"] = preflight["reason"]
                result["screenshot"] = await screenshot(page, "preflight_blocked")
                proof = build_metadata(
                    workflow="publish_linkedin_approved",
                    platform="linkedin",
                    profile=args.profile,
                    normalized_status="blocked",
                    reason=preflight["reason"],
                    url=page.url,
                    title=await page.title(),
                    action_type="blocked",
                    next_action="Review expected LinkedIn account context before publishing.",
                    screenshots={"blocked": result["screenshot"]},
                    account_context=preflight.get("context") or {},
                )
                result["proof_bundle"] = str(write_metadata(Path(OUTPUT_DIR), proof))
                result["secrets_policy"] = SECRETS_POLICY
                return result

            result["open_composer_method"] = await open_composer(page)
            await page.wait_for_timeout(3000)
            result["fill_method"] = await fill_composer(page, content)
            await page.wait_for_timeout(3000)

            composed = await current_composer_text(page)
            if normalize(composed) != normalize(content):
                result["reason"] = "visible composer text does not exactly match approved packet"
                result["screenshot"] = await screenshot(page, "text_mismatch")
                return result

            result["pre_publish_screenshot"] = await screenshot(page, "ready")
            if args.dry_run:
                result["status"] = "ready_dry_run"
                result["reason"] = "composer is filled with exact approved text; dry-run prevented live publish"
                return result

            post_button = await find_post_button(page)
            if post_button is None:
                result["reason"] = "post button not visible/enabled after exact text verification"
                result["screenshot"] = await screenshot(page, "no_post_button")
                return result
            try:
                result["post_click_method"] = await click_post_button(page, post_button)
            except Exception as exc:
                result["reason"] = f"post button click blocked after exact text verification: {exc}"
                result["screenshot"] = await screenshot(page, "post_click_blocked")
                return result
            await page.wait_for_timeout(8000)

            remaining_composed = await current_composer_text(page)
            remaining_button = await find_post_button(page)
            if normalize(remaining_composed) == normalize(content) and remaining_button is not None:
                try:
                    result["post_click_retry_method"] = await click_button_by_mouse(page, remaining_button)
                    await page.wait_for_timeout(8000)
                    remaining_composed = await current_composer_text(page)
                    remaining_button = await find_post_button(page)
                except Exception as exc:
                    result["post_click_retry_error"] = str(exc)
            if normalize(remaining_composed) == normalize(content) and remaining_button is not None:
                try:
                    result["post_click_keyboard_retry_method"] = await click_button_by_keyboard(page, remaining_button)
                    await page.wait_for_timeout(8000)
                    remaining_composed = await current_composer_text(page)
                    remaining_button = await find_post_button(page)
                except Exception as exc:
                    result["post_click_keyboard_retry_error"] = str(exc)
            if normalize(remaining_composed) == normalize(content) and remaining_button is not None:
                result["status"] = "blocked"
                result["reason"] = "post click returned but composer remained open with exact approved text; treating as not published"
                result["screenshot"] = await screenshot(page, "post_click_no_submit")
                return result

            # A successful post usually closes the modal and may show a view/update URL. We do not
            # scrape hidden state; capture sanitized visible URL and screenshot for operator audit.
            result["status"] = "published_or_submitted"
            result["reason"] = "clicked Post after exact composer verification; public URL may require feed lookup"
            result["published_url"] = sanitize_url(page.url)
            result["screenshot"] = await screenshot(page, "after_post")
            proof = build_metadata(
                workflow="publish_linkedin_approved",
                platform="linkedin",
                profile=args.profile,
                normalized_status="published_or_submitted",
                reason=result["reason"],
                url=page.url,
                title=await page.title(),
                action_type="approved_write",
                next_action="Record public URL if available from LinkedIn feed.",
                screenshots={"after": result["screenshot"]},
                account_context=(result.get("preflight") or {}).get("context") or {},
            )
            result["proof_bundle"] = str(write_metadata(Path(OUTPUT_DIR), proof))
            result["secrets_policy"] = SECRETS_POLICY
            return result
        finally:
            await context.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish an approved LinkedIn packet safely")
    parser.add_argument("--packet", required=True, help="Path to approved packet markdown")
    parser.add_argument("--profile", default="linkedin-profile", help="Browser profile name")
    parser.add_argument("--expected-account-name", help="Expected visible LinkedIn account name before publishing")
    parser.add_argument("--timeout", type=int, default=45, help="Navigation timeout seconds")
    parser.add_argument("--headless", action="store_true", help="Run headless instead of headed DISPLAY browser")
    parser.add_argument("--dry-run", action="store_true", help="Stop before clicking Post")
    parser.add_argument("--json-out", help="Write result JSON")
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    try:
        result = await run(args)
    except Exception as exc:
        result = {"status": "error", "reason": str(exc), "published_url": None}
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.json_out:
        path = Path(args.json_out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0 if result.get("status") in {"published_or_submitted", "ready_dry_run"} else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
