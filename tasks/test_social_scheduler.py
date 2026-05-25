#!/usr/bin/env python3
"""Tests for social approved publish scheduler safety gates."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path("/home/orchestrator/.hermes/scripts/social-approved-publish-due.py")
if not MODULE_PATH.exists():
    pytest.skip(
        f"host Hermes script not mounted in canonical container: {MODULE_PATH}",
        allow_module_level=True,
    )
spec = importlib.util.spec_from_file_location("social_approved_publish_due", MODULE_PATH)
scheduler = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = scheduler
spec.loader.exec_module(scheduler)

DISPATCHER_MODULE_PATH = Path("/home/orchestrator/.hermes/scripts/social-approval-next-card.py")
dispatcher_spec = importlib.util.spec_from_file_location("social_approval_next_card", DISPATCHER_MODULE_PATH)
approval_dispatcher = importlib.util.module_from_spec(dispatcher_spec)
sys.modules[dispatcher_spec.name] = approval_dispatcher
dispatcher_spec.loader.exec_module(approval_dispatcher)


def test_slots_for_uses_valid_metrics_recommendations(monkeypatch, tmp_path):
    recs = tmp_path / "scheduling-recommendations.json"
    recs.write_text(
        json.dumps(
            {
                "version": 1,
                "usable": True,
                "timezone": "America/Chicago",
                "generated_at": "2026-05-25T00:00:00+00:00",
                "slots": {"X": {"post": ["10:05", "14:15"], "reply": ["18:10"]}},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "SCHEDULING_RECOMMENDATIONS", recs)

    assert [slot.strftime("%H:%M") for slot in scheduler.slots_for("X", "post")] == ["10:05", "14:15"]
    assert [slot.strftime("%H:%M") for slot in scheduler.slots_for("X", "reply")] == ["18:10"]


def test_slots_for_falls_back_when_recommendations_low_confidence(monkeypatch, tmp_path):
    recs = tmp_path / "scheduling-recommendations.json"
    recs.write_text(json.dumps({"version": 1, "usable": False, "slots": {"X": {"post": ["03:00"]}}}), encoding="utf-8")
    monkeypatch.setattr(scheduler, "SCHEDULING_RECOMMENDATIONS", recs)

    assert scheduler.slots_for("X", "post") == scheduler.DEFAULT_SLOTS["X"]


def test_readiness_preflight_allows_ready_with_warnings(tmp_path, monkeypatch):
    readiness = tmp_path / "readiness.sh"
    readiness.write_text("#!/usr/bin/env bash\necho overall=READY_WITH_WARNINGS\nexit 1\n", encoding="utf-8")
    readiness.chmod(0o755)
    monkeypatch.setattr(scheduler, "READINESS_CHECK", readiness)

    assert scheduler.readiness_preflight_blocked("publish") is None


def test_readiness_preflight_blocks_hard_failure(tmp_path, monkeypatch):
    readiness = tmp_path / "readiness.sh"
    readiness.write_text("#!/usr/bin/env bash\necho overall=BLOCKED\nexit 2\n", encoding="utf-8")
    readiness.chmod(0o755)
    monkeypatch.setattr(scheduler, "READINESS_CHECK", readiness)

    blocked = scheduler.readiness_preflight_blocked("publish")

    assert blocked is not None
    assert "readiness check exited 2" in blocked


def test_approval_card_preflight_allows_ready_with_warnings(tmp_path, monkeypatch):
    readiness = tmp_path / "readiness.sh"
    readiness.write_text("#!/usr/bin/env bash\necho overall=READY_WITH_WARNINGS\nexit 1\n", encoding="utf-8")
    readiness.chmod(0o755)
    monkeypatch.setattr(approval_dispatcher, "READINESS_CHECK", readiness)

    approval_dispatcher.run_readiness_preflight()


def test_approval_card_preflight_blocks_hard_failure(tmp_path, monkeypatch):
    readiness = tmp_path / "readiness.sh"
    readiness.write_text("#!/usr/bin/env bash\necho overall=BLOCKED\nexit 2\n", encoding="utf-8")
    readiness.chmod(0o755)
    monkeypatch.setattr(approval_dispatcher, "READINESS_CHECK", readiness)

    try:
        approval_dispatcher.run_readiness_preflight()
    except approval_dispatcher.ReadinessBlocked as exc:
        assert "readiness check exited 2" in str(exc)
    else:
        raise AssertionError("expected hard readiness failure to block approval card dispatch")


def test_scheduler_parse_first_batch_stops_last_reply_before_global_metadata(monkeypatch, tmp_path):
    queue = tmp_path / "queue.md"
    queue.write_text(
        """status: needs-review
exact_content: |
  X REPLY DRAFTS

  XReply-05 - Blake Neff / clever marketing
  Target URL: https://x.com/BlakeSNeff/status/2
  Target context: Comment on clever marketing.
  Reply:
  That’s the kind of marketing I actually like.

media:
  - none
links:
  - none
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(scheduler, "QUEUE", queue)

    drafts = scheduler.parse_first_batch()
    reply = drafts["XReply-05"]

    assert reply.content == "That’s the kind of marketing I actually like."
    assert reply.target_url == "https://x.com/BlakeSNeff/status/2"
    assert "media:" not in reply.content
    review = scheduler.review_social_copy(reply.content, platform=reply.platform, kind=reply.kind)
    assert review["blocking"] is False


def test_schedule_new_approvals_blocks_ai_slop_before_scheduling(monkeypatch):
    state = {"items": {}}
    drafts = {
        "X-99": scheduler.Draft(
            item_id="X-99",
            platform="X",
            kind="post",
            title="AI slop draft",
            content="Great point! Here's the thing: this game-changing framework unlocks value across the entire landscape. Thoughts?",
        )
    }
    events = [{"item_id": "X-99", "action": "approve", "recorded_at": 1}]

    scheduled = scheduler.schedule_new_approvals(state, drafts, events, persist=False)

    assert scheduled == []
    assert state["items"]["X-99"]["status"] == "blocked"
    assert state["items"]["X-99"]["block_reason"] == "voice_review_failed"
    assert any(issue["code"] == "ai_signposting" for issue in state["items"]["X-99"]["voice_review"]["issues"])


def test_publish_due_blocks_existing_scheduled_ai_slop_before_publish():
    past = "2026-01-01T00:00:00+00:00"
    state = {
        "items": {
            "X-98": {
                "item_id": "X-98",
                "platform": "X",
                "kind": "post",
                "status": "scheduled",
                "scheduled_at": past,
                "auto_publish": True,
            }
        }
    }
    drafts = {
        "X-98": scheduler.Draft(
            item_id="X-98",
            platform="X",
            kind="post",
            title="AI slop draft",
            content="Great point! Here's the thing: this game-changing framework unlocks value across the entire landscape. Thoughts?",
        )
    }

    messages, readiness_blocked = scheduler.publish_due(state, drafts, execute=True)

    assert readiness_blocked is False
    assert any("voice review failed" in message for message in messages)
    assert state["items"]["X-98"]["status"] == "blocked"
    assert state["items"]["X-98"]["block_reason"] == "voice_review_failed"


def test_recover_legacy_x_auth_blocks_reschedules_false_classifier_blocks():
    state = {
        "items": {
            "XReply-01": {
                "item_id": "XReply-01",
                "platform": "X",
                "kind": "reply",
                "status": "blocked",
                "block_reason": "x_state_unrecognized",
            },
            "XReply-02": {
                "item_id": "XReply-02",
                "platform": "X",
                "kind": "reply",
                "status": "blocked",
                "block_reason": "reply target_url missing",
            },
        }
    }

    recovered = scheduler.recover_legacy_x_auth_blocks(state)

    assert recovered == ["XReply-01"]
    assert state["items"]["XReply-01"]["status"] == "scheduled"
    assert "block_reason" not in state["items"]["XReply-01"]
    assert state["items"]["XReply-02"]["status"] == "blocked"
