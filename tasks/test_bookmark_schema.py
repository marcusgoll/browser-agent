#!/usr/bin/env python3
"""Validation tests for the canonical bookmark artifact schema."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import bookmark_schema as schema  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


class BookmarkSchemaTests(unittest.TestCase):
    def load_fixture(self, name):
        with open(FIXTURES / name, encoding="utf-8") as fixture:
            return json.load(fixture)

    def test_analysis_legacy_output_wraps_into_explicit_v1_artifact(self):
        legacy_analysis = self.load_fixture("bookmark_analysis_legacy.json")

        artifact = schema.wrap_legacy_analysis(legacy_analysis, generated_at="2026-05-31T09:04:10")

        self.assertEqual(artifact["schema_version"], schema.CURRENT_SCHEMA_VERSION)
        self.assertEqual(artifact["artifact_type"], "bookmark_analysis")
        self.assertEqual(artifact["generated_at"], "2026-05-31T09:04:10")
        self.assertEqual(artifact["data"], legacy_analysis)
        self.assertEqual(artifact["metadata"]["record_count"], len(legacy_analysis))
        self.assertEqual(schema.unwrap_analysis(artifact), legacy_analysis)
        schema.validate_artifact(artifact)

    def test_summary_legacy_output_wraps_into_explicit_v1_artifact(self):
        legacy_summary = self.load_fixture("bookmark_summary_legacy.json")

        artifact = schema.wrap_legacy_summary(legacy_summary, generated_at="2026-05-31T09:04:10")

        self.assertEqual(artifact["schema_version"], schema.CURRENT_SCHEMA_VERSION)
        self.assertEqual(artifact["artifact_type"], "bookmark_summary")
        self.assertEqual(artifact["data"], legacy_summary)
        self.assertEqual(artifact["metadata"]["record_count"], legacy_summary["total_processed"])
        self.assertEqual(schema.unwrap_summary(artifact), legacy_summary)
        schema.validate_artifact(artifact)

    def test_legacy_analysis_and_summary_still_unwrap_without_version_header(self):
        legacy_analysis = self.load_fixture("bookmark_analysis_legacy.json")
        legacy_summary = self.load_fixture("bookmark_summary_legacy.json")

        self.assertEqual(schema.unwrap_analysis(legacy_analysis), legacy_analysis)
        self.assertEqual(schema.unwrap_summary(legacy_summary), legacy_summary)

    def test_validation_rejects_unknown_schema_version_or_shape(self):
        valid = schema.wrap_legacy_summary(self.load_fixture("bookmark_summary_legacy.json"))
        invalid_version = {**valid, "schema_version": "bookmark-artifact/v999"}
        missing_data = {key: value for key, value in valid.items() if key != "data"}

        with self.assertRaisesRegex(schema.BookmarkSchemaError, "unsupported schema_version"):
            schema.validate_artifact(invalid_version)
        with self.assertRaisesRegex(schema.BookmarkSchemaError, "missing required fields"):
            schema.validate_artifact(missing_data)

    def test_combined_artifact_round_trips_current_summary_and_analysis_outputs(self):
        legacy_summary = self.load_fixture("bookmark_summary_legacy.json")
        legacy_analysis = self.load_fixture("bookmark_analysis_legacy.json")

        artifact = schema.build_bookmark_run_artifact(
            summary=legacy_summary,
            analysis=legacy_analysis,
            generated_at="2026-05-31T09:04:10",
        )

        self.assertEqual(artifact["schema_version"], schema.CURRENT_SCHEMA_VERSION)
        self.assertEqual(artifact["artifact_type"], "bookmark_run")
        self.assertEqual(artifact["data"]["summary"], legacy_summary)
        self.assertEqual(artifact["data"]["analysis"], legacy_analysis)
        self.assertEqual(artifact["metadata"], {"record_count": 2, "summary_total_processed": 2})
        schema.validate_artifact(artifact)
        self.assertEqual(schema.unwrap_summary(artifact), legacy_summary)
        self.assertEqual(schema.unwrap_analysis(artifact), legacy_analysis)


if __name__ == "__main__":
    unittest.main()
