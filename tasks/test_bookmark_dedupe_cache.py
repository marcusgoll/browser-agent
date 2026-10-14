#!/usr/bin/env python3
"""Regression tests for deterministic X bookmark dedupe and analysis cache reuse."""

import asyncio
import os
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

    def test_normalized_duplicate_inputs_share_same_dedupe_key_and_content_hash(self):
        canonical = self.sample_bookmark(url="https://x.com/TestPilot/status/123")
        normalized_duplicate = self.sample_bookmark(url="https://twitter.com/testpilot/status/123?utm_source=feed&s=20#thread")

        self.assertEqual(pb.normalize_bookmark_url(canonical["url"]), "https://x.com/i/web/status/123")
        self.assertEqual(pb.normalize_bookmark_url(normalized_duplicate["url"]), "https://x.com/i/web/status/123")
        self.assertEqual(pb.bookmark_dedupe_key(canonical), pb.bookmark_dedupe_key(normalized_duplicate))
        self.assertEqual(pb.bookmark_content_hash(canonical), pb.bookmark_content_hash(normalized_duplicate))

    def test_dedupe_key_uses_content_hash_when_url_is_missing(self):
        first = self.sample_bookmark(id="", url="", text="Same deleted bookmark text", author="same_author")
        second = self.sample_bookmark(id="", url="", text="Same deleted bookmark text", author="same_author")
        distinct = self.sample_bookmark(id="", url="", text="Different deleted bookmark text", author="same_author")

        self.assertTrue(pb.bookmark_dedupe_key(first).startswith("content:"))
        self.assertEqual(pb.bookmark_dedupe_key(first), pb.bookmark_dedupe_key(second))
        self.assertNotEqual(pb.bookmark_dedupe_key(first), pb.bookmark_dedupe_key(distinct))

    def test_content_hash_is_deterministic_after_normalizing_nested_fields(self):
        first = self.sample_bookmark(
            id="",
            url="",
            external_urls=[
                {"expanded_url": "https://Example.com/path?utm_source=feed&b=2"},
                {"url": "https://twitter.com/TestPilot/status/123?s=20"},
            ],
            card={
                "url": "https://example.com/card?utm_medium=email&z=9",
                "title": " Durable   title ",
                "description": "Same\nsummary",
            },
            media=[
                {
                    "id": "media-1",
                    "type": "photo",
                    "media_url": "https://pbs.twimg.com/media/ABC?format=jpg&utm_campaign=x",
                    "alt_text": "Alt\ntext",
                }
            ],
        )
        reordered_equivalent = self.sample_bookmark(
            id="",
            url="",
            external_urls=[
                {"url": "https://x.com/i/web/status/123?utm_campaign=ignored"},
                {"expanded_url": "https://example.com/path?b=2&utm_medium=email"},
            ],
            card={
                "url": "https://EXAMPLE.com/card?z=9&utm_source=newsletter",
                "title": "Durable title",
                "description": "Same summary",
            },
            media=[
                {
                    "id": "media-1",
                    "type": "photo",
                    "media_url": "https://pbs.twimg.com/media/ABC?utm_source=feed&format=jpg",
                    "alt_text": "Alt text",
                }
            ],
        )
        distinct = self.sample_bookmark(id="", url="", text="A different deleted-bookmark insight.")

        first_hash = pb.bookmark_content_hash(first)
        self.assertEqual(first_hash, pb.bookmark_content_hash(reordered_equivalent))
        self.assertNotEqual(first_hash, pb.bookmark_content_hash(distinct))

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
        self.assertEqual(run["duplicates"][0]["cache_key"], run["results"][0]["cache_key"])

    def test_distinct_cache_misses_are_analyzed_and_cached_separately(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["id"])
            return {
                "folder": f"folder-{bookmark['id']}",
                "reason": f"fresh-{bookmark['id']}",
                "insights": bookmark["text"],
                "actionable": f"act-{bookmark['id']}",
            }

        first = self.sample_bookmark(id="124", url="https://x.com/TestPilot/status/124", text="Distinct insight 124")
        second = self.sample_bookmark(id="125", url="https://x.com/TestPilot/status/125", text="Distinct insight 125")

        run = asyncio.run(pb.analyze_bookmarks_with_cache([first, second], fake_analyze, cache={}))

        self.assertEqual(calls, ["124", "125"])
        self.assertEqual(run["cache_stats"], {"hits": 0, "misses": 2, "duplicates_suppressed": 0})
        self.assertEqual(run["duplicates"], [])
        self.assertEqual([result["cache_status"] for result in run["results"]], ["miss", "miss"])
        self.assertEqual([result["folder"] for result in run["results"]], ["folder-124", "folder-125"])
        self.assertNotEqual(run["results"][0]["cache_key"], run["results"][1]["cache_key"])
        self.assertIn(run["results"][0]["cache_key"], run["cache"]["entries"])
        self.assertIn(run["results"][1]["cache_key"], run["cache"]["entries"])

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

    def test_cache_hit_preserves_miss_path_enrichment_fields(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["id"])
            return {
                "folder": "coding",
                "reason": "fresh analysis",
                "insights": bookmark["text"],
                "actionable": "write regression test",
                "link_enrichment": [{"source": "tweet_external_url", "status": "ok", "title": "Example"}],
                "media_enrichment": [{"media_id": "m-1", "status": "skipped", "error": "video transcription disabled"}],
            }

        cache = {}
        first = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))
        second = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))

        self.assertEqual(calls, ["123"])
        self.assertEqual(first["results"][0]["cache_status"], "miss")
        self.assertEqual(second["results"][0]["cache_status"], "hit")
        self.assertEqual(second["results"][0]["link_enrichment"], first["results"][0]["link_enrichment"])
        self.assertEqual(second["results"][0]["media_enrichment"], first["results"][0]["media_enrichment"])

    def test_cache_version_mismatch_rejects_stale_entries_instead_of_overwriting(self):
        calls = []
        bookmark = self.sample_bookmark()
        key = pb.bookmark_dedupe_key(bookmark)
        stale_cache = {
            "version": "stale-version",
            "entries": {
                key: {
                    "analysis": {"folder": "archive", "reason": "stale", "insights": "old", "actionable": None},
                    "cached_at": "2026-06-01T00:00:00",
                    "source_url": bookmark["url"],
                    "content_hash": pb.bookmark_content_hash(bookmark),
                }
            },
        }

        async def fake_analyze(bookmark):
            calls.append(bookmark["id"])
            return {"folder": "coding", "reason": "fresh", "insights": "new", "actionable": None}

        run = asyncio.run(pb.analyze_bookmarks_with_cache([bookmark], fake_analyze, cache=stale_cache))

        self.assertEqual(calls, ["123"])
        self.assertEqual(run["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(run["results"][0]["cache_status"], "miss")
        self.assertEqual(run["results"][0]["folder"], "coding")
        self.assertEqual(run["cache"]["version"], pb.BOOKMARK_ANALYSIS_CACHE_VERSION)

    def test_non_x_query_s_and_ref_remain_content_significant(self):
        self.assertNotEqual(
            pb.normalize_bookmark_url("https://example.com/search?s=ai"),
            pb.normalize_bookmark_url("https://example.com/search?s=robotics"),
        )
        self.assertNotEqual(
            pb.normalize_bookmark_url("https://example.com/article?ref=a"),
            pb.normalize_bookmark_url("https://example.com/article?ref=b"),
        )
        self.assertEqual(
            pb.normalize_bookmark_url("https://twitter.com/testpilot/status/123?s=20&ref=feed"),
            "https://x.com/i/web/status/123",
        )

    def test_changed_bookmark_analysis_input_invalidates_url_cache_hit(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["text"])
            return {"folder": "coding", "reason": bookmark["text"], "insights": bookmark["text"], "actionable": None}

        cache = {}
        first = self.sample_bookmark(text="Original text with enough signal")
        changed = self.sample_bookmark(text="Changed text with different signal")
        first_run = asyncio.run(pb.analyze_bookmarks_with_cache([first], fake_analyze, cache=cache))
        second_run = asyncio.run(pb.analyze_bookmarks_with_cache([changed], fake_analyze, cache=cache))

        self.assertEqual(calls, ["Original text with enough signal", "Changed text with different signal"])
        self.assertEqual(first_run["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(second_run["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(second_run["results"][0]["cache_status"], "miss")
        self.assertEqual(second_run["results"][0]["insights"], "Changed text with different signal")

    def test_changed_model_policy_signature_invalidates_cache_hit(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(os.environ.get("BOOKMARK_ANALYSIS_POLICY_VERSION"))
            return {
                "folder": "coding",
                "reason": f"policy {os.environ.get('BOOKMARK_ANALYSIS_POLICY_VERSION')}",
                "insights": bookmark["text"],
                "actionable": None,
            }

        cache = {}
        previous = os.environ.get("BOOKMARK_ANALYSIS_POLICY_VERSION")
        try:
            os.environ["BOOKMARK_ANALYSIS_POLICY_VERSION"] = "policy-v1"
            first = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))
            os.environ["BOOKMARK_ANALYSIS_POLICY_VERSION"] = "policy-v2"
            second = asyncio.run(pb.analyze_bookmarks_with_cache([self.sample_bookmark()], fake_analyze, cache=cache))
        finally:
            if previous is None:
                os.environ.pop("BOOKMARK_ANALYSIS_POLICY_VERSION", None)
            else:
                os.environ["BOOKMARK_ANALYSIS_POLICY_VERSION"] = previous

        self.assertEqual(calls, ["policy-v1", "policy-v2"])
        self.assertEqual(first["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(second["cache_stats"], {"hits": 0, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual(second["results"][0]["reason"], "policy policy-v2")

    def test_second_run_keeps_normalized_hits_and_new_misses_separate(self):
        calls = []

        async def fake_analyze(bookmark):
            calls.append(bookmark["id"])
            return {
                "folder": f"folder-{bookmark['id']}",
                "reason": f"fresh-{bookmark['id']}",
                "insights": bookmark["text"],
                "actionable": f"act-{bookmark['id']}",
            }

        seed_cache = [
            self.sample_bookmark(id="123", url="https://x.com/TestPilot/status/123", text="Seeded 123"),
            self.sample_bookmark(id="124", url="https://x.com/TestPilot/status/124", text="Seeded 124"),
        ]
        cache = {}
        first = asyncio.run(pb.analyze_bookmarks_with_cache(seed_cache, fake_analyze, cache=cache))

        calls.clear()
        second_inputs = [
            self.sample_bookmark(id="123", url="https://twitter.com/testpilot/status/123?s=20", text="Seeded 123"),
            self.sample_bookmark(id="124", url="https://x.com/TestPilot/status/124?utm_source=feed", text="Seeded 124"),
            self.sample_bookmark(id="125", url="https://x.com/TestPilot/status/125", text="New miss 125"),
        ]
        second = asyncio.run(pb.analyze_bookmarks_with_cache(second_inputs, fake_analyze, cache=cache))

        self.assertEqual(first["cache_stats"], {"hits": 0, "misses": 2, "duplicates_suppressed": 0})
        self.assertEqual(calls, ["125"])
        self.assertEqual(second["cache_stats"], {"hits": 2, "misses": 1, "duplicates_suppressed": 0})
        self.assertEqual([result["cache_status"] for result in second["results"]], ["hit", "hit", "miss"])
        self.assertEqual([result["folder"] for result in second["results"]], ["folder-123", "folder-124", "folder-125"])
        self.assertEqual(second["results"][0]["cache_key"], first["results"][0]["cache_key"])
        self.assertEqual(second["results"][1]["cache_key"], first["results"][1]["cache_key"])
        self.assertNotEqual(second["results"][2]["cache_key"], first["results"][0]["cache_key"])
        self.assertNotEqual(second["results"][2]["cache_key"], first["results"][1]["cache_key"])


if __name__ == "__main__":
    unittest.main()
