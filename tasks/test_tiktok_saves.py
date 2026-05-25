#!/usr/bin/env python3
"""Deterministic tests for the read-only TikTok saved/favorites intake."""

import json
import asyncio
import sys
import unittest
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_tiktok_saves as pts  # noqa: E402


class FakeLocator:
    def __init__(self, text=None, exc=None):
        self.text = text or ""
        self.exc = exc

    async def inner_text(self, timeout=3000):
        if self.exc:
            raise self.exc
        return self.text


class FakePage:
    def __init__(self, *, body_by_url=None, cards_by_url=None, evaluate_exc_by_url=None, locator_exc_by_url=None):
        self.url = ""
        self.gotos = []
        self.body_by_url = body_by_url or {}
        self.cards_by_url = cards_by_url or {}
        self.evaluate_exc_by_url = evaluate_exc_by_url or {}
        self.locator_exc_by_url = locator_exc_by_url or {}

    async def goto(self, target, wait_until="domcontentloaded", timeout=45000):
        self.url = target
        self.gotos.append(target)

    def locator(self, selector):
        return FakeLocator(self.body_by_url.get(self.url, ""), self.locator_exc_by_url.get(self.url))

    async def evaluate(self, script, max_items):
        if self.url in self.evaluate_exc_by_url:
            raise self.evaluate_exc_by_url[self.url]
        return self.cards_by_url.get(self.url, [])[:max_items]


class TikTokSavedTransformTests(unittest.TestCase):
    def test_canonicalize_tiktok_url_keeps_video_id(self):
        url = "https://www.tiktok.com/@chef/video/7351234567890123456?lang=en&utm_source=x"
        self.assertEqual(
            pts.canonicalize_tiktok_url(url),
            "https://www.tiktok.com/@chef/video/7351234567890123456",
        )
        self.assertEqual(
            pts.canonicalize_tiktok_url("https://www.tiktok.com/t/ZPRabc123/"),
            "https://www.tiktok.com/t/ZPRabc123/",
        )

    def test_extract_hashtags_lowercases_without_hash(self):
        self.assertEqual(
            pts.extract_hashtags("Easy dinner #FoodTok #MealPrep #foodtok"),
            ["foodtok", "mealprep"],
        )

    def test_classify_record_prefers_recipe_when_food_signals_exist(self):
        record = {
            "caption": "Easy chicken dinner hack: add sauce and bake",
            "hashtags": ["DinnerIdeas"],
            "text_context": "ingredients chicken rice oven bake",
        }
        classification = pts.classify_record(record)
        self.assertEqual(classification["kind"], "recipe")
        self.assertGreaterEqual(classification["recipe_score"], classification["tip_score"])
        self.assertIn("chicken", classification["signals"])

    def test_classify_record_routes_non_food_advice_to_tip(self):
        record = {
            "caption": "Travel packing hack for toddlers",
            "hashtags": ["parenting"],
            "text_context": "organize clean routine setup",
        }
        classification = pts.classify_record(record)
        self.assertEqual(classification["kind"], "tip")
        self.assertEqual(classification["category"], "household_tip")

    def test_build_recipe_card_contains_family_fields(self):
        record = {
            "url": "https://www.tiktok.com/@chef/video/7351234567890123456",
            "video_id": "7351234567890123456",
            "creator_handle": "chef",
            "caption": "Easy chicken rice dinner for kids",
            "hashtags": ["familydinner"],
            "text_context": "chicken rice dinner",
        }
        card = pts.build_recipe_card(record, pts.classify_record(record))
        self.assertEqual(card["id"], "7351234567890123456")
        self.assertEqual(card["source_url"], record["url"])
        for field in (
            "title",
            "category",
            "family_fit",
            "confidence",
            "ingredients",
            "steps",
            "time_estimate_minutes",
            "servings_estimate",
            "grocery_categories",
            "prep_ahead_notes",
            "kid_friendly_notes",
            "why_try_this",
        ):
            self.assertIn(field, card)
        self.assertIn("chicken", card["ingredients"])

    def test_build_tip_card_contains_actionable_fields(self):
        record = {
            "url": "https://www.tiktok.com/@mom/video/7350000000000000000",
            "video_id": "7350000000000000000",
            "creator_handle": "mom",
            "caption": "Organize school lunch boxes faster",
            "text_context": "organize routine tip",
        }
        card = pts.build_tip_card(record, pts.classify_record(record))
        self.assertEqual(card["id"], "7350000000000000000")
        for field in (
            "source_url",
            "title",
            "creator_handle",
            "category",
            "summary",
            "actionable_next_step",
            "family_or_household_relevance",
            "confidence",
        ):
            self.assertIn(field, card)


class TikTokSavedArtifactTests(unittest.TestCase):
    def test_render_weekly_digest_includes_recipe_and_tip_sections(self):
        digest = pts.render_weekly_digest(
            [{"title": "Chicken Rice", "source_url": "https://t", "why_try_this": "easy", "ingredients": ["chicken"]}],
            [{"title": "Lunchbox Tip", "source_url": "https://u", "summary": "prep ahead", "actionable_next_step": "try it"}],
            {"status": "ok", "recipe_count": 1, "tip_count": 1},
        )
        self.assertIn("## Recipes", digest)
        self.assertIn("Chicken Rice", digest)
        self.assertIn("## Tips", digest)
        self.assertIn("Lunchbox Tip", digest)

    def test_render_grocery_list_groups_unknown_items_under_other(self):
        grocery = pts.render_grocery_list([
            {"title": "Dinner", "ingredients": ["mystery spice"], "grocery_categories": {"protein": ["chicken"]}}
        ])
        self.assertIn("## Protein", grocery)
        self.assertIn("- chicken", grocery)
        self.assertIn("## Other", grocery)
        self.assertIn("- mystery spice", grocery)

    def test_build_run_summary_counts_statuses(self):
        summary = pts.build_run_summary(
            [
                {"extraction_status": "ok"},
                {"extraction_status": "partial"},
                {"extraction_status": "error"},
            ],
            [{"id": "r"}],
            [{"id": "t"}],
            status="partial",
        )
        self.assertEqual(summary["status"], "partial")
        self.assertEqual(summary["processed_count"], 3)
        self.assertEqual(summary["recipe_count"], 1)
        self.assertEqual(summary["tip_count"], 1)
        self.assertEqual(summary["partial_count"], 1)
        self.assertEqual(summary["error_count"], 1)


def test_write_artifacts_creates_expected_files(tmp_path):
    raw = [
        {
            "source": "tiktok",
            "url": "https://www.tiktok.com/@chef/video/7351234567890123456",
            "video_id": "7351234567890123456",
            "caption": "Easy chicken dinner",
            "extraction_status": "ok",
        }
    ]
    recipes = [{"id": "7351234567890123456", "title": "Easy chicken dinner", "source_url": raw[0]["url"], "ingredients": ["chicken"], "grocery_categories": {}}]
    tips = [{"id": "tip", "title": "Kitchen tip", "source_url": "https://example.com", "summary": "prep"}]
    summary = pts.write_artifacts(tmp_path / "nested", raw, recipes, tips, status="ok")
    expected = {"raw_saves.jsonl", "recipes.jsonl", "tips.jsonl", "weekly_digest.md", "grocery_list.md", "run_summary.json"}
    assert set(p.name for p in (tmp_path / "nested").iterdir()) == expected
    assert summary["status"] == "ok"
    assert json.loads((tmp_path / "nested" / "run_summary.json").read_text())["recipe_count"] == 1


class TikTokSavedCliTests(unittest.TestCase):
    def test_parse_args_defaults_to_dry_run_and_tiktok_profile(self):
        args = pts.build_parser().parse_args([])
        self.assertTrue(args.dry_run)
        self.assertEqual(args.profile, pts.DEFAULT_PROFILE)
        self.assertEqual(args.output_dir, pts.DEFAULT_OUTPUT_DIR)
        self.assertTrue(args.headless)

    def test_parse_args_exposes_no_execute_flag(self):
        parser = pts.build_parser()
        options = {option for action in parser._actions for option in action.option_strings}
        self.assertIn("--dry-run", options)
        self.assertNotIn("--execute", options)
        with self.assertRaises(SystemExit):
            parser.parse_args(["--execute"])

    def test_normalize_visible_video_card_builds_raw_record(self):
        record = pts.normalize_visible_video_card(
            {
                "href": "https://www.tiktok.com/@chef/video/7351234567890123456?is_copy_url=1",
                "text": "@chef Easy dinner #FoodTok",
                "creator_handle": "@chef",
                "creator_name": "Chef Person",
                "caption": "Easy dinner #FoodTok",
            },
            "2026-05-25T12:00:00Z",
        )
        self.assertEqual(record["source"], "tiktok")
        self.assertEqual(record["video_id"], "7351234567890123456")
        self.assertEqual(record["creator_handle"], "chef")
        self.assertEqual(record["hashtags"], ["foodtok"])
        self.assertEqual(record["extraction_status"], "ok")


def test_requires_user_summary_written_when_auth_missing(tmp_path):
    summary = pts.write_requires_user_summary(tmp_path)
    assert summary["status"] == "requires_user"
    saved = json.loads((tmp_path / "run_summary.json").read_text())
    assert saved["status"] == "requires_user"


def test_auth_required_short_circuits_browser_orchestration(tmp_path):
    page = FakePage(body_by_url={"https://www.tiktok.com/": "For You\nLog in\nGet App"})
    summary = asyncio.run(pts.extract_from_saved_surfaces(page, tmp_path, max_items=10))
    assert summary["status"] == "requires_user"
    assert page.gotos == ["https://www.tiktok.com/"]
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"] == "requires_user"


def test_first_saved_candidate_empty_then_second_candidate_collects_records(tmp_path):
    second_surface = pts.TIKTOK_SAVED_SURFACES[1]
    page = FakePage(
        cards_by_url={
            pts.TIKTOK_SAVED_SURFACES[0]: [],
            second_surface: [
                {
                    "href": "https://www.tiktok.com/@chef/video/7351234567890123456",
                    "text": "Easy chicken dinner #FoodTok",
                    "caption": "Easy chicken dinner #FoodTok",
                }
            ],
        }
    )
    summary = asyncio.run(pts.extract_from_saved_surfaces(page, tmp_path, max_items=10))
    assert summary["status"] == "ok"
    assert summary["raw_count"] == 1
    assert "https://www.tiktok.com/@me" not in page.gotos
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"] == "ok"


def test_all_saved_candidates_empty_writes_extraction_failed(tmp_path):
    page = FakePage(cards_by_url={surface: [] for surface in pts.TIKTOK_SAVED_SURFACES})
    summary = asyncio.run(pts.extract_from_saved_surfaces(page, tmp_path, max_items=10))
    assert summary["status"] == "extraction_failed"
    assert summary["raw_count"] == 0
    assert json.loads((tmp_path / "run_summary.json").read_text())["status"] == "extraction_failed"


def test_evaluate_exception_writes_extraction_failed_not_partial(tmp_path):
    page = FakePage(evaluate_exc_by_url={surface: RuntimeError("selector/evaluate failed") for surface in pts.TIKTOK_SAVED_SURFACES})
    summary = asyncio.run(pts.extract_from_saved_surfaces(page, tmp_path, max_items=10))
    assert summary["status"] == "extraction_failed"
    assert "selector/evaluate failed" in summary["error"]


def test_login_detector_exceptions_are_auth_unknown_errors():
    page = FakePage(locator_exc_by_url={"https://www.tiktok.com/": RuntimeError("body unavailable")})
    page.url = "https://www.tiktok.com/"
    with pytest.raises(pts.AuthDetectionError):
        asyncio.run(pts._looks_login_required(page))


def test_profile_path_traversal_rejected():
    for profile in ("../outside", "/tmp/profile", "nested/profile", "..", ".", ""):
        with pytest.raises(ValueError):
            pts.profile_user_data_dir(profile)
    assert str(pts.profile_user_data_dir("safe-profile_1.2")).endswith("/safe-profile_1.2")


def test_main_returns_nonzero_for_extraction_failed_status(tmp_path, monkeypatch):
    async def fake_process(profile, output_dir, max_items, headless):
        return pts.write_extraction_failed_summary(output_dir, "no saved/favorites records found")

    monkeypatch.setattr(pts, "process_tiktok_saves", fake_process)
    exit_code = asyncio.run(pts.main_async(["--output-dir", str(tmp_path)]))
    assert exit_code == 1


def test_readme_documents_tiktok_read_only_workflow():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text().lower()
    assert "process_tiktok_saves.py" in readme
    assert "tiktok-profile" in readme
    assert "--dry-run" in readme
    assert "no execute mode" in readme or "no mutation" in readme


if __name__ == "__main__":
    unittest.main()
