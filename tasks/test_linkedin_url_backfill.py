#!/usr/bin/env python3
"""Tests for read-only LinkedIn public URL backfill helpers."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backfill_linkedin_url.py"
spec = importlib.util.spec_from_file_location("backfill_linkedin_url", MODULE_PATH)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)


def test_snippet_extraction_ignores_packet_metadata(tmp_path):
    packet = tmp_path / "LinkedIn-02.linkedin.md"
    packet.write_text(
        "# LinkedIn-02\n\n"
        "Status: approved\n\n"
        "Item ID: LinkedIn-02\n"
        "Platform: LinkedIn\n\n"
        "## Exact content\n"
        "One thing aviation teaches well: repeatability matters more than confidence.\n\n"
        "A student can feel confident and still have a weak process.\n\n"
        "## Links / media / assets\n"
        "none\n",
        encoding="utf-8",
    )

    snippet = backfill.extract_packet_snippet(packet, max_chars=80)

    assert snippet.startswith("One thing aviation teaches well")
    assert "platform:" not in snippet
    assert "kind:" not in snippet


def test_select_unique_activity_url_requires_single_match():
    snippet = "repeatability matters more than confidence"
    candidates = [
        {
            "text": "One thing aviation teaches well: repeatability matters more than confidence.",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:123456/",
        },
        {
            "text": "Unrelated post",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:999999/",
        },
    ]

    result = backfill.select_unique_activity_url(snippet, candidates)

    assert result["ok"] is True
    assert result["published_url"] == "https://www.linkedin.com/feed/update/urn:li:activity:123456/"


def test_select_unique_activity_url_matches_truncated_visible_feed_card():
    snippet = "One thing aviation teaches well: repeatability matters more than confidence. A student can feel confident and still have a weak process. A CFI can be experienced and still leave too much of the lesson in their head."
    candidates = [
        {
            "text": "Marcus Gollahon One thing aviation teaches well: repeatability matters more than confidence. A student can feel confident and still have a weak process. A CFI can... more",
            "url": "https://www.linkedin.com/feed/update/urn:li:activity:123456/",
        }
    ]

    result = backfill.select_unique_activity_url(snippet, candidates)

    assert result["ok"] is True
    assert result["published_url"] == "https://www.linkedin.com/feed/update/urn:li:activity:123456/"


def test_classify_lookup_page_blocks_login_or_join_surface():
    result = backfill.classify_lookup_page(
        "https://www.linkedin.com/signup",
        "Join LinkedIn Email Password Agree & Join Already on LinkedIn? Sign in",
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["reason"] == "linkedin_not_authenticated"


def test_select_unique_activity_url_blocks_zero_or_multiple_matches():
    assert backfill.select_unique_activity_url("missing", [])["status"] == "blocked"

    result = backfill.select_unique_activity_url(
        "same snippet",
        [
            {"text": "same snippet here", "url": "https://www.linkedin.com/feed/update/urn:li:activity:1/"},
            {"text": "same snippet there", "url": "https://www.linkedin.com/feed/update/urn:li:activity:2/"},
        ],
    )

    assert result["ok"] is False
    assert result["status"] == "blocked"
    assert result["reason"] == "multiple_matching_linkedin_posts"
