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

    def test_learning_note_rejects_missing_or_invalid_source_url(self):
        for bad_url in ("", "x.com/good_ai/status/123", "ftp://example.com/bookmark"):
            with self.subTest(bad_url=bad_url):
                item = self.routed_bookmark(source_url=None, url=bad_url)

                with self.assertRaises(ValueError):
                    feed.build_learning_note_artifact(item, generated_on="2026-06-03")

    def test_learning_note_id_prefers_contract_source_fields_over_legacy_ids(self):
        item = self.routed_bookmark(
            id="fallback-id",
            bookmark_id="bookmark-id",
            source_id="legacy-source-id",
            source_item_id="canonical-source-item-id",
            _task_id="task-id",
        )

        artifact = feed.build_learning_note_artifact(item, generated_on="2026-06-03")

        self.assertEqual(artifact["filename"], "canonical-source-item-id.md")
        self.assertEqual(artifact["metadata"]["id"], "canonical-source-item-id")
        self.assertEqual(artifact["metadata"]["source_item_id"], "canonical-source-item-id")

    def test_learning_note_id_falls_back_to_task_id_after_id(self):
        item = self.routed_bookmark(id="")
        item.pop("id")
        item["_task_id"] = "task-id-fallback"
        item["url"] = "https://example.com/no-status-id"

        artifact = feed.build_learning_note_artifact(item, generated_on="2026-06-03")

        self.assertEqual(artifact["filename"], "task-id-fallback.md")
        self.assertEqual(artifact["metadata"]["id"], "task-id-fallback")
        self.assertEqual(artifact["metadata"]["source_item_id"], "task-id-fallback")

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

    def test_learning_note_writer_suffixes_distinct_ids_with_same_sanitized_filename(self):
        first = feed.build_learning_note_artifact(self.routed_bookmark(id="bookmark:123"), generated_on="2026-06-03")
        second = feed.build_learning_note_artifact(self.routed_bookmark(id="bookmark/123"), generated_on="2026-06-03")

        with tempfile.TemporaryDirectory() as tempdir:
            result = feed.write_learning_note_artifacts([first, second], Path(tempdir) / "learning_notes")
            note_paths = sorted(Path(path) for path in result["files"])
            filenames = sorted(path.name for path in note_paths)
            parsed_ids = sorted(
                feed.parse_learning_note_metadata(path.read_text(encoding="utf-8"))["source_item_id"]
                for path in note_paths
            )

        self.assertEqual(result["inserted"], 2)
        self.assertEqual(filenames, ["bookmark-123-2.md", "bookmark-123.md"])
        self.assertEqual(parsed_ids, ["bookmark/123", "bookmark:123"])

    def test_learning_note_writer_does_not_treat_filename_collision_as_duplicate(self):
        existing = feed.build_learning_note_artifact(self.routed_bookmark(id="bookmark:123"), generated_on="2026-06-03")
        colliding = feed.build_learning_note_artifact(self.routed_bookmark(id="bookmark/123"), generated_on="2026-06-04")

        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"
            feed.write_learning_note_artifacts([existing], notes_dir)
            result = feed.write_learning_note_artifacts([colliding], notes_dir)
            note_paths = sorted(notes_dir.glob("*.md"))
            filenames = sorted(path.name for path in note_paths)
            parsed_ids = sorted(
                feed.parse_learning_note_metadata(path.read_text(encoding="utf-8"))["source_item_id"]
                for path in note_paths
            )

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["noop"], 0)
        self.assertEqual(filenames, ["bookmark-123-2.md", "bookmark-123.md"])
        self.assertEqual(parsed_ids, ["bookmark/123", "bookmark:123"])

    def test_learning_note_repeated_run_suppresses_duplicate_by_source_item_id(self):
        """Processing the same bookmark twice produces exactly one note artifact."""
        bookmark = self.routed_bookmark(id="repeat-run-456", url="https://x.com/good_ai/status/456")
        routed = {
            "immediate_actions": [bookmark],
            "research_queue": [],
            "knowledge_promotions": [],
        }

        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"

            first = feed.write_learning_notes_from_routed(
                routed, generated_on="2026-06-03", notes_dir=notes_dir
            )
            second = feed.write_learning_notes_from_routed(
                routed, generated_on="2026-06-04", notes_dir=notes_dir
            )
            third = feed.write_learning_notes_from_routed(
                routed, generated_on="2026-06-05", notes_dir=notes_dir
            )

            note_files = list(notes_dir.glob("*.md"))
            self.assertEqual(len(note_files), 1)
            self.assertEqual(note_files[0].name, "repeat-run-456.md")

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(first["suppressed"], 0)
        self.assertEqual(second["suppressed"], 1)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(second["noop"], 0)
        self.assertEqual(third["suppressed"], 1)
        self.assertEqual(third["inserted"], 0)
        self.assertEqual(third["updated"], 0)
        self.assertEqual(third["noop"], 0)

    def test_learning_note_dedupe_ignores_non_learning_note_files(self):
        """Only learning-note/v1 files are scanned for existing source_item_id values."""
        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "random.md").write_text("# Not a learning note\n", encoding="utf-8")

            bookmark = self.routed_bookmark(id="new-bookmark-789")
            routed = {
                "immediate_actions": [bookmark],
                "research_queue": [],
                "knowledge_promotions": [],
            }
            result = feed.write_learning_notes_from_routed(
                routed, generated_on="2026-06-03", notes_dir=notes_dir
            )

            note_files = list(notes_dir.glob("*.md"))
            self.assertEqual(len(note_files), 2)
            self.assertEqual(result["inserted"], 1)
            self.assertEqual(result["suppressed"], 0)

    def test_learning_note_dedupe_ignores_wrong_schema_version_files(self):
        stale = feed.build_learning_note_artifact(
            self.routed_bookmark(id="schema-version-ignored"),
            generated_on="2026-06-02",
        )["content"].replace(
            'schema_version: "learning-note/v1"',
            'schema_version: "learning-note/v0"',
            1,
        )
        routed = {
            "immediate_actions": [self.routed_bookmark(id="schema-version-ignored")],
            "research_queue": [],
            "knowledge_promotions": [],
        }

        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"
            notes_dir.mkdir(parents=True, exist_ok=True)
            (notes_dir / "schema-version-ignored.md").write_text(stale, encoding="utf-8")

            result = feed.write_learning_notes_from_routed(
                routed, generated_on="2026-06-03", notes_dir=notes_dir
            )
            note_files = sorted(path.name for path in notes_dir.glob("*.md"))

        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["suppressed"], 0)
        self.assertEqual(note_files, ["schema-version-ignored-2.md", "schema-version-ignored.md"])

    def test_learning_note_repeated_run_updates_when_content_changes(self):
        """If the same source_item_id is reprocessed with different content on a repeated run,
        the existing note is suppressed (not updated) to avoid churn from generated_on changes."""
        first = self.routed_bookmark(id="update-me-999", url="https://x.com/good_ai/status/999")
        second = self.routed_bookmark(
            id="update-me-999",
            url="https://x.com/good_ai/status/999",
            insight="Changed insight.",
        )
        routed_first = {
            "immediate_actions": [first],
            "research_queue": [],
            "knowledge_promotions": [],
        }
        routed_second = {
            "immediate_actions": [second],
            "research_queue": [],
            "knowledge_promotions": [],
        }

        with tempfile.TemporaryDirectory() as tempdir:
            notes_dir = Path(tempdir) / "learning_notes"

            feed.write_learning_notes_from_routed(
                routed_first, generated_on="2026-06-03", notes_dir=notes_dir
            )
            result = feed.write_learning_notes_from_routed(
                routed_second, generated_on="2026-06-04", notes_dir=notes_dir
            )
            content = (notes_dir / "update-me-999.md").read_text(encoding="utf-8")

        self.assertEqual(result["suppressed"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertNotIn("Changed insight.", content)
        self.assertIn("Agent memory systems need remember/cite/forget layers", content)

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
            {"enabled": False, "artifacts": 0, "inserted": 0, "updated": 0, "noop": 0, "suppressed": 0, "files": []},
        )
        self.assertEqual(note_files, [])
        memo = feed.render_opportunity_memo(routed, "2026-06-03")
        self.assertIn("Immediate executable actions", memo)
        self.assertIn("Knowledge-base promotions", memo)


if __name__ == "__main__":
    unittest.main()
