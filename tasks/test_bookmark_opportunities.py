#!/usr/bin/env python3
"""Tests for high-ROI X bookmark opportunity routing."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import feed_to_agents as feed  # noqa: E402


class OpportunityRouterTests(unittest.TestCase):
    def sample_summary(self):
        return {
            "total_processed": 4,
            "action_summary": {"ok": 4, "error": 0, "skipped": 0, "by_action": {"move": 3, "delete": 1}},
            "insights": [
                {"author": "good_ai", "insight": "Agent memory needs remember cite forget layers for persistent agents", "url": "https://x.com/good_ai/status/1"},
                {"author": "trader", "insight": "Autonomous financial research agent builds stock theses", "url": "https://x.com/trader/status/2"},
                {"author": "css", "insight": "CSS custom easing functions improve transitions", "url": "https://x.com/css/status/3"},
                {"author": "spam", "insight": "Unrealistic profit promise", "url": "https://x.com/spam/status/4"},
            ],
            "action_items": [
                {"author": "good_ai", "action": "Update agent memory docs and add tests for context compression", "url": "https://x.com/good_ai/status/1"},
                {"author": "trader", "action": "Compare this finance agent to the Alpaca/Ross paper pipeline", "url": "https://x.com/trader/status/2"},
                {"author": "css", "action": "Bookmark transition pattern for future UI projects", "url": "https://x.com/css/status/3"},
                {"author": "spam", "action": "Ignore", "url": "https://x.com/spam/status/4"},
            ],
        }

    def sample_analysis(self):
        return [
            {"url": "https://x.com/good_ai/status/1", "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/trader/status/2", "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/css/status/3", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/spam/status/4", "folder": "delete", "action_result": {"action": "delete", "status": "ok"}},
        ]

    def test_router_filters_deleted_items_from_opportunities(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        all_urls = {item["url"] for section in ("immediate_actions", "research_queue", "knowledge_promotions") for item in routed[section]}
        self.assertNotIn("https://x.com/spam/status/4", all_urls)
        self.assertEqual(routed["skipped"]["deleted_or_low_value"], 1)

    def test_router_prioritizes_active_project_relevance(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        top_urls = [item["url"] for item in routed["immediate_actions"][:2]]
        self.assertIn("https://x.com/good_ai/status/1", top_urls)
        self.assertIn("https://x.com/trader/status/2", top_urls)

    def test_router_emits_three_ranked_sections_with_scores_and_reasons(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        for section in ("immediate_actions", "research_queue", "knowledge_promotions"):
            self.assertIn(section, routed)
            self.assertTrue(routed[section], section)
            scores = [item["score"] for item in routed[section]]
            self.assertEqual(scores, sorted(scores, reverse=True))
            self.assertTrue(all(item.get("why") for item in routed[section]))

    def test_markdown_memo_contains_top_sections_and_action_summary(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        memo = feed.render_opportunity_memo(routed, "2026-05-23")
        self.assertIn("Immediate executable actions", memo)
        self.assertIn("Research queue", memo)
        self.assertIn("Knowledge-base promotions", memo)
        self.assertIn("Action summary", memo)
        self.assertIn("deleted_or_low_value: 1", memo)

    def test_high_roi_task_queue_turns_router_sections_into_safe_concrete_tasks(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        tasks = feed.build_high_roi_task_queue(routed, limit=4)
        self.assertTrue(tasks)
        self.assertEqual(tasks[0]["priority"], 1)
        self.assertEqual(tasks[0]["status"], "proposed")
        self.assertIn(tasks[0]["task_type"], {"implementation", "research", "knowledge_promotion"})
        self.assertTrue(tasks[0]["title"])
        self.assertTrue(tasks[0]["deliverable"])
        self.assertRegex(tasks[0]["id"], r"^x-bookmark-[a-f0-9]{12}$")
        self.assertEqual(tasks[0]["safety"], {"auto_execute": False, "requires_human_review": True})
        self.assertEqual([task["priority"] for task in tasks], list(range(1, len(tasks) + 1)))
        self.assertNotIn("https://x.com/spam/status/4", {task["source_url"] for task in tasks})

    def test_high_roi_task_markdown_is_operator_action_list(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())
        tasks = feed.build_high_roi_task_queue(routed, limit=3)
        memo = feed.render_high_roi_task_list(tasks, "2026-05-23")
        self.assertIn("High-ROI X Bookmark Tasks - 2026-05-23", memo)
        self.assertIn("auto_execute: false", memo)
        self.assertIn("requires_human_review: true", memo)
        self.assertIn("deliverable:", memo)
        self.assertIn("source:", memo)


if __name__ == "__main__":
    unittest.main()
