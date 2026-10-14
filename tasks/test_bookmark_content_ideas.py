#!/usr/bin/env python3
"""Tests for source-grounded X bookmark content idea drafts and gates."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import feed_to_agents as feed  # noqa: E402


class ContentIdeaIntegrationTests(unittest.TestCase):
    def routed_bookmark(self, **overrides):
        item = {
            "id": "x-bookmark-approval-gates",
            "author": "agent_builder",
            "url": "https://x.com/agent_builder/status/42",
            "source_section": "immediate_actions",
            "project_bucket": "hermes",
            "folder": "ai_tools",
            "score": 19,
            "insight": "Browser agents need approval gates and proof bundles before unattended actions are allowed.",
            "action": "Add a browser-agent review checklist before scaling approved automations.",
            "why": "The routed P0 bookmark names approval gates, proof bundles, and review queues as concrete safety controls.",
            "priority": 1,
        }
        item.update(overrides)
        return item

    def test_draft_output_contract_has_required_fields_and_pending_status(self):
        draft = feed.build_content_idea_draft(self.routed_bookmark(), generated_on="2026-06-04")

        self.assertEqual(draft["schema_version"], "content-idea/v1")
        self.assertEqual(draft["artifact_type"], "content_idea")
        self.assertEqual(draft["status"], "pending_novelty_check")
        self.assertRegex(draft["content_idea_id"], r"^content-idea-[a-f0-9]{12}$")
        self.assertRegex(draft["source_fingerprint"], r"^source-[a-f0-9]{16}$")
        self.assertRegex(draft["idea_fingerprint"], r"^idea-[a-f0-9]{16}$")
        self.assertEqual(draft["source_metadata"]["source_item_id"], "x-bookmark-approval-gates")
        self.assertEqual(draft["source_metadata"]["source_url"], "https://x.com/agent_builder/status/42")
        for field in ("hook", "angle", "audience", "proof_point"):
            self.assertTrue(draft[field], field)
            self.assertIn(field, draft["field_grounding"])
            grounding = draft["field_grounding"][field]
            self.assertTrue(grounding["source_paths"], field)
            self.assertTrue(grounding["evidence_excerpt"], field)
            self.assertTrue(grounding["grounding_note"], field)
        self.assertEqual(draft["novelty_signal"]["status"], "not_checked")
        self.assertEqual(draft["duplicate_policy"]["status"], "not_checked")

    def test_field_grounding_uses_p0_learning_note_paths_when_router_fields_are_absent(self):
        item = self.routed_bookmark(insight="", action="", why="")
        item["learning_note"] = {
            "takeaway": "Approval gates should stop browser agents before irreversible account actions.",
            "action": "Turn the P0 note into an operator checklist for browser-agent approvals.",
            "why_now": "The note cites proof bundles and review queues as failure-prevention controls.",
        }

        draft = feed.build_content_idea_draft(item, generated_on="2026-06-04")

        self.assertEqual(draft["status"], "pending_novelty_check")
        self.assertEqual(draft["field_grounding"]["hook"]["source_paths"], ["learning_note.takeaway"])
        self.assertEqual(draft["field_grounding"]["angle"]["source_paths"], ["learning_note.action", "project_bucket"])
        self.assertEqual(draft["field_grounding"]["proof_point"]["source_paths"], ["learning_note.why_now"])

    def test_generic_idea_is_rejected_before_duplicate_scoring(self):
        generic = self.routed_bookmark(
            insight="Interesting idea about AI.",
            action="Write a post about it.",
            why="Could be useful.",
        )

        checked = feed.build_content_idea_with_checks(generic, generated_on="2026-06-04", prior_manifest=[])

        self.assertEqual(checked["status"], "rejected_generic")
        self.assertIn("generic", " ".join(checked["novelty_signal"]["reason_codes"]))
        self.assertEqual(checked["duplicate_policy"]["status"], "not_checked")

    def test_weak_or_untraceable_proof_point_is_rejected(self):
        weak = self.routed_bookmark(why="")

        checked = feed.build_content_idea_with_checks(weak, generated_on="2026-06-04", prior_manifest=[])

        self.assertEqual(checked["status"], "rejected_weak_evidence")
        self.assertIn("weak_proof_point", checked["novelty_signal"]["reason_codes"])
        self.assertEqual(checked["field_grounding"]["proof_point"]["source_paths"], [])

    def test_exact_duplicate_is_rejected_before_final_accepted_emission(self):
        accepted = feed.build_content_idea_with_checks(self.routed_bookmark(), generated_on="2026-06-04", prior_manifest=[])

        duplicate = feed.build_content_idea_with_checks(
            self.routed_bookmark(),
            generated_on="2026-06-04",
            prior_manifest=[accepted],
        )

        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(duplicate["status"], "rejected_duplicate")
        self.assertEqual(duplicate["duplicate_policy"]["nearest_prior_idea_id"], accepted["content_idea_id"])
        self.assertGreaterEqual(duplicate["duplicate_policy"]["duplicate_score"], 0.86)

    def test_near_duplicate_requires_revision_not_final_emission(self):
        prior = feed.build_content_idea_with_checks(self.routed_bookmark(), generated_on="2026-06-04", prior_manifest=[])
        near_duplicate = self.routed_bookmark(
            id="x-bookmark-approval-gates-rephrase",
            url="https://x.com/agent_builder/status/43",
            insight="Browser automation needs proof bundles and approval gates before unattended account actions.",
            action="Add a review checklist for browser-agent approvals before scaling automations.",
            why="The source-backed P0 route repeats approval gates, review queues, and proof bundles as the safety mechanism.",
        )

        checked = feed.build_content_idea_with_checks(near_duplicate, generated_on="2026-06-04", prior_manifest=[prior])

        self.assertEqual(checked["status"], "needs_revision")
        self.assertGreaterEqual(checked["duplicate_policy"]["duplicate_score"], 0.72)
        self.assertLess(checked["duplicate_policy"]["duplicate_score"], 0.86)

    def test_same_source_distinct_source_backed_angle_can_be_accepted(self):
        prior = feed.build_content_idea_with_checks(self.routed_bookmark(), generated_on="2026-06-04", prior_manifest=[])
        distinct = self.routed_bookmark(
            insight="The same bookmark also shows proof bundles are useful only when they include visual evidence before-and-after each browser step.",
            action="Add visual proof bundle review to the browser-agent operator checklist.",
            why="Same source, distinct proof: visual before/after evidence is a separate next-step from approval gates.",
        )

        checked = feed.build_content_idea_with_checks(distinct, generated_on="2026-06-04", prior_manifest=[prior])

        self.assertEqual(checked["status"], "accepted")
        self.assertLess(checked["duplicate_policy"]["duplicate_score"], 0.72)
        self.assertIn("source_backed_delta", checked["duplicate_policy"]["reason_codes"])

    def test_missing_prior_manifest_returns_needs_review_manifest_unavailable(self):
        routed = {"immediate_actions": [self.routed_bookmark()], "research_queue": [], "knowledge_promotions": []}

        ideas = feed.build_content_idea_artifacts(
            routed,
            generated_on="2026-06-04",
            prior_manifest_path="/tmp/does-not-exist-content-ideas.json",
        )

        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["status"], "needs_review")
        self.assertIn("manifest_unavailable", ideas[0]["novelty_signal"]["reason_codes"])

    def test_malformed_prior_manifest_returns_needs_review_manifest_unavailable(self):
        routed = {"immediate_actions": [self.routed_bookmark()], "research_queue": [], "knowledge_promotions": []}
        with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
            tmp.write(json.dumps({"not_ideas": "bad shape"}))
            manifest_path = tmp.name

        ideas = feed.build_content_idea_artifacts(routed, generated_on="2026-06-04", prior_manifest_path=manifest_path)

        self.assertEqual(ideas[0]["status"], "needs_review")
        self.assertIn("manifest_unavailable", ideas[0]["novelty_signal"]["reason_codes"])

    def test_unspecified_prior_manifest_returns_needs_review_manifest_unavailable(self):
        routed = {"immediate_actions": [self.routed_bookmark()], "research_queue": [], "knowledge_promotions": []}

        ideas = feed.build_content_idea_artifacts(routed, generated_on="2026-06-04")

        self.assertEqual(ideas[0]["status"], "needs_review")
        self.assertIn("manifest_unavailable", ideas[0]["novelty_signal"]["reason_codes"])

    def test_disabled_generation_returns_no_ideas_and_preserves_routing_payload(self):
        routed = {"immediate_actions": [self.routed_bookmark()], "research_queue": [], "knowledge_promotions": []}
        before = copy.deepcopy(routed)

        ideas = feed.build_content_idea_artifacts(routed, generated_on="2026-06-04", enabled=False)

        self.assertEqual(ideas, [])
        self.assertEqual(routed, before)

    def test_routed_p0_bookmark_router_output_feeds_content_idea_generation(self):
        summary = {
            "total_processed": 1,
            "action_summary": {"ok": 1, "error": 0, "skipped": 0, "by_action": {"move": 1}},
            "insights": [{"author": "agent_builder", "insight": self.routed_bookmark()["insight"], "url": self.routed_bookmark()["url"]}],
            "action_items": [{"author": "agent_builder", "action": self.routed_bookmark()["action"], "url": self.routed_bookmark()["url"]}],
        }
        analysis = [{"url": self.routed_bookmark()["url"], "folder": "ai_tools", "action_result": {"action": "move", "status": "ok"}}]
        routed = feed.build_opportunity_router(summary, analysis)

        ideas = feed.build_content_idea_artifacts(routed, generated_on="2026-06-04", prior_manifest=[])

        accepted = [idea for idea in ideas if idea["status"] == "accepted"]
        self.assertTrue(accepted)
        self.assertEqual(accepted[0]["source_metadata"]["source_section"], "immediate_actions")
        self.assertIn("approval gates", accepted[0]["hook"].lower())
        self.assertNotEqual(
            accepted[0]["proof_point"],
            "Relevant to active Hermes/trading/devops work and has an executable next step.",
        )
        self.assertEqual(accepted[0]["field_grounding"]["proof_point"]["source_paths"], ["insight"])
        self.assertIn("approval gates", accepted[0]["proof_point"].lower())


if __name__ == "__main__":
    unittest.main()
