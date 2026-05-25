#!/usr/bin/env python3
"""Tests for visible-state account context preflight."""
import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "account_context.py"
spec = importlib.util.spec_from_file_location("account_context", MODULE_PATH)
account_context = importlib.util.module_from_spec(spec)
spec.loader.exec_module(account_context)


def test_preflight_allows_matching_x_context():
    context = {
        "platform": "x",
        "url": "https://x.com/home",
        "handle": "marcusgoll",
        "authenticated": True,
    }
    expected = {"allowed_domains": ["x.com"], "expected_handle": "@marcusgoll"}
    result = account_context.validate_preflight(context, expected, "approved_write")
    assert result["ok"] is True
    assert result["reason"] == "context_ok"


def test_preflight_blocks_account_mismatch():
    context = {
        "platform": "x",
        "url": "https://x.com/home",
        "handle": "wrongaccount",
        "authenticated": True,
    }
    expected = {"allowed_domains": ["x.com"], "expected_handle": "marcusgoll"}
    result = account_context.validate_preflight(context, expected, "approved_write")
    assert result["ok"] is False
    assert result["reason"] == "account_mismatch"


def test_preflight_blocks_ambiguous_write_context():
    context = {
        "platform": "linkedin",
        "url": "https://www.linkedin.com/feed/",
        "authenticated": True,
    }
    expected = {"allowed_domains": ["www.linkedin.com"], "expected_account_name": "Marcus Gollahon"}
    result = account_context.validate_preflight(context, expected, "approved_write")
    assert result["ok"] is False
    assert result["reason"] == "account_ambiguous"


def test_preflight_blocks_domain_mismatch():
    context = {
        "platform": "x",
        "url": "https://evil.example/home",
        "handle": "marcusgoll",
        "authenticated": True,
    }
    expected = {"allowed_domains": ["x.com"]}
    result = account_context.validate_preflight(context, expected, "approved_write")
    assert result["ok"] is False
    assert result["reason"] == "domain_mismatch"


def test_extract_handle_from_visible_text():
    assert account_context.extract_handle_from_visible_text("Marcus\n@marcusgoll\nProfile") == "marcusgoll"


def test_x_publish_preflight_result_shape_blocks_mismatch():
    result = account_context.publisher_preflight_result(
        platform="x",
        url="https://x.com/home",
        authenticated=True,
        visible_text="Profile @wrongaccount",
        expected_handle="marcusgoll",
        allowed_domains=["x.com"],
        action_type="approved_write",
    )
    assert result["ok"] is False
    assert result["reason"] == "account_mismatch"
    assert result["context"]["handle"] == "wrongaccount"


def test_linkedin_publish_preflight_result_shape_blocks_ambiguous_context():
    result = account_context.publisher_preflight_result(
        platform="linkedin",
        url="https://www.linkedin.com/feed/",
        authenticated=True,
        visible_text="Home My Network Start a post",
        expected_account_name="Marcus Gollahon",
        allowed_domains=["www.linkedin.com"],
        action_type="approved_write",
    )
    assert result["ok"] is False
    assert result["reason"] == "account_ambiguous"


def test_linkedin_publish_preflight_inferrs_expected_name_from_visible_text():
    result = account_context.publisher_preflight_result(
        platform="linkedin",
        url="https://www.linkedin.com/feed/",
        authenticated=True,
        visible_text="Home My Network Marcus Gollahon Start a post",
        expected_account_name="Marcus Gollahon",
        allowed_domains=["www.linkedin.com"],
        action_type="approved_write",
    )
    assert result["ok"] is True
    assert result["reason"] == "context_ok"
    assert result["context"]["account_name"] == "Marcus Gollahon"
