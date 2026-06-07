#!/usr/bin/env python3
"""Tests for the local-first X bookmark metrics dashboard/report."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bookmark_metrics_dashboard as dashboard  # noqa: E402


class BookmarkMetricsDashboardTests(unittest.TestCase):
    def sample_metrics(self) -> dict:
        return {
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
                "route_skipped": {"deleted_or_low_value": 2, "unscored": 3},
                "warnings": ["2 bookmarks lacked enough project evidence"],
                "missing_optional_outputs": ["digest"],
            },
            "runs": [
                {"id": "run-20260603", "status": "completed", "processed": 12},
            ],
        }

    def test_dashboard_renders_the_exact_listed_metric_counts(self) -> None:
        html = dashboard.render_dashboard(self.sample_metrics(), source_name="metrics.json")

        self.assertIn("X Bookmark Metrics", html)
        self.assertIn("metrics.json", html)
        expected_rows = {
            "Processed": "12",
            "Deduped": "3",
            "Routed": "7",
            "Notes": "4",
            "Ideas": "2",
            "Digests": "1",
            "Cache hits": "5",
        }
        for label, count in expected_rows.items():
            self.assertIn(f"<th scope=\"row\">{label}</th>", html)
            self.assertIn(f"<td>{count}</td>", html)

    def test_dashboard_makes_failure_summary_and_partial_data_visible(self) -> None:
        metrics = self.sample_metrics()
        metrics["counts"].pop("idea")
        metrics["failure_summary"]["warnings"].append("cache metadata was unavailable")

        html = dashboard.render_dashboard(metrics, source_name="partial.json")

        self.assertIn("Missing metrics", html)
        self.assertIn("Ideas", html)
        self.assertIn("missing", html)
        self.assertIn("Failure summary", html)
        self.assertIn("attention_required", html)
        self.assertIn("action_errors", html)
        self.assertIn("route_skipped", html)
        self.assertIn("deleted_or_low_value", html)
        self.assertIn("missing_optional_outputs", html)
        self.assertIn("2 bookmarks lacked enough project evidence", html)
        self.assertIn("cache metadata was unavailable", html)

    def test_dashboard_renders_explicit_error_field_as_failure(self) -> None:
        metrics = self.sample_metrics()
        metrics["error"] = "analyzer crashed before digest generation"

        html = dashboard.render_dashboard(metrics, source_name="errored.json")

        self.assertIn("Failures", html)
        self.assertIn("analyzer crashed before digest generation", html)
        self.assertNotIn("No failures reported.", html)

    def test_dashboard_uses_only_canonical_counts_fields_not_aliases(self) -> None:
        metrics = self.sample_metrics()
        metrics["counts"] = {
            "processed_count": 99,
            "deduped_count": 98,
            "routed_count": 97,
            "note_count": 96,
            "idea_count": 95,
            "digest_count": 94,
            "cache_hits": 93,
        }

        html = dashboard.render_dashboard(metrics, source_name="alias-counts.json")

        self.assertIn("Metrics data degraded", html)
        self.assertIn("required count fields are missing or null", html)
        for count in ("99", "98", "97", "96", "95", "94", "93"):
            self.assertNotIn(f"<td>{count}</td>", html)
        for label in ("Processed", "Deduped", "Routed", "Notes", "Ideas", "Digests", "Cache hits"):
            self.assertIn(f"<th scope=\"row\">{label}</th><td>missing</td>", html)

    def test_dashboard_does_not_fall_back_to_run_counts_when_counts_object_is_absent(self) -> None:
        metrics = self.sample_metrics()
        metrics.pop("counts")
        metrics["runs"] = [{"id": "stale-run", "status": "completed", "counts": {"processed": 88}}]

        html = dashboard.render_dashboard(metrics, source_name="missing-counts.json")

        self.assertIn("Metrics data degraded", html)
        self.assertIn("counts object is missing", html)
        self.assertIn("Missing metrics", html)
        self.assertIn("<th scope=\"row\">Processed</th><td>missing</td>", html)
        self.assertNotIn("<th scope=\"row\">Processed</th><td>88</td>", html)
        self.assertNotIn("<td>0</td>", html)

    def test_dashboard_renders_degraded_state_for_null_counts_object(self) -> None:
        metrics = self.sample_metrics()
        metrics["counts"] = None

        html = dashboard.render_dashboard(metrics, source_name="null-counts-object.json")

        self.assertIn("Metrics data degraded", html)
        self.assertIn("counts object is null", html)
        self.assertNotIn("<td>0</td>", html)

    def test_dashboard_renders_degraded_state_for_null_counts_and_metric_values(self) -> None:
        metrics = self.sample_metrics()
        metrics["counts"] = {
            "processed": None,
            "deduped": 3,
            "routed": 7,
            "note": 4,
            "idea": 2,
            "digest": 1,
            "cache-hit": 5,
        }

        html = dashboard.render_dashboard(metrics, source_name="null-counts.json")

        self.assertIn("Metrics data degraded", html)
        self.assertIn("Processed", html)
        self.assertIn("missing", html)
        self.assertNotIn("<th scope=\"row\">Processed</th><td>0</td>", html)

    def test_dashboard_keeps_failure_summary_attention_visible_without_failure_entries(self) -> None:
        metrics = self.sample_metrics()
        metrics["failure_summary"] = {
            "status": "attention_required",
            "action_errors": 2,
            "route_skipped": {"unscored": 3},
            "warnings": [],
            "missing_optional_outputs": [],
        }

        html = dashboard.render_dashboard(metrics, source_name="summary-attention.json")

        self.assertIn("Failure indicators present", html)
        self.assertIn("attention_required", html)
        self.assertIn("action_errors", html)
        self.assertNotIn("No failures reported.", html)

    def test_dashboard_renders_zero_counts_as_zero_not_missing(self) -> None:
        metrics = self.sample_metrics()
        metrics["counts"] = {key: 0 for key in metrics["counts"]}

        html = dashboard.render_dashboard(metrics, source_name="zeroes.json")

        self.assertIn("All required metrics are present.", html)
        for label in ("Processed", "Deduped", "Routed", "Notes", "Ideas", "Digests", "Cache hits"):
            self.assertIn(f"<th scope=\"row\">{label}</th><td>0</td>", html)
        self.assertNotIn("Missing metrics", html)

    def test_cli_writes_error_report_for_unavailable_metrics_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            report_path = root / "dashboard.html"

            exit_code = dashboard.main([
                "--metrics",
                str(root / "missing_metrics.json"),
                "--output",
                str(report_path),
            ])

            self.assertEqual(exit_code, 2)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("Metrics unavailable", html)
            self.assertIn("missing_metrics.json", html)
            self.assertIn("Input file unavailable", html)
            self.assertIn("No counts were rendered from missing data.", html)

    def test_cli_writes_error_report_for_metrics_json_parse_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics_path = root / "bad_metrics.json"
            report_path = root / "dashboard.html"
            metrics_path.write_text("{not-json", encoding="utf-8")

            exit_code = dashboard.main([
                "--metrics",
                str(metrics_path),
                "--output",
                str(report_path),
            ])

            self.assertEqual(exit_code, 2)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("Metrics unavailable", html)
            self.assertIn("bad_metrics.json", html)
            self.assertIn("JSON parse error", html)
            self.assertIn("No counts were rendered from unreadable data.", html)

    def test_cli_reads_metrics_json_and_writes_a_local_html_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics_path = root / "bookmark_metrics.json"
            report_path = root / "dashboard.html"
            metrics_path.write_text(json.dumps(self.sample_metrics()), encoding="utf-8")

            exit_code = dashboard.main([
                "--metrics",
                str(metrics_path),
                "--output",
                str(report_path),
            ])

            self.assertEqual(exit_code, 0)
            html = report_path.read_text(encoding="utf-8")
            self.assertIn("X Bookmark Metrics", html)
            self.assertIn("run-20260603", html)
            self.assertIn("2 bookmarks lacked enough project evidence", html)


if __name__ == "__main__":
    unittest.main()
