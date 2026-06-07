#!/usr/bin/env python3
"""Tests for deterministic design/taste review gate."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "design_review_gate.py"
spec = importlib.util.spec_from_file_location("design_review_gate", MODULE_PATH)
assert spec and spec.loader
review_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review_gate)


def test_concrete_ui_copy_passes_review():
    result = review_gate.review_design_artifact(
        "Primary CTA sits below the pricing table and the warning badge shows one issue.",
        artifact_type="ui",
    )

    assert result["status"] == "pass"
    assert result["blocking"] is False
    assert result["issues"] == []


def test_generic_taste_language_warns():
    result = review_gate.review_design_artifact(
        "Clean, modern, intuitive dashboard experience.",
        artifact_type="ui",
    )

    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert any(issue["code"] == "vague_design_claim" for issue in result["issues"])


def test_hype_language_fails_review():
    result = review_gate.review_design_artifact(
        "An AI-powered, revolutionary, seamless experience that unlocks the full ecosystem.",
        artifact_type="ui",
    )

    assert result["status"] == "fail"
    assert result["blocking"] is True
    assert any(issue["code"] == "hype_language" for issue in result["issues"])


def test_secret_like_screenshot_metadata_is_rejected():
    result = review_gate.review_design_artifact(
        artifact_type="screenshot",
        screenshot_meta={"source": "secret-token-screenshot.png", "description": "homepage screenshot"},
    )

    assert result["status"] == "fail"
    assert result["blocking"] is True
    assert any(issue["code"] == "secret_like_screenshot_source" for issue in result["issues"])
