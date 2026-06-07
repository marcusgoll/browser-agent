#!/usr/bin/env python3
"""Smoke tests for the bookmark reporting CLIs."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bookmark_metrics_dashboard as dashboard  # noqa: E402
import weekly_bookmark_digest as digest  # noqa: E402


class BookmarkReportingSmokeTests(unittest.TestCase):
    def seed_weekly_digest_inputs(self, root: Path) -> None:
        (root / "opportunities").mkdir(parents=True, exist_ok=True)
        (root / "content_ideas").mkdir(parents=True, exist_ok=True)
        (root / "learning_notes").mkdir(parents=True, exist_ok=True)

        (root / "bookmark_summary_20260531_090410.json").write_text(
            json.dumps(
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
                        }
                    ],
                    "action_items": [
                        {
                            "author": "agent_builder",
                            "action": "Add a checklist for approval-gated agent tasks.",
                            "url": "https://x.com/agent_builder/status/1",
                        }
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (root / "opportunities" / "opportunity_router_2026-05-31.json").write_text(
            json.dumps(
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
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (root / "content_ideas" / "permission-idea.json").write_text(
            json.dumps(
                {
                    "generated_on": "2026-05-31",
                    "source_url": "https://x.com/agent_builder/status/1",
                    "hook": "Your agent should ask before it acts",
                    "angle": "Approval gates as product safety",
                    "audience": "agent operators",
                    "proof_point": "Same source appears in routes, tasks, and notes.",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (root / "learning_notes" / "permission.md").write_text(
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

    def test_weekly_digest_cli_emits_deterministic_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.seed_weekly_digest_inputs(root)
            argv = [
                "weekly_bookmark_digest.py",
                "--week-start",
                "2026-05-25",
                "--output-dir",
                str(root),
                "--json",
            ]

            stdout = io.StringIO()
            with mock.patch.object(sys, "argv", argv):
                with redirect_stdout(stdout):
                    exit_code = digest.main()

            self.assertEqual(exit_code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["schema_version"], "weekly-bookmark-digest-input/v1")
            self.assertEqual(payload["week"], {"week_start": "2026-05-25", "week_end": "2026-06-01"})
            self.assertEqual(payload["source_counts"]["bookmark_summary_runs"], 1)
            self.assertGreaterEqual(payload["source_counts"]["route_items"], 1)
            self.assertTrue(payload["digest_items"])

    def test_metrics_dashboard_cli_writes_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics_path = root / "bookmark_metrics.json"
            report_path = root / "bookmark_metrics.html"
            metrics_path.write_text(
                json.dumps(
                    {
                        "schema_version": "bookmark-analyzer-metrics/v1",
                        "generated_at": "2026-06-03T12:30:00Z",
                        "counts": {
                            "processed": 12,
                            "deduped": 3,
                            "routed": 7,
                            "note": 4,
                            "idea": 2,
                            "digest": 1,
                            "cache-hit": 5,
                        },
                        "failure_summary": {
                            "status": "attention_required",
                            "action_errors": 1,
                            "route_skipped": {"deleted_or_low_value": 2},
                            "warnings": ["2 bookmarks lacked enough project evidence"],
                            "missing_optional_outputs": ["digest"],
                        },
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            exit_code = dashboard.main(["--metrics", str(metrics_path), "--output", str(report_path)])

            self.assertEqual(exit_code, 0)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("X Bookmark Metrics", html)
            self.assertIn("Processed", html)
            self.assertIn("12", html)
            self.assertIn("attention_required", html)
            self.assertIn("2 bookmarks lacked enough project evidence", html)


if __name__ == "__main__":
    unittest.main()
