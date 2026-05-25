#!/usr/bin/env python3
"""Tests for anti-AI-slop review gate."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "social_voice_review.py"
spec = importlib.util.spec_from_file_location("social_voice_review", MODULE_PATH)
voice_review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice_review)


def test_human_reply_passes_voice_review():
    result = voice_review.review_social_copy(
        "Yep. The unsexy parts matter most.",
        platform="X",
        kind="reply",
    )

    assert result["status"] == "pass"
    assert result["blocking"] is False
    assert result["issues"] == []


def test_obvious_ai_slop_fails_voice_review():
    result = voice_review.review_social_copy(
        "Great point! Here's the thing: this game-changing framework unlocks value across the entire landscape. Thoughts? #AI #Automation #Leadership #Growth",
        platform="X",
        kind="reply",
    )

    assert result["status"] == "fail"
    assert result["blocking"] is True
    assert any(issue["code"] == "generic_reply_praise" for issue in result["issues"])
    assert any(issue["code"] == "ai_signposting" for issue in result["issues"])
    assert any(issue["code"] == "engagement_bait" for issue in result["issues"])


def test_tidy_numbered_framework_warns_but_does_not_block():
    result = voice_review.review_social_copy(
        "Three things I would check before blaming the model:\n1. The prompt\n2. The input data\n3. The eval",
        platform="X",
        kind="post",
    )

    assert result["status"] == "warn"
    assert result["blocking"] is False
    assert any(issue["code"] == "numbered_framework" for issue in result["issues"])
