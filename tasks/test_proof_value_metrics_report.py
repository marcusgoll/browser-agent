#!/usr/bin/env python3
"""Tests for the local-first proof-of-value metrics report page."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import proof_value_metrics_report as report  # noqa: E402


class ProofValueMetricsReportTests(unittest.TestCase):
    def sample_metrics(self) -> dict[str, object]:
        return {
            "schema_version": "proof-of-value-metrics/v1",
            "generated_at": "2026-06-03T21:30:00",
            "source": "x_bookmark_analysis",
            "counts": {
                "processed": 5,
                "deduped": 1,
                "routed": 3,
                "note": 2,
                "idea": 2,
                "digest": 0,
                "cache-hit": 2,
            },
        }

    def test_report_renders_each_required_count_from_metrics_json(self) -> None:
        html = report.render_report(self.sample_metrics(), source_name="proof_value_metrics_2026-06-03.json")

        self.assertIn("Proof-of-Value Metrics", html)
        self.assertIn("proof_value_metrics_2026-06-03.json", html)
        expected_counts = {
            "Processed": "5",
            "Deduped": "1",
            "Routed": "3",
            "Notes": "2",
            "Ideas": "2",
            "Digest": "0",
            "Cache hits": "2",
        }
        for label, count in expected_counts.items():
            self.assertIn(f"<dt>{label}</dt>", html)
            self.assertIn(f"<dd>{count}</dd>", html)
        self.assertIn("All expected metrics are present.", html)

    def test_report_shows_missing_expected_fields_without_filling_zeroes(self) -> None:
        metrics = self.sample_metrics()
        counts = dict(cast(dict[str, int], metrics["counts"]))
        counts.pop("idea")
        metrics["counts"] = counts

        html = report.render_report(metrics, source_name="partial.json")

        self.assertIn("Report needs attention", html)
        self.assertIn("Missing expected metrics", html)
        self.assertIn("Ideas", html)
        self.assertIn("<dd>missing</dd>", html)
        self.assertIn("<dt>Digest</dt>", html)
        self.assertIn("<dd>0</dd>", html)

    def test_report_marks_present_null_required_count_as_attention_needed(self) -> None:
        metrics = self.sample_metrics()
        counts = dict(cast(dict[str, int | None], metrics["counts"]))
        counts["idea"] = None
        metrics["counts"] = counts

        html = report.render_report(metrics, source_name="null-count.json")

        self.assertIn("Report needs attention", html)
        self.assertNotIn("All expected metrics are present.", html)
        self.assertIn("Missing expected metric: Ideas", html)
        self.assertIn("<dt>Ideas</dt>", html)
        self.assertIn("<dd>missing</dd>", html)

    def test_report_marks_non_integer_and_negative_required_counts_as_invalid(self) -> None:
        invalid_values: tuple[object, ...] = ("2", True, -1)
        for value in invalid_values:
            with self.subTest(value=value):
                metrics = self.sample_metrics()
                counts = dict(cast(dict[str, object], metrics["counts"]))
                counts["idea"] = value
                metrics["counts"] = counts

                html = report.render_report(metrics, source_name="invalid-count.json")

                self.assertIn("Report needs attention", html)
                self.assertNotIn("All expected metrics are present.", html)
                self.assertIn("Invalid expected metric: Ideas", html)
                self.assertIn("<dt>Ideas</dt>", html)
                self.assertIn("<dd>invalid</dd>", html)

    def test_write_report_reads_metrics_json_and_writes_local_html(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics_path = root / "proof_value_metrics_2026-06-03.json"
            output_path = root / "proof_value_metrics_2026-06-03.html"
            metrics_path.write_text(json.dumps(self.sample_metrics()), encoding="utf-8")

            result = report.write_report(metrics_path, output_path)

            self.assertTrue(result.ok)
            html = output_path.read_text(encoding="utf-8")
            self.assertIn("Proof-of-Value Metrics", html)
            self.assertIn("<dt>Cache hits</dt>", html)
            self.assertIn("<dd>2</dd>", html)

    def test_missing_metrics_json_writes_visible_failure_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            output_path = root / "proof_value_metrics_report.html"

            result = report.write_report(root / "missing.json", output_path)

            self.assertFalse(result.ok)
            self.assertIn("missing metrics JSON", result.message)
            html = output_path.read_text(encoding="utf-8")
            self.assertIn("Report needs attention", html)
            self.assertIn("Missing metrics JSON", html)
            self.assertIn("missing.json", html)

    def test_invalid_metrics_json_writes_visible_failure_page(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            metrics_path = root / "proof_value_metrics_2026-06-03.json"
            output_path = root / "proof_value_metrics_2026-06-03.html"
            metrics_path.write_text("{not-json", encoding="utf-8")

            result = report.write_report(metrics_path, output_path)

            self.assertFalse(result.ok)
            self.assertIn("invalid metrics JSON", result.message)
            html = output_path.read_text(encoding="utf-8")
            self.assertIn("Report needs attention", html)
            self.assertIn("Invalid metrics JSON", html)
            self.assertIn("proof_value_metrics_2026-06-03.json", html)


if __name__ == "__main__":
    unittest.main()
