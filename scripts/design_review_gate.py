#!/usr/bin/env python3
"""Deterministic design/taste review gate for browser-agent artifacts.

No LLM calls. No rewrites. This is a preflight lint gate for UI copy and
screenshot metadata.
"""
from __future__ import annotations

import re
from typing import Any

Issue = dict[str, Any]

FAIL_PATTERNS: list[tuple[str, str, str]] = [
    ("ai_signposting", r"\b(we('?| )?ll|let('?| )?s)\s+(dive in|explore|unpack|build|review)\b", "AI-style signposting reads like generated narration."),
    ("hype_language", r"\b(game[- ]?changing|revolutionary|transformative|seamless|world[- ]class|unmatched|next[- ]level|AI[- ]powered)\b", "Hype language weakens the design critique."),
    ("engagement_bait", r"\b(what do you think|thoughts\?|agree\?|drop .* below)\b", "Engagement bait is not a design review."),
]

WARN_PATTERNS: list[tuple[str, str, str]] = [
    ("listicle_shape", r"(?m)^\s*(?:\d+\.|[-*])\s+\S+", "Structured list copy may be too tidy for a taste review."),
    ("abstract_vocabulary", r"\b(landscape|ecosystem|journey|experience|momentum|synergy|vision)\b", "Abstract vocabulary can hide weak design specificity."),
    ("vague_design_claim", r"\b(clean|modern|sleek|premium|elegant|intuitive|beautiful)\b", "Vague design praise does not describe the artifact."),
]

SECRET_PATTERNS: list[tuple[str, str]] = [
    ("secret", r"\bsecret\b"),
    ("token", r"\btoken\b"),
    ("cookie", r"\bcookie\b"),
    ("password", r"\bpassword\b"),
    ("bearer", r"\bbearer\s+token\b"),
    ("api_key", r"\bapi[-_ ]?key\b"),
]

MAX_WARNINGS_BEFORE_FAIL = 3


def _issue(code: str, severity: str, message: str, match: str | None = None) -> Issue:
    issue: Issue = {"code": code, "severity": severity, "message": message}
    if match:
        issue["match"] = match[:120]
    return issue


def _pattern_issues(text: str, patterns: list[tuple[str, str, str]], severity: str) -> list[Issue]:
    issues: list[Issue] = []
    for code, pattern, message in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            issues.append(_issue(code, severity, message, match.group(0)))
    return issues


def _secret_issues(text: str) -> list[Issue]:
    issues: list[Issue] = []
    for code, pattern in SECRET_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            issues.append(_issue(f"secret_like_{code}", "fail", "Secret-like text is not allowed in design review input.", match.group(0)))
    return issues


def review_design_artifact(
    copy: str | None = None,
    *,
    screenshot_meta: dict[str, Any] | None = None,
    artifact_type: str = "ui",
) -> dict[str, Any]:
    """Return pass/warn/fail for UI copy or screenshot metadata."""
    meta = screenshot_meta or {}
    text = (copy or meta.get("description") or meta.get("alt") or meta.get("caption") or "").strip()

    if not text and not meta:
        return {
            "status": "fail",
            "blocking": True,
            "artifact_type": artifact_type,
            "issues": [_issue("empty_input", "fail", "No artifact text or screenshot metadata was provided.")],
        }

    issues = _secret_issues(text)
    warnings = _pattern_issues(text, WARN_PATTERNS, "warn")
    fails = _pattern_issues(text, FAIL_PATTERNS, "fail")

    if artifact_type.lower() in {"screenshot", "visual", "image"} and not any(meta.get(key) for key in ("description", "alt", "caption", "source")):
        fails.append(_issue("ambiguous_screenshot_reference", "fail", "Screenshot review needs a concrete description or source reference."))

    if meta.get("source") and isinstance(meta.get("source"), str):
        source_text = meta.get("source") or ""
        if re.search(r"\b(secret|token|cookie|password|bearer)\b", source_text, flags=re.IGNORECASE):
            issues.append(_issue("secret_like_screenshot_source", "fail", "Secret-like screenshot source references are rejected.", source_text))

    all_issues = issues + fails + warnings
    fail_count = len(issues) + len(fails)
    if fail_count:
        status = "fail"
    elif len(warnings) >= MAX_WARNINGS_BEFORE_FAIL:
        status = "fail"
        all_issues.append(_issue("too_many_review_warnings", "fail", "Too many design warnings in one review."))
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "blocking": status == "fail",
        "artifact_type": artifact_type,
        "text": text,
        "screenshot_meta": meta,
        "issues": all_issues,
    }


def format_review_for_card(review: dict[str, Any]) -> str:
    status = str(review.get("status") or "unknown").upper()
    issues = review.get("issues") or []
    if not issues:
        return f"Design review: {status}"
    lines = [f"Design review: {status}"]
    for issue in issues[:4]:
        lines.append(f"- {issue.get('code')}: {issue.get('message')}")
    if len(issues) > 4:
        lines.append(f"- plus {len(issues) - 4} more")
    return "\n".join(lines)
