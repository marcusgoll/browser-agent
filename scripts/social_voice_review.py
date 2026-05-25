#!/usr/bin/env python3
"""Deterministic anti-AI-slop review for Marcus social copy.

No LLM calls. No rewriting. This is a preflight lint gate for approval and
publishing workflows.
"""
from __future__ import annotations

import re
from typing import Any

Issue = dict[str, Any]

FAIL_PATTERNS: list[tuple[str, str, str]] = [
    ("generic_reply_praise", r"\b(great|excellent|amazing|fantastic)\s+(point|question|insight|take)\b", "Generic praise reads like a bot reply."),
    ("engagement_bait", r"(?:\bagree\?|\bthoughts\?|\bcomment\s+\w+|\bdrop\s+.*\bbelow)", "Engagement bait makes the post feel manufactured."),
    ("ai_signposting", r"\b(here'?s the thing|let'?s dive in|let'?s explore|here'?s what you need to know|let'?s break this down)\b", "AI-style signposting announces instead of speaking naturally."),
    ("hype_language", r"\b(game[- ]?changing|unlock(?:s|ed|ing)?|leverage|seamless|cutting[- ]edge|revolutionary|transformative)\b", "Hype language sounds like generic AI marketing copy."),
    ("announcement_cliche", r"\b(thrilled|excited)\s+to\s+announce\b", "Announcement cliche sounds corporate and templated."),
    ("guru_cadence", r"\b(the real question is|at its core|what really matters|the deeper issue|the heart of the matter)\b", "Guru framing feels synthetic."),
]

WARN_PATTERNS: list[tuple[str, str, str]] = [
    ("numbered_framework", r"(?m)^\s*(?:\d+\.|[-*])\s+\S+", "Structured list/framework may be too tidy for X unless the context needs it."),
    ("hook_lesson_cta_shape", r"(?is)\b(lesson|takeaway)\b.*\b(try this|save this|follow for|share this)\b", "Hook/lesson/CTA shape can feel generated."),
    ("abstract_landscape", r"\b(landscape|ecosystem|pivotal|crucial|vital|underscores?|highlights?)\b", "Abstract AI vocabulary weakens the voice."),
]

MAX_HASHTAGS = 2
MAX_WARNINGS_BEFORE_FAIL = 3


def _issue(code: str, severity: str, message: str, match: str | None = None) -> Issue:
    issue: Issue = {"code": code, "severity": severity, "message": message}
    if match:
        issue["match"] = match[:80]
    return issue


def _pattern_issues(text: str, patterns: list[tuple[str, str, str]], severity: str) -> list[Issue]:
    issues: list[Issue] = []
    for code, pattern, message in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            issues.append(_issue(code, severity, message, match.group(0)))
    return issues


def review_social_copy(copy: str, *, platform: str = "Unknown", kind: str = "post") -> dict[str, Any]:
    """Return pass/warn/fail for exact social copy.

    fail means do not send for approval and do not publish.
    warn means surface the concern on the approval card but do not block.
    """
    text = (copy or "").strip()
    if not text:
        return {
            "status": "fail",
            "blocking": True,
            "issues": [_issue("empty_copy", "fail", "No exact copy found for voice review.")],
        }

    issues = _pattern_issues(text, FAIL_PATTERNS, "fail")
    warnings = _pattern_issues(text, WARN_PATTERNS, "warn")

    hashtags = re.findall(r"(?<!\w)#\w+", text)
    if len(hashtags) > MAX_HASHTAGS:
        issues.append(_issue("hashtag_stuffing", "fail", "Too many hashtags for Marcus's default voice.", " ".join(hashtags)))

    # Replies should usually be lighter than posts. A multi-bullet reply is a red flag.
    if kind == "reply" and len(re.findall(r"(?m)^\s*(?:\d+\.|[-*])\s+\S+", text)) >= 2:
        issues.append(_issue("over_structured_reply", "fail", "Reply is too structured; use a normal human response."))

    all_issues = issues + warnings
    fail_count = len(issues)
    if fail_count:
        status = "fail"
    elif len(warnings) >= MAX_WARNINGS_BEFORE_FAIL:
        status = "fail"
        all_issues.append(_issue("too_many_voice_warnings", "fail", "Too many voice warnings in one item."))
    elif warnings:
        status = "warn"
    else:
        status = "pass"

    return {
        "status": status,
        "blocking": status == "fail",
        "platform": platform,
        "kind": kind,
        "issues": all_issues,
    }


def format_review_for_card(review: dict[str, Any]) -> str:
    status = str(review.get("status") or "unknown").upper()
    issues = review.get("issues") or []
    if not issues:
        return f"Voice review: {status}"
    lines = [f"Voice review: {status}"]
    for issue in issues[:4]:
        lines.append(f"- {issue.get('code')}: {issue.get('message')}")
    if len(issues) > 4:
        lines.append(f"- plus {len(issues) - 4} more")
    return "\n".join(lines)
