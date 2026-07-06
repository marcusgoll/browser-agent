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
            "total_processed": 6,
            "action_summary": {"ok": 6, "error": 0, "skipped": 0, "by_action": {"move": 5, "delete": 1}},
            "insights": [
                {"author": "good_ai", "insight": "Agent memory needs remember cite forget layers for persistent agents", "url": "https://x.com/good_ai/status/1"},
                {"author": "trader", "insight": "Autonomous financial research agent builds stock theses", "url": "https://x.com/trader/status/2"},
                {"author": "css", "insight": "CSS custom easing functions improve transitions", "url": "https://x.com/css/status/3"},
                {"author": "neutral", "insight": "Small visual reference for later inspiration", "url": "https://x.com/neutral/status/5"},
                {"author": "ux", "insight": "A generic design moodboard with attractive colors", "url": "https://x.com/ux/status/6"},
                {"author": "spam", "insight": "Unrealistic profit promise", "url": "https://x.com/spam/status/4"},
            ],
            "action_items": [
                {"author": "good_ai", "action": "Update agent memory docs and add tests for context compression", "url": "https://x.com/good_ai/status/1"},
                {"author": "trader", "action": "Compare this finance agent to the Alpaca/Ross paper pipeline", "url": "https://x.com/trader/status/2"},
                {"author": "css", "action": "Bookmark transition pattern for future UI projects", "url": "https://x.com/css/status/3"},
                {"author": "neutral", "action": "Save for later", "url": "https://x.com/neutral/status/5"},
                {"author": "ux", "action": "Maybe useful for product polish", "url": "https://x.com/ux/status/6"},
                {"author": "spam", "action": "Ignore", "url": "https://x.com/spam/status/4"},
            ],
        }

    def sample_analysis(self):
        return [
            {"url": "https://x.com/good_ai/status/1", "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/trader/status/2", "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/css/status/3", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/neutral/status/5", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/ux/status/6", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/spam/status/4", "folder": "delete", "action_result": {"action": "delete", "status": "ok"}},
        ]

    def representative_project_route_fixture(self):
        summary = {
            "total_processed": 3,
            "action_summary": {"ok": 3, "error": 0, "skipped": 0, "by_action": {"move": 3}},
            "insights": [
                {
                    "author": "good_ai",
                    "insight": "Agent memory needs remember cite forget layers for persistent agents",
                    "url": "https://x.com/good_ai/status/1",
                },
                {
                    "author": "css",
                    "insight": "CSS custom easing functions improve transitions",
                    "url": "https://x.com/css/status/3",
                },
                {
                    "author": "ux",
                    "insight": "A generic design moodboard with attractive colors",
                    "url": "https://x.com/ux/status/6",
                },
            ],
            "action_items": [
                {
                    "author": "good_ai",
                    "action": "Update agent memory docs and add tests for context compression",
                    "url": "https://x.com/good_ai/status/1",
                },
                {
                    "author": "css",
                    "action": "Bookmark transition pattern for future UI projects",
                    "url": "https://x.com/css/status/3",
                },
                {
                    "author": "ux",
                    "action": "Maybe useful for product polish",
                    "url": "https://x.com/ux/status/6",
                },
            ],
        }
        analysis = [
            {"url": "https://x.com/good_ai/status/1", "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/css/status/3", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
            {"url": "https://x.com/ux/status/6", "folder": "design", "action_result": {"action": "move", "status": "ok"}},
        ]
        return summary, analysis

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
        self.assertIn("Project routes", memo)
        self.assertIn("primary: hermes_agent", memo)
        self.assertIn("secondary: knowledge_base", memo)
        self.assertIn("secondary route justified by", memo)
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

    def test_representative_project_route_fixture_matches_expected_routes(self):
        summary, analysis = self.representative_project_route_fixture()
        routes = feed.build_project_routes(summary, analysis)

        routes_by_url = {route["url"]: route for route in routes}
        self.assertEqual(
            set(routes_by_url),
            {"https://x.com/good_ai/status/1", "https://x.com/css/status/3"},
        )
        expected_routes_by_url = {
            "https://x.com/good_ai/status/1": {
                "author": "good_ai",
                "insight": "Agent memory needs remember cite forget layers for persistent agents",
                "action": "Update agent memory docs and add tests for context compression",
                "url": "https://x.com/good_ai/status/1",
                "folder": "ai_tools",
                "project": "hermes_agent",
                "route_score": 33,
                "route_why": "primary route justified by agent, agents, context, memory; folder signal ai_tools.",
                "opportunity_score": 0,
                "opportunity_why": "",
                "secondary_routes": [
                    {
                        "project": "knowledge_base",
                        "score": 16,
                        "why": "secondary route justified by context, layers, memory; folder signal ai_tools.",
                    }
                ],
            },
            "https://x.com/css/status/3": {
                "author": "css",
                "insight": "CSS custom easing functions improve transitions",
                "action": "Bookmark transition pattern for future UI projects",
                "url": "https://x.com/css/status/3",
                "folder": "design",
                "project": "product_design",
                "route_score": 36,
                "route_why": "primary route justified by css, easing, transition, transitions, ui; folder signal design.",
                "opportunity_score": 0,
                "opportunity_why": "",
                "secondary_routes": [],
            },
        }
        for url, expected_route in expected_routes_by_url.items():
            with self.subTest(url=url):
                self.assertEqual(routes_by_url[url], expected_route)

    def test_representative_project_route_fixture_omits_folder_only_fallbacks(self):
        summary, analysis = self.representative_project_route_fixture()
        routes = feed.build_project_routes(summary, analysis)

        route_urls = {route["url"] for route in routes}
        route_projects = {route["project"] for route in routes}
        secondary_projects = {
            secondary["project"]
            for route in routes
            for secondary in route.get("secondary_routes", [])
        }
        self.assertNotIn("https://x.com/ux/status/6", route_urls)
        self.assertNotIn("general_research", route_projects | secondary_projects)

    def test_project_routes_include_only_sparse_justified_secondary_routes(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        routes_by_url = {route["url"]: route for route in routed["project_routes"]}
        self.assertEqual(routes_by_url["https://x.com/good_ai/status/1"]["project"], "hermes_agent")
        secondaries = routes_by_url["https://x.com/good_ai/status/1"]["secondary_routes"]
        self.assertEqual([route["project"] for route in secondaries], ["knowledge_base"])
        self.assertTrue(secondaries[0]["why"].startswith("secondary route justified by "))
        self.assertIn("memory", secondaries[0]["why"])
        for route in routed["project_routes"]:
            self.assertLessEqual(len(route.get("secondary_routes", [])), 1)
            for secondary in route.get("secondary_routes", []):
                self.assertIn("project", secondary)
                self.assertIn("score", secondary)
                self.assertRegex(secondary.get("why", ""), r"^secondary route justified by .+\.$")

    def test_project_routes_preserve_existing_opportunity_explanations(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        routes_by_url = {route["url"]: route for route in routed["project_routes"]}
        good_ai = routes_by_url["https://x.com/good_ai/status/1"]
        self.assertEqual(good_ai["opportunity_score"], 52)
        self.assertEqual(
            good_ai["opportunity_why"],
            "Relevant to active Hermes/trading/devops work and has an executable next step.",
        )
        self.assertEqual(
            good_ai["route_why"],
            "primary route justified by agent, agents, context, memory; folder signal ai_tools.",
        )
        for route in routed["project_routes"]:
            for required_field in (
                "author",
                "insight",
                "action",
                "url",
                "folder",
                "project",
                "route_score",
                "route_why",
                "opportunity_score",
                "opportunity_why",
                "secondary_routes",
            ):
                self.assertIn(required_field, route)

    def test_project_routes_skip_ambiguous_folder_only_and_deleted_items(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        route_urls = {route["url"] for route in routed["project_routes"]}
        self.assertNotIn("https://x.com/neutral/status/5", route_urls)
        self.assertNotIn("https://x.com/ux/status/6", route_urls)
        self.assertNotIn("https://x.com/spam/status/4", route_urls)
        self.assertNotIn("general_research", {route["project"] for route in routed["project_routes"]})

    def test_project_routes_do_not_create_tasks_or_multi_hop_routes(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        tasks = feed.build_high_roi_task_queue(routed, limit=10)
        self.assertNotIn("project_routes", {task["source_section"] for task in tasks})
        known_projects = set(feed.PROJECT_ROUTE_RULES)
        for route in routed["project_routes"]:
            self.assertIn(route["project"], known_projects)
            self.assertNotIn("routes", route)
            for secondary in route.get("secondary_routes", []):
                self.assertIn(secondary["project"], known_projects)
                self.assertNotIn("secondary_routes", secondary)

    def test_opportunity_memo_tolerates_missing_or_empty_project_routes(self):
        routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        for project_routes_value in (None, []):
            with self.subTest(project_routes=project_routes_value):
                rollback_shape = dict(routed)
                if project_routes_value is None:
                    rollback_shape.pop("project_routes", None)
                else:
                    rollback_shape["project_routes"] = project_routes_value

                memo = feed.render_opportunity_memo(rollback_shape, "2026-05-23")

                self.assertIn("Immediate executable actions", memo)
                self.assertIn("Research queue", memo)
                self.assertIn("Knowledge-base promotions", memo)
                self.assertIn("Project routes", memo)
                self.assertIn("- None", memo)


if __name__ == "__main__":
    unittest.main()
