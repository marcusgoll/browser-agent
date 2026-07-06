#!/usr/bin/env python3
"""Tests for concise X bookmark learning note artifacts."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import feed_to_agents as feed  # noqa: E402


class LearningNoteTests(unittest.TestCase):
    def routed_bookmark(self, **overrides):
        bookmark = {
            "id": "x-bookmark-source-123",
            "author": "good_ai",
            "url": "https://x.com/good_ai/status/123",
            "project_bucket": "hermes",
            "source_section": "knowledge_promotions",
            "insight": "Agent memory systems need remember/cite/forget layers before adding more tools.",
            "action": "Add a small memory hygiene checklist to the Hermes operator workflow.",
            "why": "Durable concept worth promoting into wiki/skills if still novel after dedupe.",
            "score": 18,
        }
        bookmark.update(overrides)
        return bookmark

    def test_learning_note_renders_expected_short_artifact_from_routed_bookmark(self):
        artifact = feed.build_learning_note_artifact(self.routed_bookmark(), generated_on="2026-06-03")

        self.assertEqual(artifact["filename"], "x-bookmark-source-123.md")
        self.assertEqual(
            artifact["metadata"],
            {
                "schema_version": "learning-note/v1",
                "id": "x-bookmark-source-123",
                "source_item_id": "x-bookmark-source-123",
                "source_url": "https://x.com/good_ai/status/123",
                "author": "good_ai",
                "project_bucket": "hermes",
                "source_section": "knowledge_promotions",
                "generated_on": "2026-06-03",
            },
        )
        self.assertEqual(
            artifact["content"],
            "---\n"
            'schema_version: "learning-note/v1"\n'
            'id: "x-bookmark-source-123"\n'
            'source_item_id: "x-bookmark-source-123"\n'
            'source_url: "https://x.com/good_ai/status/123"\n'
            'author: "good_ai"\n'
            'project_bucket: "hermes"\n'
            'source_section: "knowledge_promotions"\n'
            'generated_on: "2026-06-03"\n'
            "---\n"
            "# Agent memory systems need remember/cite/forget layers before adding more tools.\n\n"
            "## Takeaway\n"
            "Agent memory systems need remember/cite/forget layers before adding more tools.\n\n"
            "## Action\n"
            "Add a small memory hygiene checklist to the Hermes operator workflow.\n\n"
            "## Why now\n"
            "Durable concept worth promoting into wiki/skills if still novel after dedupe.\n\n"
            "Source: https://x.com/good_ai/status/123\n",
        )

    def test_learning_note_metadata_round_trips_losslessly(self):
        artifact = feed.build_learning_note_artifact(self.routed_bookmark(), generated_on="2026-06-03")

        parsed = feed.parse_learning_note_metadata(artifact["content"])

        self.assertEqual(parsed, artifact["metadata"])

    def test_learning_note_metadata_preserves_routed_source_fields_exactly(self):
        item = self.routed_bookmark(
            source_url='https://example.com/path?q=a:b&quote="yes"',
            url="https://fallback.example/should-not-be-used",
            author='Jane: The "Builder"',
            project_bucket="bucket:with punctuation / spaces",
            source_section="research_queue",
        )

        artifact = feed.build_learning_note_artifact(item, generated_on="2026-06-03")
        parsed = feed.parse_learning_note_metadata(artifact["content"])

        self.assertEqual(parsed["source_url"], 'https://example.com/path?q=a:b&quote="yes"')
        self.assertEqual(parsed["author"], 'Jane: The "Builder"')
        self.assertEqual(parsed["project_bucket"], "bucket:with punctuation / spaces")
        self.assertEqual(parsed["source_section"], "research_queue")

    def test_learning_note_project_bucket_uses_project_before_folder_fallback(self):
        artifact = feed.build_learning_note_artifact(
            self.routed_bookmark(project_bucket=None, project="project-route", folder="folder-route"),
            generated_on="2026-06-03",
        )

        self.assertEqual(artifact["metadata"]["project_bucket"], "project-route")
        self.assertEqual(
            feed.parse_learning_note_metadata(artifact["content"])["project_bucket"],
            "project-route",
        )

    def test_learning_notes_build_from_existing_opportunity_router_sections(self):
        routed = {"immediate_actions": [self.routed_bookmark()], "research_queue": [], "knowledge_promotions": []}

        artifacts = feed.build_learning_note_artifacts(routed, generated_on="2026-06-03")

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["metadata"]["id"], "x-bookmark-source-123")
        self.assertEqual(artifacts[0]["metadata"]["project_bucket"], "hermes")
        self.assertIn("## Takeaway\nAgent memory systems", artifacts[0]["content"])

    def test_learning_note_writer_updates_same_canonical_id_instead_of_duplicating(self):
        first = self.routed_bookmark(id="stable-bookmark-123", url="https://x.com/good_ai/status/123")
        second = self.routed_bookmark(
            id="stable-bookmark-123",
            url="https://x.com/good_ai/status/123?utm_source=second-run",
            insight="Updated insight for the same bookmarked source item.",
        )

        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"

            first_result = feed.write_learning_note_artifacts(
                [feed.build_learning_note_artifact(first, generated_on="2026-06-03")],
                notes_dir,
            )
            second_artifact = feed.build_learning_note_artifact(second, generated_on="2026-06-04")
            second_result = feed.write_learning_note_artifacts(
                [second_artifact],
                notes_dir,
            )
            third_result = feed.write_learning_note_artifacts([second_artifact], notes_dir)

            note_files = list(notes_dir.glob("*.md"))
            self.assertEqual(len(note_files), 1)
            self.assertEqual(note_files[0].name, "stable-bookmark-123.md")
            self.assertIn(
                "Updated insight for the same bookmarked source item.",
                note_files[0].read_text(encoding="utf-8"),
            )

        self.assertEqual(first_result["inserted"], 1)
        self.assertEqual(second_result["updated"], 1)
        self.assertEqual(third_result["noop"], 1)

    def test_learning_note_artifacts_dedupe_repeated_canonical_id_across_sections(self):
        duplicate = self.routed_bookmark(id="stable-bookmark-123", source_url="https://example.com/changed")
        routed = {
            "immediate_actions": [self.routed_bookmark(id="stable-bookmark-123")],
            "research_queue": [duplicate],
            "knowledge_promotions": [],
        }

        artifacts = feed.build_learning_note_artifacts(routed, generated_on="2026-06-03")

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["metadata"]["id"], "stable-bookmark-123")

    def test_learning_note_artifacts_dedupe_by_canonical_x_status_when_bookmark_id_missing(self):
        first = self.routed_bookmark(
            id=None,
            source_item_id=None,
            url="https://x.com/good_ai/status/123",
            source_url="https://x.com/good_ai/status/123",
        )
        duplicate = self.routed_bookmark(
            id=None,
            source_item_id=None,
            url="https://x.com/good_ai/status/123?utm_source=rerun",
            source_url="https://x.com/good_ai/status/123?utm_source=rerun",
        )
        routed = {
            "immediate_actions": [first],
            "research_queue": [duplicate],
            "knowledge_promotions": [],
        }

        artifacts = feed.build_learning_note_artifacts(routed, generated_on="2026-06-03")

        self.assertEqual(len(artifacts), 1)
        self.assertEqual(artifacts[0]["metadata"]["id"], "123")

    def test_learning_note_artifacts_keep_distinct_bookmark_ids_for_same_source_url(self):
        routed = {
            "immediate_actions": [
                self.routed_bookmark(id="bookmark-a", source_url="https://x.com/good_ai/status/123"),
                self.routed_bookmark(id="bookmark-b", source_url="https://x.com/good_ai/status/123"),
            ],
            "research_queue": [],
            "knowledge_promotions": [],
        }

        artifacts = feed.build_learning_note_artifacts(routed, generated_on="2026-06-03")

        self.assertEqual(
            [artifact["metadata"]["id"] for artifact in artifacts],
            ["bookmark-a", "bookmark-b"],
        )
        self.assertEqual(
            [artifact["filename"] for artifact in artifacts],
            ["bookmark-a.md", "bookmark-b.md"],
        )

    def test_learning_notes_enabled_honors_env_rollback_switch(self):
        for disabled_value in ("0", "false", "no", "off"):
            with self.subTest(disabled_value=disabled_value):
                self.assertFalse(
                    feed.learning_notes_enabled({"BOOKMARK_LEARNING_NOTES_ENABLED": disabled_value})
                )
        self.assertTrue(feed.learning_notes_enabled({"BOOKMARK_LEARNING_NOTES_ENABLED": "1"}))
        self.assertTrue(feed.learning_notes_enabled({}))

    def test_learning_note_output_can_be_disabled_without_replacing_opportunity_memo(self):
        routed = {
            "generated_from": "x_bookmark_analysis",
            "total_processed": 1,
            "action_summary": {"ok": 1, "error": 0, "skipped": 0},
            "immediate_actions": [self.routed_bookmark()],
            "research_queue": [],
            "knowledge_promotions": [],
            "project_routes": [],
            "skipped": {},
        }

        with tempfile.TemporaryDirectory() as tempdir:
            result = feed.write_learning_notes_from_routed(
                routed,
                generated_on="2026-06-03",
                notes_dir=Path(tempdir) / "learning_notes",
                enabled=False,
            )
            note_files = list(Path(tempdir).glob("**/*.md"))

        self.assertEqual(
            result,
            {"enabled": False, "artifacts": 0, "inserted": 0, "updated": 0, "noop": 0, "files": []},
        )
        self.assertEqual(note_files, [])
        memo = feed.render_opportunity_memo(routed, "2026-06-03")
        self.assertIn("Immediate executable actions", memo)
        self.assertIn("Knowledge-base promotions", memo)


if __name__ == "__main__":
    unittest.main()
