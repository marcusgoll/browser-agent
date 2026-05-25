#!/usr/bin/env python3
"""Read-only TikTok saved/favorites recipe and tip intake.

This v0 only reads visible TikTok saved/favorites surfaces and writes local
artifacts. It has no execute or mutation mode.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")
DEFAULT_PROFILE = "tiktok-profile"
DEFAULT_OUTPUT_DIR = Path("/app/output/tiktok")
TIKTOK_HOME = "https://www.tiktok.com/"
TIKTOK_SAVED_SURFACES = (
    "https://www.tiktok.com/favorites",
    "https://www.tiktok.com/@me/favorites",
    "https://www.tiktok.com/@me?tab=favorites",
)

RECIPE_WORDS = {
    "recipe",
    "dinner",
    "lunch",
    "breakfast",
    "snack",
    "meal prep",
    "mealprep",
    "chicken",
    "beef",
    "pasta",
    "rice",
    "air fryer",
    "airfryer",
    "crockpot",
    "grill",
    "oven",
    "bake",
    "cook",
    "simmer",
    "sauce",
    "ingredients",
    "mix",
    "add",
    "chop",
    "season",
    "serve",
}
TIP_WORDS = {
    "hack",
    "tip",
    "idea",
    "organize",
    "clean",
    "travel",
    "parenting",
    "productivity",
    "routine",
    "setup",
}
RECIPE_HASHTAGS = {
    "foodtok",
    "dinnerideas",
    "mealprep",
    "recipe",
    "easyrecipe",
    "familydinner",
    "airfryer",
}
TIP_HASHTAGS = {"hack", "tips", "tip", "parenting", "organize", "cleaning", "travel"}

INGREDIENT_CATEGORIES = {
    "protein": {"chicken", "beef", "pork", "turkey", "fish", "salmon", "egg", "eggs", "tofu", "beans"},
    "produce": {"onion", "garlic", "pepper", "tomato", "lettuce", "spinach", "broccoli", "carrot", "potato"},
    "pantry": {"rice", "pasta", "flour", "sugar", "oil", "sauce", "salt", "pepper", "spice", "seasoning"},
    "dairy": {"milk", "cheese", "butter", "yogurt", "cream"},
}

MUTATION_CONTROL_RE = re.compile(
    r"\b(like|favorite|save|follow|comment|share|delete|message|shop|publish|schedule)\b",
    re.IGNORECASE,
)


class AuthDetectionError(RuntimeError):
    """Raised when the page auth state cannot be safely determined."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonicalize_tiktok_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url.strip())
    if not parsed.netloc:
        return url.strip()
    match = re.search(r"/@([^/?#]+)/video/(\d+)", parsed.path)
    if match:
        return f"https://www.tiktok.com/@{match.group(1)}/video/{match.group(2)}"
    short_match = re.search(r"^/t/[^/?#]+/?$", parsed.path)
    if short_match:
        path = parsed.path if parsed.path.endswith("/") else f"{parsed.path}/"
        return f"https://www.tiktok.com{path}"
    return f"{parsed.scheme or 'https'}://{parsed.netloc}{parsed.path}".rstrip("?")


def video_id_from_url(url: str) -> str:
    match = re.search(r"/video/(\d+)", url or "")
    return match.group(1) if match else ""


def stable_record_id(record: dict[str, Any]) -> str:
    if record.get("video_id"):
        return str(record["video_id"])
    url = canonicalize_tiktok_url(str(record.get("url") or ""))
    if url and video_id_from_url(url):
        return video_id_from_url(url)
    seed = "|".join(str(record.get(key) or "") for key in ("url", "creator_handle", "caption", "text_context"))
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def extract_hashtags(text: str) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for tag in re.findall(r"(?<!\w)#([\w\d_]+)", text or "", flags=re.UNICODE):
        normalized = tag.lower()
        if normalized not in seen:
            seen.add(normalized)
            tags.append(normalized)
    return tags


def _combined_text(record: dict[str, Any]) -> str:
    parts = [record.get("caption") or "", record.get("text_context") or "", " ".join(record.get("hashtags") or [])]
    return " ".join(str(part) for part in parts if part).lower()


def _matched_words(text: str, words: set[str]) -> list[str]:
    return sorted(word for word in words if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text))


def classify_record(record: dict[str, Any]) -> dict[str, Any]:
    text = _combined_text(record)
    hashtags = {str(tag).lower().lstrip("#") for tag in (record.get("hashtags") or [])}
    recipe_signals = set(_matched_words(text, RECIPE_WORDS)) | (hashtags & RECIPE_HASHTAGS)
    tip_signals = set(_matched_words(text, TIP_WORDS)) | (hashtags & TIP_HASHTAGS)
    recipe_score = len(recipe_signals)
    tip_score = len(tip_signals)
    has_food_signal = bool(recipe_signals)

    if has_food_signal:
        kind = "recipe"
        category = "family_recipe"
        confidence = "high" if recipe_score >= 3 else "medium"
    elif tip_signals:
        kind = "tip"
        category = "household_tip"
        confidence = "medium" if tip_score >= 2 else "low"
    else:
        kind = "tip"
        category = "review"
        confidence = "low"

    return {
        "kind": kind,
        "category": category,
        "confidence": confidence,
        "recipe_score": recipe_score,
        "tip_score": tip_score,
        "signals": sorted(recipe_signals | tip_signals),
    }


def _title_from_record(record: dict[str, Any], fallback: str) -> str:
    text = (record.get("caption") or record.get("text_context") or fallback).strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"#\w+", "", text).strip()
    return (text[:97] + "...") if len(text) > 100 else text or fallback


def infer_ingredients(record: dict[str, Any]) -> list[str]:
    text = _combined_text(record)
    ingredients: list[str] = []
    all_terms = sorted(set().union(*INGREDIENT_CATEGORIES.values()))
    for term in all_terms:
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text):
            ingredients.append(term)
    return ingredients


def categorize_ingredients(ingredients: list[str]) -> dict[str, list[str]]:
    categorized: dict[str, list[str]] = {}
    for item in ingredients:
        lowered = item.lower()
        category = "other"
        for candidate, words in INGREDIENT_CATEGORIES.items():
            if any(word in lowered for word in words):
                category = candidate
                break
        categorized.setdefault(category, [])
        if item not in categorized[category]:
            categorized[category].append(item)
    return categorized


def build_recipe_card(record: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    ingredients = infer_ingredients(record)
    return {
        "id": stable_record_id(record),
        "source_url": canonicalize_tiktok_url(record.get("url") or ""),
        "title": _title_from_record(record, "Untitled TikTok recipe"),
        "creator_handle": (record.get("creator_handle") or "").lstrip("@"),
        "category": classification.get("category") or "family_recipe",
        "family_fit": "high" if {"dinner", "familydinner", "chicken", "rice"} & set(classification.get("signals") or []) else "medium",
        "confidence": classification.get("confidence") or "low",
        "ingredients": ingredients,
        "steps": [],
        "time_estimate_minutes": None,
        "servings_estimate": None,
        "grocery_categories": categorize_ingredients(ingredients),
        "prep_ahead_notes": "",
        "kid_friendly_notes": "",
        "why_try_this": _title_from_record(record, "Saved as a likely family recipe."),
    }


def build_tip_card(record: dict[str, Any], classification: dict[str, Any]) -> dict[str, Any]:
    title = _title_from_record(record, "Untitled TikTok tip")
    return {
        "id": stable_record_id(record),
        "source_url": canonicalize_tiktok_url(record.get("url") or ""),
        "title": title,
        "creator_handle": (record.get("creator_handle") or "").lstrip("@"),
        "category": classification.get("category") or "review",
        "summary": title,
        "actionable_next_step": "Review the saved TikTok and decide whether to try it this week.",
        "family_or_household_relevance": "Potential family or household usefulness; verify details from the source video.",
        "confidence": classification.get("confidence") or "low",
    }


def render_weekly_digest(recipes: list[dict[str, Any]], tips: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = ["# TikTok Saved/Favorites Weekly Digest", "", f"Status: {summary.get('status', 'unknown')}", f"Recipes: {summary.get('recipe_count', len(recipes))}", f"Tips: {summary.get('tip_count', len(tips))}", "", "## Recipes"]
    if not recipes:
        lines.append("- No recipe candidates collected.")
    for recipe in recipes:
        lines.append(f"- [{recipe.get('title') or 'Untitled recipe'}]({recipe.get('source_url') or '#'})")
        why = recipe.get("why_try_this")
        if why:
            lines.append(f"  - Why try: {why}")
        if recipe.get("ingredients"):
            lines.append(f"  - Ingredients spotted: {', '.join(recipe['ingredients'])}")
    lines.extend(["", "## Tips"])
    if not tips:
        lines.append("- No general tips collected.")
    for tip in tips:
        lines.append(f"- [{tip.get('title') or 'Untitled tip'}]({tip.get('source_url') or '#'})")
        if tip.get("summary"):
            lines.append(f"  - Summary: {tip['summary']}")
        if tip.get("actionable_next_step"):
            lines.append(f"  - Next step: {tip['actionable_next_step']}")
    lines.append("")
    return "\n".join(lines)


def render_grocery_list(recipes: list[dict[str, Any]]) -> str:
    grouped: dict[str, list[str]] = {"protein": [], "produce": [], "pantry": [], "dairy": [], "other": []}
    for recipe in recipes:
        categorized = recipe.get("grocery_categories") or {}
        seen_categorized: set[str] = set()
        for category, items in categorized.items():
            bucket = category if category in grouped else "other"
            for item in items or []:
                if item not in grouped[bucket]:
                    grouped[bucket].append(item)
                seen_categorized.add(item)
        for item in recipe.get("ingredients") or []:
            if item in seen_categorized:
                continue
            bucket = next((cat for cat, words in INGREDIENT_CATEGORIES.items() if any(word in item.lower() for word in words)), "other")
            if item not in grouped[bucket]:
                grouped[bucket].append(item)
    lines = ["# TikTok Grocery List", ""]
    for category in ("protein", "produce", "pantry", "dairy", "other"):
        title = category.replace("_", " ").title()
        lines.append(f"## {title}")
        items = grouped[category]
        if items:
            lines.extend(f"- {item}" for item in sorted(items))
        else:
            lines.append("- ")
        lines.append("")
    return "\n".join(lines)


def build_run_summary(raw_records: list[dict[str, Any]], recipes: list[dict[str, Any]], tips: list[dict[str, Any]], status: str) -> dict[str, Any]:
    statuses = [record.get("extraction_status") or "unknown" for record in raw_records]
    return {
        "status": status,
        "collected_at": utc_now_iso(),
        "processed_count": len(raw_records),
        "raw_count": len(raw_records),
        "recipe_count": len(recipes),
        "tip_count": len(tips),
        "partial_count": statuses.count("partial"),
        "error_count": statuses.count("error"),
        "ok_count": statuses.count("ok"),
    }


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_artifacts(output_dir: Path, raw_records: list[dict[str, Any]], recipes: list[dict[str, Any]], tips: list[dict[str, Any]], status: str = "ok") -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_run_summary(raw_records, recipes, tips, status)
    write_jsonl(output_dir / "raw_saves.jsonl", raw_records)
    write_jsonl(output_dir / "recipes.jsonl", recipes)
    write_jsonl(output_dir / "tips.jsonl", tips)
    (output_dir / "weekly_digest.md").write_text(render_weekly_digest(recipes, tips, summary), encoding="utf-8")
    (output_dir / "grocery_list.md").write_text(render_grocery_list(recipes), encoding="utf-8")
    (output_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_requires_user_summary(output_dir: Path) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_run_summary([], [], [], "requires_user")
    summary["operator_action"] = "Complete attended TikTok login into the tiktok-profile browser profile, then rerun the read-only dry run."
    (output_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def write_extraction_failed_summary(output_dir: Path, error: str) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = build_run_summary([], [], [], "extraction_failed")
    summary["error"] = error
    (output_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def profile_user_data_dir(profile: str) -> Path:
    if not profile or profile in {".", ".."}:
        raise ValueError("--profile must be a simple profile directory name")
    profile_path = Path(profile)
    if profile_path.is_absolute() or len(profile_path.parts) != 1 or profile_path.name != profile:
        raise ValueError("--profile must be a simple profile directory name under BROWSER_PROFILE_DIR")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", profile):
        raise ValueError("--profile may contain only letters, numbers, dot, underscore, and dash")
    return Path(PROFILE_DIR) / profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only TikTok saved/favorites recipe and tip intake")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Read-only mode (default; v0 has no execute mode)")
    parser.add_argument("--profile", default=DEFAULT_PROFILE, help="Persistent browser profile name")
    parser.add_argument("--max", dest="max_items", type=int, default=50, help="Maximum visible saved/favorite items to collect")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Artifact output directory")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser headless (default)")
    parser.add_argument("--headed", dest="headless", action="store_false", help="Open a visible browser for attended debugging")
    return parser


def normalize_visible_video_card(card: dict[str, Any], collected_at: str) -> dict[str, Any]:
    url = canonicalize_tiktok_url(card.get("href") or card.get("url") or "")
    text = str(card.get("text") or "")
    caption = str(card.get("caption") or text)
    hashtags = extract_hashtags(" ".join([caption, text]))
    creator_handle = str(card.get("creator_handle") or "").strip().lstrip("@")
    if not creator_handle:
        match = re.search(r"@([A-Za-z0-9_.]+)", " ".join([url, text]))
        creator_handle = match.group(1) if match else ""
    video_id = video_id_from_url(url)
    status = "ok" if url and video_id else "partial"
    notes = "" if status == "ok" else "visible card lacked a canonical TikTok video id"
    record = {
        "source": "tiktok",
        "url": url,
        "video_id": video_id,
        "creator_handle": creator_handle,
        "creator_name": card.get("creator_name") or "",
        "caption": caption,
        "hashtags": hashtags,
        "saved_at": None,
        "collected_at": collected_at,
        "text_context": re.sub(r"\s+", " ", " ".join([text, caption])).strip(),
        "media_type": "video",
        "extraction_status": status,
        "extraction_notes": notes,
    }
    if not record["video_id"]:
        record["video_id"] = stable_record_id(record)
    return record


async def _looks_login_required(page: Any) -> bool:
    try:
        url = getattr(page, "url", "") or ""
        if "/login" in url.lower():
            return True
        text = (await page.locator("body").inner_text(timeout=3000)).lower()
        login_markers = [
            "log in",
            "log in to tiktok",
            "sign up for tiktok",
            "continue with google",
            "use phone / email",
        ]
        return any(marker in text for marker in login_markers)
    except Exception as exc:
        raise AuthDetectionError(f"Could not determine TikTok auth state: {type(exc).__name__}: {exc}") from exc


async def extract_saved_items(page: Any, max_items: int) -> list[dict[str, Any]]:
    collected_at = utc_now_iso()
    cards = await page.evaluate(
        """
        (maxItems) => {
          const deny = /(like|favorite|save|follow|comment|share|delete|message|shop|publish|schedule)/i;
          const anchors = Array.from(document.querySelectorAll('a[href*="/video/"]'));
          const rows = [];
          const seen = new Set();
          for (const anchor of anchors) {
            const href = anchor.href || anchor.getAttribute('href') || '';
            if (!href || seen.has(href)) continue;
            const container = anchor.closest('div') || anchor;
            const text = (container.innerText || anchor.innerText || '').trim();
            const roleText = `${anchor.getAttribute('aria-label') || ''} ${anchor.getAttribute('data-e2e') || ''}`;
            if (deny.test(roleText)) continue;
            rows.push({href, text, caption: text, creator_handle: '', creator_name: ''});
            seen.add(href);
            if (rows.length >= maxItems) break;
          }
          return rows;
        }
        """,
        max_items,
    )
    return [normalize_visible_video_card(card, collected_at) for card in cards]


def build_cards(raw_records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    recipes: list[dict[str, Any]] = []
    tips: list[dict[str, Any]] = []
    for record in raw_records:
        classification = classify_record(record)
        if classification["kind"] == "recipe":
            recipes.append(build_recipe_card(record, classification))
        else:
            tips.append(build_tip_card(record, classification))
    return recipes, tips


async def extract_from_saved_surfaces(page: Any, output_dir: Path, max_items: int) -> dict[str, Any]:
    """Navigate read-only TikTok saved/favorites surfaces and write artifacts."""
    try:
        await page.goto(TIKTOK_HOME, wait_until="domcontentloaded", timeout=45000)
        if await _looks_login_required(page):
            return write_requires_user_summary(output_dir)
    except AuthDetectionError as exc:
        return write_extraction_failed_summary(output_dir, str(exc))
    except Exception as exc:
        return write_extraction_failed_summary(output_dir, f"Initial TikTok navigation failed: {type(exc).__name__}: {exc}")

    errors: list[str] = []
    for target in TIKTOK_SAVED_SURFACES:
        try:
            await page.goto(target, wait_until="domcontentloaded", timeout=45000)
            if await _looks_login_required(page):
                return write_requires_user_summary(output_dir)
            raw_records = await extract_saved_items(page, max_items)
        except AuthDetectionError as exc:
            return write_extraction_failed_summary(output_dir, str(exc))
        except Exception as exc:
            errors.append(f"{target}: {type(exc).__name__}: {exc}")
            continue
        if raw_records:
            recipes, tips = build_cards(raw_records)
            return write_artifacts(output_dir, raw_records, recipes, tips, status="ok")

    if errors:
        return write_extraction_failed_summary(output_dir, "No saved/favorites records found; candidate errors: " + "; ".join(errors))
    return write_extraction_failed_summary(output_dir, "No records found on TikTok saved/favorites candidate surfaces")


async def process_tiktok_saves(profile: str, output_dir: Path, max_items: int, headless: bool) -> dict[str, Any]:
    user_data_dir = str(profile_user_data_dir(profile))

    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(user_data_dir=user_data_dir, headless=headless, args=["--no-sandbox"])
        page = await context.new_page()
        try:
            return await extract_from_saved_surfaces(page, output_dir, max_items)
        finally:
            await context.close()


async def main_async(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        summary = await process_tiktok_saves(args.profile, args.output_dir, args.max_items, args.headless)
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if summary.get("status") in {"ok", "requires_user"} else 1
    except Exception as exc:
        output_dir = getattr(args, "output_dir", DEFAULT_OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        summary = build_run_summary([], [], [], "extraction_failed")
        summary["error"] = f"{type(exc).__name__}: {exc}"
        (output_dir / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
        return 1


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
