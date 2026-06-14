#!/usr/bin/env python3
"""Tests for the bookmark opportunity scorer rollback switch."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import feed_to_agents as feed  # noqa: E402


class BookmarkRollbackSwitchTests(unittest.TestCase):
    def read_repo_file_or_skip(self, relative_path):
        path = REPO_ROOT / relative_path
        if not path.exists():
            self.skipTest(f"{relative_path} is not mounted in this test environment")
        return path.read_text()

    def sample_summary(self):
        return {
            "total_processed": 1,
            "action_summary": {"ok": 1},
            "insights": [
                {
                    "author": "operator",
                    "insight": "Agent memory architecture pattern",
                    "url": "https://x.com/operator/status/1",
                }
            ],
            "action_items": [
                {
                    "author": "operator",
                    "action": "Add tests for agent memory routing",
                    "url": "https://x.com/operator/status/1",
                }
            ],
        }

    def sample_analysis(self):
        return [
            {
                "url": "https://x.com/operator/status/1",
                "folder": "ai_tools",
                "action_result": {"action": "move", "status": "ok"},
            }
        ]

    def test_default_scorer_remains_deterministic_with_explainable_item_shape(self):
        with patch.dict(feed.os.environ, {}, clear=False):
            feed.os.environ.pop(feed.TRIAGE_SCORER_MODE_ENV, None)
            routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        self.assertEqual(routed["triage_scorer"], "deterministic")
        item = routed["immediate_actions"][0]
        self.assertEqual(item["url"], "https://x.com/operator/status/1")
        self.assertTrue(item["passes_threshold"])
        self.assertEqual(item["threshold"], feed.TRIAGE_SECTION_THRESHOLDS["immediate_actions"])
        self.assertIn("active_project:agent", item["reason_codes"])
        self.assertIn("threshold:immediate_actions:met", item["reason_codes"])
        self.assertIn("Reason codes:", item["why"])

    def test_legacy_scorer_uses_pre_reason_code_item_shape_and_weights(self):
        with patch.dict(feed.os.environ, {feed.TRIAGE_SCORER_MODE_ENV: "legacy"}):
            routed = feed.build_opportunity_router(self.sample_summary(), self.sample_analysis())

        self.assertEqual(routed["triage_scorer"], "legacy")
        item = routed["immediate_actions"][0]
        self.assertEqual(item["url"], "https://x.com/operator/status/1")
        self.assertEqual(item["score"], 28)
        self.assertEqual(
            item["why"],
            "Relevant to active Hermes/trading/devops work and has an executable next step.",
        )
        self.assertNotIn("threshold", item)
        self.assertNotIn("passes_threshold", item)
        self.assertNotIn("reason_codes", item)

    def test_compose_passes_rollback_switch_into_browser_agent_service(self):
        compose = self.read_repo_file_or_skip("docker-compose.yml")

        self.assertIn(
            "- BOOKMARK_TRIAGE_SCORER=${BOOKMARK_TRIAGE_SCORER:-deterministic}",
            compose,
        )

    def test_scheduled_wrapper_passes_rollback_switch_to_compose_run(self):
        wrapper = self.read_repo_file_or_skip("ops/hermes-scripts/x-bookmark-agent-feed.sh")

        self.assertIn("-e", wrapper)
        self.assertIn(
            "BOOKMARK_TRIAGE_SCORER=${BOOKMARK_TRIAGE_SCORER:-deterministic}",
            wrapper,
        )


if __name__ == "__main__":
    unittest.main()
