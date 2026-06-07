# Content Idea Draft Contract v1

## Purpose

Define the minimal input and output contract for generating one local content idea
draft from a routed X bookmark opportunity. This contract is intentionally scoped
to draft generation only so downstream implementers do not add publishing or
workflow behavior by accident.

Source of truth in code today:

- `scripts/feed_to_agents.py`
  - `build_opportunity_router(summary, analysis)` emits routed bookmark items.
  - `build_content_idea_draft(item, generated_on, prior_ideas=None)` emits one
    `content-idea/v1` draft.
  - `build_content_idea_artifacts(routed, generated_on, prior_ideas=None,
    enabled=True)` maps routed sections into draft artifacts without mutating the
    routing payload.
- `tasks/test_bookmark_opportunities.py` covers routed bookmark section shape.
- `tasks/test_bookmark_content_ideas.py` covers draft shape, grounding, rejection,
  and duplicate behavior.

## In scope

- Read routed bookmark items from `immediate_actions`, `research_queue`, and
  `knowledge_promotions`.
- Accept either the current routed-bookmark fields or P0 learning-note fields as
  source material.
- Generate a structured local draft with `hook`, `angle`, `audience`, and
  `proof_point`.
- Preserve source attribution and per-field grounding so every generated draft
  claim can be traced to the routed item.
- Reject drafts when source material is missing, generic, or duplicate.

## Explicit non-goals

- Publishing to X, LinkedIn, or any public channel.
- Editorial assignment, approval queue, rewrite workflow, or scheduling.
- Knowledge-graph creation, wiki promotion, skill creation, or backlinking.
- Bookmark move/delete execution or approval handling.
- LLM-based expansion beyond the provided routed bookmark/P0 source fields.

## Input contract

### Routed bookmark container

`build_content_idea_artifacts` accepts a routed opportunity object with these
sections:

```json
{
  "generated_from": "x_bookmark_analysis",
  "total_processed": 1,
  "action_summary": {"ok": 1, "error": 0, "skipped": 0},
  "immediate_actions": [],
  "research_queue": [],
  "knowledge_promotions": [],
  "skipped": {"deleted_or_low_value": 0, "unscored": 0}
}
```

Only these sections are eligible for content ideas:

- `immediate_actions`
- `research_queue`
- `knowledge_promotions`

Each section contains routed bookmark items. When `source_section` is absent,
`build_content_idea_artifacts` sets it from the section name before drafting.

### Required routed bookmark item fields

A routed item must provide enough grounded source material for three content
parts: `insight`, `action`, and `why`. The current router emits these fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `url` | Yes | Source bookmark URL; becomes `source_url`. |
| `author` | Yes | Source author handle; becomes `source_author`. |
| `insight` | Yes unless supplied by P0 output | Source-derived takeaway for `hook`. |
| `action` | Yes unless supplied by P0 output | Operator action used for `angle`. |
| `why` | Yes unless supplied by P0 output | Evidence/reason used for `proof_point`. |
| `score` | Yes | Router score copied to output for prioritization context. |
| `source_section` | Recommended | One of the eligible sections; derived from container when absent. |
| `project_bucket` | Recommended | Product/operator context for `angle` and `audience`. |
| `folder` | Optional fallback | Used as project bucket when `project_bucket` is absent. |
| `id` or `source_item_id` | Optional | Stable source id; otherwise derived from `url`, `action`, and `insight`. |

The generator also accepts `author_name`, `source_url`, `primary_route`, `title`,
and `suggested_action` as compatibility/fallback aliases, but new producers
should prefer the fields above.

### P0 output fields accepted as source material

When a routed item carries a P0/learning-note output under `learning_note`, the
content idea generator may use those fields as grounded replacements for missing
legacy fields:

| P0 field | Maps to | Required when used |
| --- | --- | --- |
| `learning_note.takeaway` | `source_material.insight`, `hook` grounding | Yes unless `learning_note.summary` or `insight` exists. |
| `learning_note.summary` | `source_material.insight`, `hook` grounding | Yes only when `takeaway` and `insight` are absent. |
| `learning_note.action` | `source_material.action`, `angle` grounding | Yes unless `action` or `suggested_action` exists. |
| `learning_note.why_now` | `source_material.why`, `proof_point` grounding | Yes unless `why` or `reason_codes` exists. |

The generator rejects the item instead of inventing copy when the combined routed
bookmark/P0 source material cannot supply all three parts: insight, action, and
why/proof evidence.

## Output contract

One accepted or rejected draft is a JSON object with:

| Field | Required | Notes |
| --- | --- | --- |
| `schema_version` | Yes | Must be `content-idea/v1`. |
| `artifact_type` | Yes | Must be `content_idea`. |
| `content_idea_id` | Yes | Stable hash for accepted drafts; empty for early rejections. |
| `generated_on` | Yes | Caller-provided date/string. |
| `status` | Yes | `accepted` or `rejected`. |
| `source_item_id` | Yes | Source routed item id or deterministic fallback. |
| `source_url` | Yes | Original bookmark URL. |
| `source_author` | Yes | Original author/handle. |
| `source_section` | Yes | Origin section used for routing. |
| `project_bucket` | Yes | Context bucket; falls back to route/folder/section/unassigned. |
| `score` | Yes | Copied from routed item; defaults to `0`. |
| `hook` | Yes | Draft hook; blank on rejection before generation. |
| `angle` | Yes | Draft angle; blank on rejection before generation. |
| `audience` | Yes | Draft audience; blank on rejection before generation. |
| `proof_point` | Yes | Source-backed proof point; blank when proof is ungrounded. |
| `source_material` | Yes | Normalized insight/action/why/source attribution used to draft. |
| `field_grounding` | Yes | Per-field source paths, evidence excerpt, grounding note. |
| `novelty_check` | Yes | Accept/reject status plus reason codes and duplicate score. |
| `duplicate_policy` | Yes | Duplicate status and nearest prior idea id when available. |
| `rejection_reason` | Yes | `null` for accepted drafts; reason code for rejections. |

Required draft fields for accepted ideas:

- `hook`: source-specific opening statement derived from `insight` or P0 takeaway.
- `angle`: operator/product angle derived from `action` and `project_bucket`.
- `audience`: target reader derived from `project_bucket`, `source_section`, and
  source author.
- `proof_point`: claim/evidence derived from `why`, `reason_codes`, or
  `learning_note.why_now`. This must not be action-only when no distinct proof
  evidence exists.

`field_grounding` must contain entries for `hook`, `angle`, `audience`, and
`proof_point`, each shaped as:

```json
{
  "source_paths": ["insight"],
  "evidence_excerpt": "Agent memory systems need remember/cite/forget layers before adding more tools.",
  "grounding_note": "Hook preserves the source-derived takeaway instead of inventing a generic prompt."
}
```

## Representative sample

### Sample routed/P0 input

```json
{
  "generated_from": "x_bookmark_analysis",
  "total_processed": 1,
  "action_summary": {"ok": 1, "error": 0, "skipped": 0},
  "immediate_actions": [
    {
      "id": "x-bookmark-memory-layers",
      "author": "good_ai",
      "url": "https://x.com/good_ai/status/123",
      "source_section": "immediate_actions",
      "project_bucket": "hermes",
      "folder": "ai_tools",
      "score": 18,
      "insight": "",
      "action": "",
      "why": "",
      "learning_note": {
        "takeaway": "Agent memory hygiene needs citation and forgetting review before tool sprawl.",
        "action": "Turn the learning note into a pre-release memory hygiene checklist.",
        "why_now": "The P0 note was routed to Hermes because memory hygiene can prevent stale context regressions."
      }
    }
  ],
  "research_queue": [],
  "knowledge_promotions": [],
  "skipped": {"deleted_or_low_value": 0, "unscored": 0}
}
```

### Expected structured output

```json
{
  "schema_version": "content-idea/v1",
  "artifact_type": "content_idea",
  "content_idea_id": "content-idea-<deterministic-12-hex>",
  "generated_on": "2026-06-03",
  "status": "accepted",
  "source_item_id": "x-bookmark-memory-layers",
  "source_url": "https://x.com/good_ai/status/123",
  "source_author": "good_ai",
  "source_section": "immediate_actions",
  "project_bucket": "hermes",
  "score": 18,
  "hook": "Before turn the learning note into a pre-release memory hygiene checklist., notice this source-specific constraint: Agent memory hygiene needs citation and forgetting review before tool sprawl.",
  "angle": "Use the hermes angle to turn the bookmark into a concrete operator decision: Turn the learning note into a pre-release memory hygiene checklist.",
  "audience": "hermes operators reviewing immediate_actions bookmarks from @good_ai",
  "proof_point": "The P0 note was routed to Hermes because memory hygiene can prevent stale context regressions.",
  "source_material": {
    "insight": "Agent memory hygiene needs citation and forgetting review before tool sprawl.",
    "action": "Turn the learning note into a pre-release memory hygiene checklist.",
    "why": "The P0 note was routed to Hermes because memory hygiene can prevent stale context regressions.",
    "url": "https://x.com/good_ai/status/123",
    "author": "good_ai",
    "source_section": "immediate_actions",
    "project_bucket": "hermes"
  },
  "field_grounding": {
    "hook": {
      "source_paths": ["learning_note.takeaway"],
      "evidence_excerpt": "Agent memory hygiene needs citation and forgetting review before tool sprawl.",
      "grounding_note": "Hook preserves the source-derived takeaway instead of inventing a generic prompt."
    },
    "angle": {
      "source_paths": ["learning_note.action", "project_bucket"],
      "evidence_excerpt": "Turn the learning note into a pre-release memory hygiene checklist.",
      "grounding_note": "Angle is anchored to the existing operator action and project context."
    },
    "audience": {
      "source_paths": ["project_bucket", "source_section", "author"],
      "evidence_excerpt": "hermes operators reviewing immediate_actions bookmarks from @good_ai",
      "grounding_note": "Audience is derived only from routed project context and source attribution."
    },
    "proof_point": {
      "source_paths": ["learning_note.why_now"],
      "evidence_excerpt": "The P0 note was routed to Hermes because memory hygiene can prevent stale context regressions.",
      "grounding_note": "Proof point uses router/scorer evidence; no external claim is added."
    }
  },
  "novelty_check": {
    "status": "accept",
    "novelty_score": 1.0,
    "duplicate_score": 0.0,
    "generic_score": 0.0,
    "reason_codes": [],
    "nearest_prior_idea_id": null
  },
  "duplicate_policy": {
    "status": "accepted",
    "duplicate_score": 0.0,
    "nearest_prior_idea_id": null,
    "reason_codes": []
  },
  "rejection_reason": null
}
```

## Rejection rules

- Missing insight/action/why after routed + P0 fallback: reject with
  `rejection_reason: "missing_or_ungrounded_proof_point"`.
- Generic source material such as "interesting idea", "write a post", or
  "could be useful": reject with `rejection_reason: "too_generic"` and
  `novelty_check.reason_codes: ["generic_phrase"]`.
- Duplicate content idea above the duplicate threshold: reject with
  `rejection_reason: "duplicate_content_idea"` and populate nearest prior id
  when available.

## Verification expectation

For changes touching this contract, run at least:

```bash
python -m pytest tasks/test_bookmark_opportunities.py tasks/test_bookmark_content_ideas.py -q
```

If host Python dependency isolation fails for broader suites, use the repo's
Docker runner documented in `README.md` and `docs/ops/source-checkpoint.md`.
