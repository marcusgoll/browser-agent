#!/usr/bin/env python3
"""Regression tests for deterministic X bookmark dedupe and analysis cache reuse."""

import asyncio
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_bookmarks as pb  # noqa: E402


class BookmarkDedupeCacheTests(unittest.TestCase):
    def sample_bookmark(self, **overrides):
        bookmark = {
            "id": "123",
            "author": "TestPilot",
            "text": "A durable testing insight about deterministic cache keys.",
            "url": "https://x.com/TestPilot/status/123",
            "timestamp": "Wed Jun 03 00:00:00 +0000 2026",
            "external_urls": [],
            "media": [],
            "card": None,
            "quoted_tweet": None,
            "deleted": False,
        }
        bookmark.update(overrides)
        return bookmark

    def test_dedupe_key_normalizes_x_status_urls_before_comparing(self):
        canonical = self.sample_bookmark(url="https://x.com/TestPilot/status/123")
        noisy_duplicate = self.sample_bookmark(url="https://X.COM/TestPilot/status/123/?utm_source=feed#comments")

        self.assertEqual(pb.bookmark_dedupe_key(canonical), pb.bookmark_dedupe_key(noisy_duplicate))
        self.assertEqual(pb.normalize_bookmark_url(noisy_duplicate["url"]), "https://x.com/i/web/status/123")

    def test_dedupe_key_treats_twitter_and_x_status_shapes_as_same_bookmark(self):
        canonical = self.sample_bookmark(url="https://x.com/i/web/status/123")
        twitter_shape = self.sample_bookmark(url="https://twitter.com/testpilot/status/123?s=20")

        self.assertEqual(pb.bookmark_dedupe_key(canonical), pb.bookmark_dedupe_key(twitter_shape))
        self.assertEqual(pb.normalize_bookmark_url(twitter_shape["url"]), "https://x.com/i/web/status/123")

    def test_dedupe_key_uses_content_hash_when_url_is_missing(self):
        first = self.sample_bookmark(id="", url="", text="Same deleted bookmark text", author="same_author")
        second = self.sample_bookmark(id="", url="", text="Same deleted bookmark text", author="same_author")
        distinct = self.sample_bookmark(id="", url="", text="Different deleted bookmark text", author="same_author")

        self.assertTrue(pb.bookmark_dedupe_key(first).startswith("content:"))
        self.assertEqual(pb.bookmark_dedupe_key(first), pb.bookmark_dedupe_key(second))
        self.assertNotEqual(pb.bookmark_dedupe_key(first), pb.bookmark_dedupe_key(distinct))

    def test_distinct_status_urls_do_not_false_positive_dedupe(self):
        first = self.sample_bookmark(id="123", url="https://x.com/TestPilot/status/123", text="same text")
        second = self.sample_bookmark(id="124", url="https://x.com/TestPilot/status/124", text="same text")

        self.assertNotEqual(pb.bookmark_dedupe_key(first), pb.bookmark_dedupe_key(second))

    def test_duplicate_inputs_are_suppressed_before_analysis(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["url"])
            return {"folder": "coding", "reason": "tested", "insights": bookmark["text"], "actionable": None}

        duplicate = self.sample_bookmark(id="123", url="https://X.COM/TestPilot/status/123/?utm_campaign=again")
        distinct = self.sample_bookmark(id="124", url="https://x.com/TestPilot/status/124", text="A distinct cache-key insight.")

        run = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark(), duplicate, distinct], fake_analyze, cache={}))

        self.assertEqual(len(run["results"]), 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(run["cache_stats"]["duplicates_suppressed"], 1)
        self.assertEqual(run["cache_stats"]["misses"], 2)
        self.assertEqual(run["cache_stats"]["hits"], 0)
        self.assertEqual(run["duplicates"][0]["duplicate_index"], 1)

    def test_repeated_run_reuses_cached_analysis_and_reports_hit(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["url"])
            return {"folder": "coding", "reason": "fresh analysis", "insights": bookmark["text"], "actionable": "write regression test"}

        cache = {}
        first = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))
        second = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))

        self.assertEqual(len(calls), 1)
        self.assertEqual(first["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(second["cache_stats"], {"hits": 1, "misses": 0, "duplicates_suppressed": 0})
        self.assertEqual(second["results"][0]["cache_status"], "hit")
        self.assertEqual(second["results"][0]["folder"], "coding")
        self.assertEqual(second["results"][0]["actionable"], "write regression test")


if __name__ == "__main__":
    unittest.main()
