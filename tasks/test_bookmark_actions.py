#!/usr/bin/env python3
"""Deterministic tests for X bookmark action planning/mutations."""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import process_bookmarks as pb  # noqa: E402


class FakePage:
    def __init__(self, response):
        self.response = response
        self.calls = []

    async def evaluate(self, script, payload):
        self.calls.append(payload)
        return self.response


class BookmarkActionTests(unittest.TestCase):
    def test_extract_folder_entities_handles_nested_x_shapes_and_dedupes(self):
        payload = {
            "data": {
                "viewer": {
                    "user_results": {
                        "result": {
                            "bookmark_collections_slice": {
                                "items": [
                                    {"id": "111", "name": "AI Tools & Agents"},
                                    {"rest_id": "222", "name": "DevOps & Infrastructure"},
                                    {"id": "111", "name": "AI Tools & Agents"},
                                ]
                            }
                        }
                    }
                }
            }
        }
        self.assertEqual(
            pb._extract_folder_entities(payload),
            [
                {"id": "111", "name": "AI Tools & Agents"},
                {"id": "222", "name": "DevOps & Infrastructure"},
            ],
        )

    def test_summarize_action_results_counts_status_and_action(self):
        summary = pb.summarize_action_results([
            {"action": "move", "status": "ok"},
            {"action": "delete", "status": "error"},
            {"action": "move", "status": "skipped"},
        ])
        self.assertEqual(summary["ok"], 1)
        self.assertEqual(summary["error"], 1)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["by_action"], {"move": 2, "delete": 1})

    def test_delete_bookmark_uses_x_graphql_delete_mutation(self):
        page = FakePage({"ok": True, "status": 200, "json": {"data": {"tweet_bookmark_delete": "Done"}}, "text": "{}"})
        with patch.object(pb, "X_BEARER_TOKEN", "test-token"):
            result = asyncio.run(pb.delete_bookmark(page, "12345"))
        self.assertEqual(result, {"action": "delete", "status": "ok", "tweet_id": "12345"})
        self.assertEqual(page.calls[0]["operationName"], "DeleteBookmark")
        self.assertEqual(page.calls[0]["queryId"], pb.GRAPHQL_OPERATION_IDS["DeleteBookmark"])
        self.assertEqual(page.calls[0]["variables"], {"tweet_id": "12345"})

    def test_move_bookmark_uses_x_graphql_folder_mutation(self):
        page = FakePage({"ok": True, "status": 200, "json": {"data": {"bookmark_collection_tweet_put": "Done"}}, "text": "{}"})
        with patch.object(pb, "X_BEARER_TOKEN", "test-token"):
            result = asyncio.run(pb.move_bookmark_to_folder(page, "12345", "folder-1", "AI Tools & Agents"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["action"], "move")
        self.assertEqual(page.calls[0]["operationName"], "bookmarkTweetToFolder")
        self.assertEqual(page.calls[0]["variables"], {"bookmark_collection_id": "folder-1", "tweet_id": "12345"})

    def test_graphql_mutation_requires_explicit_bearer_token(self):
        page = FakePage({"ok": True})
        with patch.object(pb, "X_BEARER_TOKEN", ""):
            result = asyncio.run(pb.x_graphql_request(page, "DeleteBookmark", {"tweet_id": "12345"}))
        self.assertFalse(result["ok"])
        self.assertIn("X_BEARER_TOKEN", result["error"])
        self.assertEqual(page.calls, [])

    def test_apply_bookmark_action_deletes_delete_folder(self):
        with patch.object(pb, "delete_bookmark", new=AsyncMock(return_value={"action": "delete", "status": "ok", "tweet_id": "9"})) as delete_mock:
            result = asyncio.run(pb.apply_bookmark_action(object(), {"id": "9", "folder": "delete"}, {}))
        self.assertEqual(result["status"], "ok")
        delete_mock.assert_awaited_once()

    def test_apply_bookmark_action_moves_known_folder_from_cache(self):
        cache = {"AI Tools & Agents": {"id": "folder-1", "name": "AI Tools & Agents"}}
        page = object()
        with patch.object(pb, "move_bookmark_to_folder", new=AsyncMock(return_value={"action": "move", "status": "ok"})) as move_mock:
            result = asyncio.run(pb.apply_bookmark_action(page, {"id": "9", "folder": "ai_tools"}, cache))
        self.assertEqual(result["status"], "ok")
        move_mock.assert_awaited_once_with(page, "9", "folder-1", "AI Tools & Agents")

    def test_write_bookmark_outputs_keeps_legacy_files_and_adds_versioned_artifact(self):
        analysis = [{"id": "9", "author": "tester", "folder": "ai_tools", "url": "https://x.com/test/status/9"}]
        summary = {
            "total_processed": 1,
            "dry_run": True,
            "action_summary": {"ok": 0, "error": 0, "skipped": 1, "by_action": {"move": 1}},
            "by_folder": {"ai_tools": 1},
            "insights": [],
            "action_items": [],
            "edge_case_counts": {},
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            written = pb.write_bookmark_outputs(
                results=analysis,
                summary=summary,
                output_dir=Path(tmpdir),
                timestamp="20260531_090410",
                generated_at="2026-05-31T09:04:10",
            )
            legacy_analysis = Path(written["analysis"])
            legacy_summary = Path(written["summary"])
            artifact_path = Path(written["artifact"])

            self.assertEqual(json.loads(legacy_analysis.read_text()), analysis)
            self.assertEqual(json.loads(legacy_summary.read_text()), summary)
            artifact = json.loads(artifact_path.read_text())
            self.assertEqual(artifact["schema_version"], pb.bookmark_schema.CURRENT_SCHEMA_VERSION)
            self.assertEqual(artifact["artifact_type"], "bookmark_run")
            self.assertEqual(artifact["data"], {"summary": summary, "analysis": analysis})


if __name__ == "__main__":
    unittest.main()
