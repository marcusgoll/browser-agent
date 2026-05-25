#!/usr/bin/env python3
"""Tests for safe public-web bookmark follow-up reports."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import public_web_followup as followup  # noqa: E402


class PublicWebFollowupTests(unittest.TestCase):
    def sample_router(self):
        return {
            "research_queue": [
                {
                    "url": "https://x.com/akshay/status/1",
                    "author": "akshay",
                    "insight": "Agent harness architecture improves tool use",
                    "action": "Review the article and promote durable harness concepts",
                    "score": 44,
                },
                {
                    "url": "https://x.com/no_links/status/2",
                    "author": "plain",
                    "insight": "No source links here",
                    "action": "Ignore",
                    "score": 3,
                },
            ],
            "knowledge_promotions": [
                {
                    "url": "https://x.com/akshay/status/1",
                    "author": "akshay",
                    "insight": "Agent harness architecture improves tool use",
                    "action": "Review the article and promote durable harness concepts",
                    "score": 51,
                }
            ],
        }

    def sample_analysis(self):
        return [
            {
                "url": "https://x.com/akshay/status/1",
                "author": "akshay",
                "link_enrichment": [
                    {
                        "url": "https://example.com/agent-harness",
                        "status": "ok",
                        "title": "Agent Harness",
                        "text_snippet": "Harnesses coordinate tools, memory, context, and guardrails.",
                    },
                    {
                        "url": "https://x.com/akshay/article/1",
                        "status": "ok",
                        "title": "X article",
                        "text_snippet": "Authenticated article body already captured.",
                    },
                ],
            },
            {"url": "https://x.com/no_links/status/2", "link_enrichment": []},
        ]

    def test_select_followup_sources_prefers_external_public_urls_and_preserves_context(self):
        sources = followup.select_followup_sources(self.sample_router(), self.sample_analysis(), limit=5)
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source["source_url"], "https://example.com/agent-harness")
        self.assertEqual(source["bookmark_url"], "https://x.com/akshay/status/1")
        self.assertEqual(source["author"], "akshay")
        self.assertEqual(source["score"], 51)
        self.assertIn("Harnesses coordinate", source["existing_snippet"])

    def test_firecrawl_fetch_redacts_api_key_and_normalizes_success_response(self):
        calls = []

        def fake_post(url, headers, body, timeout):
            calls.append({"url": url, "headers": headers, "body": body, "timeout": timeout})
            return 200, {"success": True, "data": {"markdown": "# Clean page\nBody", "metadata": {"title": "Clean page"}}}

        result = followup.fetch_with_firecrawl("https://example.com/page", "secret-key", http_post=fake_post)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider"], "firecrawl")
        self.assertEqual(result["title"], "Clean page")
        self.assertNotIn("secret-key", str(result))
        self.assertEqual(calls[0]["headers"]["Authorization"], "Bearer secret-key")

    def test_followup_report_is_candidate_only_and_blocks_low_value_deleted_items(self):
        sources = followup.select_followup_sources(self.sample_router(), self.sample_analysis(), limit=5)
        fetch_results = [{"status": "ok", "provider": "fallback", "title": "Agent Harness", "text": "Tool memory context guardrails."}]
        report = followup.build_promotion_candidate_report(sources, fetch_results, "2026-05-23")
        self.assertIn("Promotion candidates only", report)
        self.assertIn("Agent Harness", report)
        self.assertIn("https://example.com/agent-harness", report)
        self.assertNotIn("auto-promoted: true", report)
        self.assertNotIn("live_trading_allowed: true", report)


if __name__ == "__main__":
    unittest.main()
