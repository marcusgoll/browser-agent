#!/usr/bin/env python3
"""Tests for deterministic weekly bookmark digest input aggregation."""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import weekly_bookmark_digest as digest  # noqa: E402


FIXED_WEEK_START = "2026-05-25"
FIXED_WEEK_END = "2026-06-01"
FIXED_WEEK_NOW = datetime(2026, 5, 31, 12, 0, 0)
FIXED_WEEK_OUTPUT_DIR = "<fixture-output-dir>"


class FrozenWeeklyDigestDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is not None:
            return FIXED_WEEK_NOW.replace(tzinfo=tz)
        return FIXED_WEEK_NOW


def write_fixture_json(root, relative_path, payload):
    path = Path(root) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def seed_fixed_week_digest_inputs(root):
    """Seed the reusable fixed-week digest fixture in an isolated root."""
    root = Path(root)
    write_fixture_json(
        root,
        "bookmark_summary_20260531_090410.json",
        {
            "total_processed": 4,
            "action_summary": {"ok": 3, "error": 1, "skipped": 0, "by_action": {"move": 2, "archive": 1}},
            "by_folder": {"ai_tools": 3, "research": 1},
            "edge_case_counts": {"missing_id": 1},
            "insights": [
                {
                    "author": "agent_builder",
                    "insight": "Use permission gates before adding autonomous execution.",
                    "url": "https://x.com/agent_builder/status/1?utm_source=test",
                },
                {
                    "author": "solo_item",
                    "insight": "Keep digest generation lightweight.",
                    "url": "https://x.com/solo_item/status/2",
                },
            ],
            "action_items": [
                {
                    "author": "agent_builder",
                    "action": "Add a checklist for approval-gated agent tasks.",
                    "url": "https://x.com/agent_builder/status/1",
                }
            ],
        },
    )
    write_fixture_json(
        root,
        "bookmark_summary_20260601_000000.json",
        {
            "total_processed": 99,
            "insights": [{"author": "outside", "insight": "outside week", "url": "https://x.com/outside/status/99"}],
        },
    )
    write_fixture_json(
        root,
        "opportunities/opportunity_router_2026-05-31.json",
        {
            "immediate_actions": [
                {
                    "author": "agent_builder",
                    "insight": "Use permission gates before adding autonomous execution.",
                    "action": "Add a checklist for approval-gated agent tasks.",
                    "url": "https://x.com/agent_builder/status/1",
                    "folder": "ai_tools",
                    "score": 42,
                    "why": "Executable and relevant.",
                }
            ],
            "research_queue": [
                {
                    "author": "researcher",
                    "insight": "Compare browser automation memory approaches.",
                    "action": "Review memory store tradeoffs.",
                    "url": "https://x.com/researcher/status/3",
                    "folder": "research",
                    "score": 18,
                    "why": "Useful but lower urgency.",
                }
            ],
            "knowledge_promotions": [
                {
                    "author": "agent_builder",
                    "insight": "Permission gates are durable agent architecture.",
                    "action": "Promote approval gates to the wiki.",
                    "url": "https://x.com/agent_builder/status/1",
                    "folder": "ai_tools",
                    "score": 51,
                    "why": "Durable concept.",
                }
            ],
            "project_routes": [
                {
                    "author": "router",
                    "insight": "Memory tooling belongs in the Hermes project lane.",
                    "action": "Route this bookmark to Hermes follow-up.",
                    "url": "https://x.com/router/status/9",
                    "folder": "ai_tools",
                    "project": "hermes_agent",
                    "route_score": 23,
                    "route_why": "Primary route justified by agent memory work.",
                }
            ],
        },
    )
    write_fixture_json(
        root,
        "opportunities/high_roi_tasks_2026-05-31.json",
        {
            "tasks": [
                {
                    "id": "x-bookmark-permission",
                    "source_section": "immediate_actions",
                    "task_type": "implementation",
                    "title": "Execute: Add approval gates",
                    "source_url": "https://x.com/agent_builder/status/1",
                    "bookmark_author": "agent_builder",
                    "folder": "ai_tools",
                    "score": 47,
                    "insight": "Use permission gates before adding autonomous execution.",
                    "suggested_action": "Add a checklist for approval-gated agent tasks.",
                    "why": "High ROI.",
                    "priority": 1,
                }
            ]
        },
    )
    learning_note = root / "learning_notes" / "permission.md"
    learning_note.parent.mkdir(parents=True, exist_ok=True)
    learning_note.write_text(
        "---\n"
        'id: "note-permission"\n'
        'source_url: "https://x.com/agent_builder/status/1"\n'
        'author: "agent_builder"\n'
        'project_bucket: "ai_tools"\n'
        'generated_on: "2026-05-31"\n'
        "---\n"
        "# Permission gates\n\n"
        "## Takeaway\nPermission gates make agents safer.\n\n"
        "## Action\nAdd approval checklist.\n",
        encoding="utf-8",
    )
    write_fixture_json(
        root,
        "content_ideas/permission-idea.json",
        {
            "generated_on": "2026-05-31",
            "source_url": "https://x.com/agent_builder/status/1",
            "hook": "Your agent should ask before it acts",
            "angle": "Approval gates as product safety",
            "audience": "agent operators",
            "proof_point": "Same source appears in routes, tasks, and notes.",
        },
    )


def build_fixed_week_digest_payload(root):
    root = Path(root)
    seed_fixed_week_digest_inputs(root)
    with mock.patch.object(digest, "datetime", FrozenWeeklyDigestDateTime):
        payload = digest.build_weekly_digest_input(FIXED_WEEK_START, output_dir=root)
    payload["generated_from"]["output_dir"] = FIXED_WEEK_OUTPUT_DIR
    return payload


class WeeklyDigestInputTests(unittest.TestCase):
    def write_json(self, root, relative_path, payload):
        path = Path(root) / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def snapshot_text(self, relative_path):
        return (Path(__file__).resolve().parent / "snapshots" / relative_path).read_text(encoding="utf-8")

    def assert_matches_snapshot(self, actual, relative_path):
        expected = self.snapshot_text(relative_path)
        self.assertEqual(actual, expected)

    def test_fixed_week_fixture_rebuilds_identical_payloads_in_isolated_roots(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            first = build_fixed_week_digest_payload(first_dir)
            second = build_fixed_week_digest_payload(second_dir)
            seeded_files = sorted(
                path.relative_to(first_dir).as_posix()
                for path in Path(first_dir).rglob("*")
                if path.is_file()
            )

        self.assertEqual(FrozenWeeklyDigestDateTime.now(), FIXED_WEEK_NOW)
        self.assertEqual(first, second)
        self.assertEqual(first["week"], {"week_start": FIXED_WEEK_START, "week_end": FIXED_WEEK_END})
        self.assertEqual(first["generated_from"]["output_dir"], FIXED_WEEK_OUTPUT_DIR)
        self.assertEqual(
            seeded_files,
            [
                "bookmark_summary_20260531_090410.json",
                "bookmark_summary_20260601_000000.json",
                "content_ideas/permission-idea.json",
                "learning_notes/permission.md",
                "opportunities/high_roi_tasks_2026-05-31.json",
                "opportunities/opportunity_router_2026-05-31.json",
            ],
        )
        self.assertIn("bookmark_summary_20260531_090410.json", first["generated_from"]["source_files"])
        self.assertNotIn("bookmark_summary_20260601_000000.json", first["generated_from"]["source_files"])
        self.assertEqual(first["source_counts"]["route_items"], 4)
        self.assertEqual(first["source_counts"]["task_items"], 1)
        self.assertEqual(first["source_counts"]["learning_notes"], 1)
        self.assertEqual(first["source_counts"]["content_ideas"], 1)

    def build_fixed_week_digest_payload(self, root):
        return build_fixed_week_digest_payload(root)

    def test_fixed_week_aggregation_is_deterministic_and_dedupes_repeated_source_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_json(
                tmpdir,
                "bookmark_summary_20260531_090410.json",
                {
                    "total_processed": 3,
                    "action_summary": {"ok": 2, "error": 1, "skipped": 0, "by_action": {"move": 2, "delete": 1}},
                    "by_folder": {"ai_tools": 2, "coding": 1},
                    "edge_case_counts": {"missing_id": 1},
                    "insights": [
                        {
                            "author": "agent_builder",
                            "insight": "Use permission gates before adding autonomous execution.",
                            "url": "https://x.com/agent_builder/status/1?utm_source=test",
                        },
                        {
                            "author": "solo_item",
                            "insight": "Keep digest generation lightweight.",
                            "url": "https://x.com/solo_item/status/2",
                        },
                    ],
                    "action_items": [
                        {
                            "author": "agent_builder",
                            "action": "Add a checklist for approval-gated agent tasks.",
                            "url": "https://x.com/agent_builder/status/1",
                        }
                    ],
                },
            )
            self.write_json(
                tmpdir,
                "bookmark_summary_20260602_090410.json",
                {
                    "total_processed": 99,
                    "insights": [
                        {"author": "outside", "insight": "outside week", "url": "https://x.com/outside/status/99"}
                    ],
                },
            )
            self.write_json(
                tmpdir,
                "opportunities/opportunity_router_2026-05-31.json",
                {
                    "immediate_actions": [
                        {
                            "author": "agent_builder",
                            "insight": "Use permission gates before adding autonomous execution.",
                            "action": "Add a checklist for approval-gated agent tasks.",
                            "url": "https://x.com/agent_builder/status/1",
                            "folder": "ai_tools",
                            "score": 42,
                            "why": "Executable and relevant.",
                        }
                    ],
                    "research_queue": [],
                    "knowledge_promotions": [
                        {
                            "author": "agent_builder",
                            "insight": "Permission gates are durable agent architecture.",
                            "action": "Promote approval gates to the wiki.",
                            "url": "https://x.com/agent_builder/status/1",
                            "folder": "ai_tools",
                            "score": 51,
                            "why": "Durable concept.",
                        }
                    ],
                },
            )
            self.write_json(
                tmpdir,
                "opportunities/high_roi_tasks_2026-05-31.json",
                {
                    "tasks": [
                        {
                            "id": "x-bookmark-permission",
                            "source_section": "immediate_actions",
                            "task_type": "implementation",
                            "title": "Execute: Add approval gates",
                            "source_url": "https://x.com/agent_builder/status/1",
                            "bookmark_author": "agent_builder",
                            "folder": "ai_tools",
                            "score": 47,
                            "insight": "Use permission gates before adding autonomous execution.",
                            "suggested_action": "Add a checklist for approval-gated agent tasks.",
                            "why": "High ROI.",
                            "priority": 1,
                        }
                    ]
                },
            )
            learning_note = Path(tmpdir) / "learning_notes" / "permission.md"
            learning_note.parent.mkdir(parents=True, exist_ok=True)
            learning_note.write_text(
                "---\n"
                'id: "note-permission"\n'
                'source_url: "https://x.com/agent_builder/status/1"\n'
                'author: "agent_builder"\n'
                'project_bucket: "ai_tools"\n'
                'generated_on: "2026-05-31"\n'
                "---\n"
                "# Permission gates\n\n"
                "## Takeaway\nPermission gates make agents safer.\n\n"
                "## Action\nAdd approval checklist.\n",
                encoding="utf-8",
            )
            self.write_json(
                tmpdir,
                "content_ideas/permission-idea.json",
                {
                    "generated_on": "2026-05-31",
                    "source_url": "https://x.com/agent_builder/status/1",
                    "hook": "Your agent should ask before it acts",
                    "angle": "Approval gates as product safety",
                    "audience": "agent operators",
                    "proof_point": "Same source appears in routes, tasks, and notes.",
                },
            )

            first = digest.build_weekly_digest_input("2026-05-25", output_dir=Path(tmpdir))
            second = digest.build_weekly_digest_input("2026-05-25", output_dir=Path(tmpdir))

        self.assertEqual(json.dumps(first, sort_keys=True), json.dumps(second, sort_keys=True))
        self.assertEqual(first["schema_version"], "weekly-bookmark-digest-input/v1")
        self.assertEqual(first["week"], {"week_start": "2026-05-25", "week_end": "2026-06-01"})
        self.assertEqual(first["summary"]["total_processed"], 3)
        self.assertEqual(first["summary"]["by_folder"], {"ai_tools": 2, "coding": 1})
        self.assertEqual(first["summary"]["action_summary"]["by_action"], {"delete": 1, "move": 2})
        self.assertEqual(first["source_counts"]["bookmark_summary_runs"], 1)
        self.assertEqual(first["source_counts"]["route_items"], 2)
        self.assertEqual(first["source_counts"]["task_items"], 1)
        self.assertEqual(first["source_counts"]["learning_notes"], 1)
        self.assertEqual(first["source_counts"]["content_ideas"], 1)

        source_urls = [item["source_url"] for item in first["digest_items"]]
        self.assertEqual(source_urls, ["https://x.com/agent_builder/status/1", "https://x.com/solo_item/status/2"])
        repeated = first["digest_items"][0]
        self.assertEqual(repeated["top_score"], 51)
        self.assertEqual(
            repeated["signals"],
            [
                "action_item",
                "bookmark_insight",
                "content_idea",
                "learning_note",
                "route:immediate_actions",
                "route:knowledge_promotions",
                "task",
            ],
        )
        self.assertEqual(repeated["authors"], ["agent_builder"])
        self.assertEqual(repeated["folders"], ["ai_tools"])
        self.assertIn("Use permission gates before adding autonomous execution.", repeated["insights"])
        self.assertIn("Add a checklist for approval-gated agent tasks.", repeated["actions"])
        self.assertEqual(
            repeated["content_ideas"],
            [
                {
                    "hook": "Your agent should ask before it acts",
                    "angle": "Approval gates as product safety",
                    "audience": "agent operators",
                    "proof_point": "Same source appears in routes, tasks, and notes.",
                }
            ],
        )

    def test_project_routes_are_aggregated_as_route_signals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_json(
                tmpdir,
                "opportunities/opportunity_router_2026-05-31.json",
                {
                    "immediate_actions": [],
                    "research_queue": [],
                    "knowledge_promotions": [],
                    "project_routes": [
                        {
                            "author": "router",
                            "insight": "Memory tooling belongs in the Hermes project lane.",
                            "action": "Route this bookmark to Hermes follow-up.",
                            "url": "https://x.com/router/status/9",
                            "folder": "ai_tools",
                            "project": "hermes_agent",
                            "route_score": 23,
                            "route_why": "primary route justified by agent, memory.",
                            "secondary_routes": [{"project": "knowledge_base", "score": 11}],
                        }
                    ],
                },
            )

            payload = digest.build_weekly_digest_input("2026-05-25", output_dir=Path(tmpdir))

        self.assertEqual(payload["source_counts"]["route_items"], 1)
        self.assertEqual(len(payload["digest_items"]), 1)
        item = payload["digest_items"][0]
        self.assertEqual(item["signals"], ["route:project_routes"])
        self.assertEqual(item["top_score"], 23)
        self.assertEqual(item["folders"], ["ai_tools"])
        self.assertEqual(item["projects"], ["hermes_agent"])
        self.assertIn("primary route justified by agent, memory.", item["why"])

    def test_empty_and_sparse_week_returns_zero_counts_with_warnings_for_skipped_records(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty = digest.build_weekly_digest_input("2026-05-25", output_dir=Path(tmpdir))

            self.assertEqual(empty["digest_items"], [])
            self.assertEqual(empty["generated_from"]["source_files"], [])
            self.assertEqual(empty["summary"]["total_processed"], 0)
            self.assertEqual(empty["summary"]["by_folder"], {})
            self.assertEqual(empty["source_counts"]["bookmark_summary_runs"], 0)
            self.assertEqual(empty["warnings"], [])

            self.write_json(
                tmpdir,
                "bookmark_summary_20260531_090410.json",
                {
                    "total_processed": 1,
                    "insights": ["not-a-record"],
                    "action_items": [42],
                },
            )
            self.write_json(
                tmpdir,
                "opportunities/opportunity_router_2026-05-31.json",
                {"immediate_actions": ["bad-route"], "research_queue": [], "knowledge_promotions": []},
            )
            self.write_json(
                tmpdir,
                "opportunities/high_roi_tasks_2026-05-31.json",
                {"tasks": [None]},
            )
            self.write_json(
                tmpdir,
                "content_ideas/sparse.json",
                {"ideas": ["not-an-idea"]},
            )

            sparse = digest.build_weekly_digest_input("2026-05-25", output_dir=Path(tmpdir))

        self.assertEqual(sparse["digest_items"], [])
        self.assertEqual(sparse["summary"]["total_processed"], 1)
        self.assertEqual(sparse["source_counts"]["bookmark_summary_runs"], 1)
        self.assertEqual(sparse["source_counts"]["bookmark_insights"], 0)
        self.assertEqual(sparse["source_counts"]["action_items"], 0)
        self.assertEqual(sparse["source_counts"]["route_items"], 0)
        self.assertEqual(sparse["source_counts"]["task_items"], 0)
        self.assertEqual(sparse["source_counts"]["content_ideas"], 0)
        self.assertEqual(
            sparse["warnings"],
            [
                "skipped non-object action item in bookmark_summary_20260531_090410.json",
                "skipped non-object content idea in content_ideas/sparse.json",
                "skipped non-object insight in bookmark_summary_20260531_090410.json",
                "skipped non-object route item in opportunities/opportunity_router_2026-05-31.json#immediate_actions",
                "skipped non-object task item in opportunities/high_roi_tasks_2026-05-31.json",
            ],
        )

    def test_fixed_week_digest_input_matches_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = self.build_fixed_week_digest_payload(tmpdir)

        snapshot = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        self.assert_matches_snapshot(snapshot, "weekly_digest_input_fixed_week.json")
        self.assertEqual(payload["week"], {"week_start": "2026-05-25", "week_end": "2026-06-01"})
        self.assertEqual(payload["source_counts"]["bookmark_summary_runs"], 1)
        self.assertEqual(payload["source_counts"]["route_items"], 4)
        self.assertEqual([item["source_url"] for item in payload["digest_items"]], [
            "https://x.com/agent_builder/status/1",
            "https://x.com/router/status/9",
            "https://x.com/researcher/status/3",
            "https://x.com/solo_item/status/2",
        ])

    def test_fixed_week_rendered_digest_matches_snapshot_and_avoids_repetition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            payload = self.build_fixed_week_digest_payload(tmpdir)

        rendered = digest.render_weekly_digest_input(payload) + "\n"
        self.assert_matches_snapshot(rendered, "weekly_digest_fixed_week.txt")
        self.assertIn("Signals: action item, bookmark insight, content idea, learning note, immediate action, knowledge promotion, task", rendered)
        self.assertIn("Signals: project route", rendered)
        self.assertIn("Permission gates are durable agent architecture.", rendered)
        self.assertIn("Memory tooling belongs in the Hermes project lane.", rendered)
        self.assertEqual(rendered.count("Permission gates are durable agent architecture."), 1)
        self.assertLess(rendered.count("Permission"), 5)

    def test_rendered_weekly_digest_input_is_deterministic_readable_and_non_repetitive(self):
        payload = {
            "schema_version": "weekly-bookmark-digest-input/v1",
            "week": {"week_start": "2026-05-25", "week_end": "2026-06-01"},
            "summary": {
                "total_processed": 3,
                "by_folder": {"coding": 1, "ai_tools": 2},
                "edge_case_counts": {"missing_id": 1},
                "action_summary": {"ok": 2, "error": 1, "skipped": 0, "by_action": {"move": 2}},
            },
            "source_counts": {
                "bookmark_summary_runs": 1,
                "bookmark_insights": 2,
                "action_items": 1,
                "route_items": 2,
                "task_items": 1,
                "learning_notes": 1,
                "content_ideas": 1,
            },
            "digest_items": [
                {
                    "source_url": "https://x.com/agent_builder/status/1",
                    "authors": ["agent_builder"],
                    "folders": ["ai_tools"],
                    "projects": ["hermes_agent"],
                    "signals": [
                        "action_item",
                        "bookmark_insight",
                        "content_idea",
                        "learning_note",
                        "route:immediate_actions",
                        "route:knowledge_promotions",
                        "task",
                    ],
                    "top_score": 51,
                    "priority": 1,
                    "insights": ["Use permission gates before adding autonomous execution."],
                    "actions": [
                        "Add a checklist for approval-gated agent tasks.",
                        "Use permission gates before adding autonomous execution.",
                    ],
                    "why": ["Durable concept."],
                    "content_ideas": [
                        {
                            "hook": "Your agent should ask before it acts",
                            "angle": "Approval gates as product safety",
                            "audience": "agent operators",
                            "proof_point": "Same source appears in routes, tasks, and notes.",
                        }
                    ],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                },
                {
                    "source_url": "https://x.com/solo_item/status/2",
                    "authors": ["solo_item"],
                    "folders": [],
                    "projects": [],
                    "signals": ["bookmark_insight"],
                    "top_score": 0,
                    "priority": None,
                    "insights": ["Keep digest generation lightweight."],
                    "actions": [],
                    "why": [],
                    "content_ideas": [],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                },
            ],
            "warnings": [],
        }
        expected = """X BOOKMARK WEEKLY DIGEST
Week: 2026-05-25 to 2026-06-01

Summary
- Bookmarks processed: 3
- Categories: ai_tools (2), coding (1)
- Sources: summaries 1, insights 2, actions 1, routes 2, tasks 1, learning notes 1, content ideas 1
- Actions: ok 2, errors 1, skipped 0; move 2
- Edge cases: missing_id (1)

Top signals
1. @agent_builder — Use permission gates before adding autonomous execution.
   Action: Add a checklist for approval-gated agent tasks.
   Why it matters: Durable concept.
   Signals: action item, bookmark insight, content idea, learning note, immediate action, knowledge promotion, task
   Score: 51 | Folder: ai_tools | Project: hermes_agent
   Content idea: "Your agent should ask before it acts" for agent operators — Approval gates as product safety
   Source: https://x.com/agent_builder/status/1

2. @solo_item — Keep digest generation lightweight.
   Signals: bookmark insight
   Source: https://x.com/solo_item/status/2"""

        first = digest.render_weekly_digest_input(payload)
        second = digest.render_weekly_digest_input(payload)

        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(first.count("Use permission gates before adding autonomous execution."), 1)

    def test_rendered_weekly_digest_input_merges_duplicate_source_urls_before_displaying(self):
        payload = {
            "schema_version": "weekly-bookmark-digest-input/v1",
            "week": {"week_start": "2026-05-25", "week_end": "2026-06-01"},
            "summary": {"total_processed": 2, "by_folder": {"ai_tools": 2}},
            "source_counts": {"bookmark_summary_runs": 1, "route_items": 1, "task_items": 0, "learning_notes": 0, "content_ideas": 0},
            "digest_items": [
                {
                    "source_url": "https://x.com/agent_builder/status/1?utm_source=weekly",
                    "authors": ["agent_builder"],
                    "folders": ["ai_tools"],
                    "projects": [],
                    "signals": ["bookmark_insight"],
                    "top_score": 12,
                    "priority": None,
                    "insights": ["Use permission gates before adding autonomous execution."],
                    "actions": [],
                    "why": [],
                    "content_ideas": [],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                },
                {
                    "source_url": "https://x.com/agent_builder/status/1",
                    "authors": ["agent_builder"],
                    "folders": ["ai_tools"],
                    "projects": ["hermes_agent"],
                    "signals": ["route:project_routes"],
                    "top_score": 30,
                    "priority": 1,
                    "insights": ["Use permission gates before adding autonomous execution."],
                    "actions": ["Route this bookmark to Hermes follow-up."],
                    "why": ["Primary route justified by agent memory work."],
                    "content_ideas": [],
                    "source_files": ["opportunities/opportunity_router_2026-05-31.json"],
                },
            ],
            "warnings": [],
        }

        rendered = digest.render_weekly_digest_input(payload)

        self.assertEqual(rendered.count("https://x.com/agent_builder/status/1"), 1)
        self.assertIn("Signals: bookmark insight, project route", rendered)
        self.assertIn("Action: Route this bookmark to Hermes follow-up.", rendered)
        self.assertIn("Score: 30 | Folder: ai_tools | Project: hermes_agent", rendered)
        self.assertNotIn("2. @agent_builder", rendered)

    def test_rendered_weekly_digest_input_limits_long_weeks_and_summarizes_omitted_items(self):
        payload = {
            "schema_version": "weekly-bookmark-digest-input/v1",
            "week": {"week_start": "2026-05-25", "week_end": "2026-06-01"},
            "summary": {"total_processed": 20, "by_folder": {"ai_tools": 20}},
            "source_counts": {"bookmark_summary_runs": 1, "route_items": 0, "task_items": 0, "learning_notes": 0, "content_ideas": 0},
            "digest_items": [
                {
                    "id": f"item-{index}",
                    "source_url": f"https://x.com/source/status/{index}",
                    "authors": [f"source_{index}"],
                    "folders": ["ai_tools"],
                    "projects": [],
                    "signals": ["bookmark_insight"],
                    "top_score": 20 - index,
                    "priority": None,
                    "insights": [f"Insight {index}"],
                    "actions": [],
                    "why": [],
                    "content_ideas": [],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                }
                for index in range(13)
            ],
            "warnings": [],
        }

        rendered = digest.render_weekly_digest_input(payload)

        self.assertIn("Top signals (12 of 13)", rendered)
        self.assertIn("1. @source_0 — Insight 0", rendered)
        self.assertIn("12. @source_11 — Insight 11", rendered)
        self.assertNotIn("@source_12", rendered)
        self.assertIn("Additional signals not shown: 1 lower-priority item.", rendered)

    def test_rendered_weekly_digest_input_suppresses_repeated_why_phrasing(self):
        payload = {
            "schema_version": "weekly-bookmark-digest-input/v1",
            "week": {"week_start": "2026-05-25", "week_end": "2026-06-01"},
            "summary": {"total_processed": 2, "by_folder": {"ai_tools": 2}},
            "source_counts": {"bookmark_summary_runs": 1, "route_items": 0, "task_items": 0, "learning_notes": 0, "content_ideas": 0},
            "digest_items": [
                {
                    "id": "first",
                    "source_url": "https://x.com/first/status/1",
                    "authors": ["first"],
                    "folders": ["ai_tools"],
                    "projects": [],
                    "signals": ["bookmark_insight"],
                    "top_score": 2,
                    "priority": None,
                    "insights": ["First insight."],
                    "actions": [],
                    "why": ["Durable concept worth promoting into wiki/skills if still novel after dedupe."],
                    "content_ideas": [],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                },
                {
                    "id": "second",
                    "source_url": "https://x.com/second/status/2",
                    "authors": ["second"],
                    "folders": ["ai_tools"],
                    "projects": [],
                    "signals": ["bookmark_insight"],
                    "top_score": 1,
                    "priority": None,
                    "insights": ["Second insight."],
                    "actions": [],
                    "why": ["Durable concept worth promoting into wiki/skills if still novel after dedupe."],
                    "content_ideas": [],
                    "source_files": ["bookmark_summary_20260531_090410.json"],
                },
            ],
            "warnings": [],
        }

        rendered = digest.render_weekly_digest_input(payload)

        self.assertEqual(rendered.count("Why it matters: Durable concept worth promoting"), 1)
        self.assertIn("1. @first — First insight.", rendered)
        self.assertIn("2. @second — Second insight.", rendered)

    def test_no_argument_digest_generation_still_uses_latest_summary_shape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            self.write_json(
                tmpdir,
                "bookmark_summary_20260531_090410.json",
                {
                    "total_processed": 1,
                    "by_folder": {"ai_tools": 1},
                    "edge_case_counts": {"missing_id": 1},
                    "insights": [
                        {"author": "tester", "insight": "Keep legacy digest readable.", "url": "https://x.com/test/status/1"}
                    ],
                    "action_items": [
                        {"author": "tester", "action": "Keep wrapper output as text.", "url": "https://x.com/test/status/1"}
                    ],
                },
            )
            original_output_dir = digest.OUTPUT_DIR
            try:
                digest.OUTPUT_DIR = Path(tmpdir)
                rendered = digest.generate_digest()
            finally:
                digest.OUTPUT_DIR = original_output_dir

        self.assertIn("X BOOKMARK WEEKLY DIGEST", rendered)
        self.assertIn("Bookmarks Processed: 1", rendered)
        self.assertIn("@tester: Keep legacy digest readable.", rendered)
        self.assertIn("@tester: Keep wrapper output as text.", rendered)


if __name__ == "__main__":
    unittest.main()
