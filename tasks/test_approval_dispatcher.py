#!/usr/bin/env python3
"""Tests for one-at-a-time social approval dispatcher."""
import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "approval_dispatcher.py"
spec = importlib.util.spec_from_file_location("approval_dispatcher", MODULE_PATH)
dispatcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dispatcher)


def write_packet(path: Path, *, status: str = "needs-review", platform: str = "X", body: str = "hello world"):
    path.write_text(
        f"""# Approval Packet: Test

Status: {status}

## Target surface
{platform}

## Exact action
Publish one post.

## Exact content
{body}

## Links / media / assets
- none

## Risk notes
- Low.
"""
    )


def test_load_markdown_packet_extracts_card_fields(tmp_path):
    packet = tmp_path / "queue" / "x-001.md"
    packet.parent.mkdir()
    write_packet(packet, platform="X", body="exact copy")

    items = dispatcher.load_queue_items([packet.parent])

    assert len(items) == 1
    item = items[0]
    assert item["item_id"] == "x-001"
    assert item["platform"] == "X"
    assert item["status"] == "needs-review"
    assert item["copy"] == "exact copy"
    assert item["source_path"] == str(packet)


def test_load_json_items_extracts_pending_cards(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "items.json").write_text(json.dumps({"items": [{"id": "j1", "platform": "LinkedIn", "status": "proposed", "text": "copy"}]}))

    items = dispatcher.load_queue_items([queue])

    assert items == [
        {
            "item_id": "j1",
            "platform": "LinkedIn",
            "type": "post",
            "goal": "Review and approve exact content.",
            "risk": "unknown",
            "copy": "copy",
            "status": "proposed",
            "source_path": str(queue / "items.json"),
        }
    ]


def test_dispatch_sends_one_card_and_second_run_stays_silent(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    write_packet(queue / "x-001.md", body="first")
    write_packet(queue / "x-002.md", body="second")

    first = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)
    second = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)

    assert first["status"] == "sent"
    assert first["item"]["item_id"] == "x-001"
    assert "SOCIAL APPROVAL x-001" in first["card"]
    assert second["status"] == "waiting"
    assert second["outstanding"]["item_id"] == "x-001"


def test_record_decision_allows_next_card(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    write_packet(queue / "x-001.md", body="first")
    write_packet(queue / "x-002.md", body="second")

    dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)
    event = dispatcher.record_decision(approvals, "x-001", "approve", actor="test")
    next_card = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)

    assert event["action"] == "approve"
    assert next_card["status"] == "sent"
    assert next_card["item"]["item_id"] == "x-002"


def test_rejects_invalid_decision_action(tmp_path):
    try:
        dispatcher.record_decision(tmp_path, "x-001", "publish-now")
    except ValueError as exc:
        assert "invalid approval action" in str(exc)
    else:
        raise AssertionError("expected invalid action rejection")


def test_dry_run_does_not_write_registry(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    write_packet(queue / "x-001.md")

    result = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=True)

    assert result["status"] == "would_send"
    assert not (approvals / "sent-approval-cards.json").exists()


def test_render_card_is_short_and_explicit():
    card = dispatcher.render_card({
        "item_id": "x-001",
        "platform": "X",
        "type": "reply",
        "goal": "Engage with useful thread.",
        "risk": "low",
        "copy": "Nice point.",
    })

    assert card.startswith("SOCIAL APPROVAL x-001")
    assert "Platform: X" in card
    assert "Copy:\nNice point." in card
    assert "approve x-001" in card


def test_load_social_batch_splits_real_batch_shape(tmp_path):
    queue = tmp_path / "queue"
    queue.mkdir()
    (queue / "batch.md").write_text(
        """status: needs-review
exact_content: |
  X DRAFTS

  X-01 - First post
  first line

  X-02 - Second post
  second line

  X REPLY DRAFTS

  XReply-04 - Lakshman / browser agents
  Target URL: https://x.com/parzival1213/status/1
  Target context: browser agents
  Reply:
  Yep. The unsexy parts matter most.

  XReply-05 - Blake Neff / clever marketing
  Target URL: https://x.com/BlakeSNeff/status/2
  Target context: clever marketing
  Reply:
  That’s the kind of marketing I actually like.

media:
  - none
"""
    )

    items = dispatcher.load_queue_items([queue])

    assert [item["item_id"] for item in items] == ["X-01", "X-02", "XReply-04", "XReply-05"]
    assert items[0]["platform"] == "X"
    assert items[0]["type"] == "post"
    assert items[2]["type"] == "reply"
    assert items[2]["target_url"] == "https://x.com/parzival1213/status/1"
    assert items[2]["copy"] == "Yep. The unsexy parts matter most."


def test_tracker_statuses_filter_non_pending_items(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    approvals.mkdir()
    (queue / "batch.md").write_text(
        """status: needs-review
exact_content: |
  X DRAFTS

  X-01 - First post
  first line

  X-02 - Second post
  second line
"""
    )
    tracker = approvals / "tracker.md"
    tracker.write_text(
        """| ID | Platform | Type | Status | Notes |
|---|---|---|---|---|
| X-01 | X | post | published | done |
| X-02 | X | post | pending | next |
"""
    )

    result = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, tracker_path=tracker, dry_run=True)

    assert result["status"] == "would_send"
    assert result["item"]["item_id"] == "X-02"


def test_legacy_registry_blocks_when_last_sent_has_no_decision(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    approvals.mkdir()
    write_packet(queue / "xreply-05.md", body="next")
    (approvals / "sent-approval-cards.json").write_text(json.dumps({
        "cards": {
            "XReply-04": {"item_id": "XReply-04", "platform": "X", "message_id": 786},
        },
        "last_sent_item_id": "XReply-04",
        "version": 1,
    }))

    result = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)

    assert result["status"] == "waiting"
    assert result["outstanding"]["item_id"] == "XReply-04"


def test_legacy_registry_allows_next_after_decision(tmp_path):
    queue = tmp_path / "queue"
    approvals = tmp_path / "approvals"
    queue.mkdir()
    approvals.mkdir()
    write_packet(queue / "xreply-05.md", body="next")
    (approvals / "sent-approval-cards.json").write_text(json.dumps({
        "cards": {
            "XReply-04": {"item_id": "XReply-04", "platform": "X", "message_id": 786},
        },
        "last_sent_item_id": "XReply-04",
        "version": 1,
    }))
    dispatcher.record_decision(approvals, "XReply-04", "reject", actor="test")

    result = dispatcher.dispatch_next(queue_dirs=[queue], approvals_dir=approvals, dry_run=False)

    assert result["status"] == "sent"
    assert result["item"]["item_id"] == "xreply-05"
