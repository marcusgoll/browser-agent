#!/usr/bin/env python3
"""Visible-state account/context preflight policy for browser-agent workflows.

This module only handles data extracted from visible page state. It must not read
cookies, tokens, browser storage, saved passwords, or browser profile databases.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


def normalize_handle(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip().lstrip("@").lower()
    return text if re.fullmatch(r"[a-z0-9_]{1,15}", text) else None


def normalize_name(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip().lower() or None


def extract_handle_from_visible_text(text: str) -> str | None:
    match = re.search(r"@([A-Za-z0-9_]{1,15})", text or "")
    return normalize_handle(match.group(1)) if match else None


def domain_matches(url: str, allowed_domains: list[str]) -> bool:
    if not allowed_domains:
        return True
    host = (urlparse(url or "").hostname or "").lower()
    for domain in allowed_domains:
        wanted = domain.lower().lstrip(".")
        if host == wanted or host.endswith(f".{wanted}"):
            return True
    return False


def build_context(
    *,
    platform: str,
    url: str,
    authenticated: bool,
    visible_text: str = "",
    handle: str | None = None,
    account_name: str | None = None,
) -> dict[str, Any]:
    extracted_handle = normalize_handle(handle) or extract_handle_from_visible_text(visible_text)
    return {
        "platform": platform,
        "url": url,
        "authenticated": bool(authenticated),
        "handle": extracted_handle,
        "account_name": account_name,
    }


def validate_preflight(context: dict[str, Any], expected: dict[str, Any] | None, action_type: str) -> dict[str, Any]:
    expected = expected or {}
    result = {
        "ok": False,
        "reason": "account_ambiguous",
        "action_type": action_type,
        "context": context,
        "expected": {
            key: value for key, value in expected.items() if key in {"allowed_domains", "expected_handle", "expected_account_name"}
        },
    }

    if not context.get("authenticated"):
        result["reason"] = "not_authenticated"
        return result

    if not domain_matches(context.get("url", ""), list(expected.get("allowed_domains") or [])):
        result["reason"] = "domain_mismatch"
        return result

    expected_handle = normalize_handle(expected.get("expected_handle"))
    if expected_handle:
        actual_handle = normalize_handle(context.get("handle"))
        if not actual_handle:
            result["reason"] = "account_ambiguous"
            return result
        if actual_handle != expected_handle:
            result["reason"] = "account_mismatch"
            return result

    expected_account_name = normalize_name(expected.get("expected_account_name"))
    if expected_account_name:
        actual_name = normalize_name(context.get("account_name"))
        if not actual_name:
            result["reason"] = "account_ambiguous"
            return result
        if actual_name != expected_account_name:
            result["reason"] = "account_mismatch"
            return result

    if action_type == "approved_write" and not (expected_handle or expected_account_name):
        # Writes need an explicit account expectation unless a platform-specific
        # caller has already populated a matching account identifier.
        if not (context.get("handle") or context.get("account_name")):
            result["reason"] = "account_ambiguous"
            return result

    result["ok"] = True
    result["reason"] = "context_ok"
    return result


def publisher_preflight_result(
    *,
    platform: str,
    url: str,
    authenticated: bool,
    visible_text: str = "",
    handle: str | None = None,
    account_name: str | None = None,
    expected_handle: str | None = None,
    expected_account_name: str | None = None,
    allowed_domains: list[str] | None = None,
    action_type: str = "approved_write",
) -> dict[str, Any]:
    inferred_account_name = account_name
    normalized_expected_name = normalize_name(expected_account_name)
    if not inferred_account_name and normalized_expected_name:
        normalized_visible_text = normalize_name(visible_text) or ""
        if normalized_expected_name in normalized_visible_text:
            inferred_account_name = expected_account_name
    context = build_context(
        platform=platform,
        url=url,
        authenticated=authenticated,
        visible_text=visible_text,
        handle=handle,
        account_name=inferred_account_name,
    )
    expected = {
        "expected_handle": expected_handle,
        "expected_account_name": expected_account_name,
        "allowed_domains": allowed_domains or [],
    }
    return validate_preflight(context, expected, action_type)
