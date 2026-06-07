# X Bookmark Learning Analyzer — Kanban Create Payloads

Purpose
- Ready-to-create payloads for the Factory + Kanban dispatch path.
- Order matters: create the factory card first, then the five P0 workflow cards, then the value gate, then keep P1 parked.
- These payloads preserve the MVP guardrail: no giant knowledge graph, no embedding-heavy detour, no entity-network rebuild before the slice proves useful.

Source of truth
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-kanban-factory-plan.md
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-factory-execution-queue.md
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-factory-prompt-bundle.md

Profiles available on this machine
- factory
- backend-engineer
- frontend-engineer
- pr-reviewer
- product-manager
- social-media-manager
- devops-engineer
- marcusgoll-content-growth

Create order
1. FX-0 factory intake
2. P0-1 schema
3. P0-2 dedupe/caching
4. P0-3 triage scoring
5. P0-4 project routing
6. P0-5 learning note output
7. P0-VALUE-GATE
8. P1-6 content idea output only if gate passes
9. P1-7 weekly digest only if gate passes
10. P1-8 metrics dashboard only if gate passes

Notes
- Parent IDs are placeholders until the parent card exists.
- Create the parent first, capture the returned ID, then substitute it into the child payloads.
- The body text is intentionally bounded so the factory can fan out without scope creep.

============================================================
FX-0 — Factory intake
============================================================
Payload
```json
{
  "title": "FX-0: synthesize P0 workflows for X Bookmark Learning Analyzer",
  "assignee": "factory",
  "priority": "P0",
  "body": "Goal: convert the five P0 cards into bounded implementation workflows and preserve the MVP guardrail. Scope: confirm assignees, parent links, verification steps, and rollback paths. Non-goals: no knowledge graph, no embedding search, no P1 dispatch. Inputs: approved MVP plan, existing bookmark scripts, existing tests and outputs. Outputs: one workflow chain per P0 card, plus a value-gate checkpoint. Acceptance: each P0 card has implement -> test -> review -> verify, every workflow names a responsible profile, rollback is explicit, and P1 remains gated. Verification: read back each workflow for scope boundaries and reviewers. Risks: over-scoping, accidental P1 leakage, overly broad child tasks. Rollback: abort P1 and keep legacy summary/opportunity paths active.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-fx-0-2026-06-03"
}
```

============================================================
P0-1 — Bookmark schema
============================================================
Payload
```json
{
  "title": "P0-1: bookmark schema",
  "assignee": "backend-engineer",
  "priority": "P0",
  "parents": ["FX0_ID"],
  "body": "Problem: bookmark processing needs a canonical schema so downstream outputs stay stable and versioned. Scope: define the bookmark schema and versioned artifact shape, add fixtures and validation tests, preserve compatibility with existing summary and analysis outputs. Non-goals: no new knowledge model, no cross-bookmark semantic graph, no UI/dashboard work. Inputs: current summary/analysis outputs and existing fixtures. Outputs: canonical schema definition, versioned artifact shape, validation tests, compatibility notes. Acceptance: schema round-trips existing outputs, version is explicit, legacy outputs still work through adapters. Verification: run schema validation tests and round-trip existing artifacts. Risks: breaking consumers, overfitting schema. Rollback: keep legacy adapters active and revert the version bump if needed.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-1-schema-2026-06-03"
}
```

============================================================
P0-2 — Deduplication/caching
============================================================
Payload
```json
{
  "title": "P0-2: deduplication and caching",
  "assignee": "backend-engineer",
  "priority": "P0",
  "parents": ["FX0_ID"],
  "body": "Problem: repeated bookmark runs waste time and can produce duplicate work. Scope: normalize URLs and content hashes, add cache keys and a reuse path for repeated analysis, add repeat-run regression tests. Non-goals: no distributed cache, no semantic dedupe model, no graph-based identity resolution. Inputs: existing parser and run outputs plus representative repeated bookmarks. Outputs: deterministic dedupe keys, cache reuse path, regression tests. Acceptance: duplicate inputs are suppressed or reused deterministically, cache hits are observable, cache misses still produce correct outputs. Verification: run the same input twice and confirm the second path reuses work, confirm duplicate suppression on normalized URLs, confirm no false positives on distinct items. Risks: stale cache entries and suppressing distinct bookmarks. Rollback: disable cache reuse and fall back to per-run analysis.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-2-dedupe-cache-2026-06-03"
}
```

============================================================
P0-3 — Triage scoring
============================================================
Payload
```json
{
  "title": "P0-3: triage scoring model",
  "assignee": "backend-engineer",
  "priority": "P0",
  "parents": ["FX0_ID"],
  "body": "Problem: the analyzer needs a deterministic scoring model to rank bookmarks for actionability. Scope: implement deterministic scoring and reason codes, add threshold and fixture tests, ensure stable ordering on repeated runs. Non-goals: no ML ranking, no opaque learned weights, no cross-bookmark knowledge graph. Inputs: current heuristic router behavior and representative fixtures. Outputs: a score per item, human-readable reason codes, stable ordering across repeated runs. Acceptance: deterministic scores, explainable reasons, threshold behavior covered by tests. Verification: run scoring twice and compare order, inspect reasons for top and low items, confirm fixtures pass. Risks: threshold drift and scores that are too coarse. Rollback: fall back to the current heuristic router weights and keep the new model behind a switch.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-3-scoring-2026-06-03"
}
```

============================================================
P0-4 — Project routing
============================================================
Payload
```json
{
  "title": "P0-4: project routing",
  "assignee": "backend-engineer",
  "priority": "P0",
  "parents": ["FX0_ID"],
  "body": "Problem: scored bookmarks need to route into the right project buckets with minimal noise. Scope: route items into primary project buckets, preserve explanations and secondary-route rules, add routing fixture tests. Non-goals: no auto-creation of new projects, no multi-hop project graph, no knowledge-graph routing. Inputs: scored bookmark items and current opportunity router behavior. Outputs: primary route assignment, secondary-route rationale where needed, fixture-tested routing rules. Acceptance: representative bookmarks route to expected buckets, explanations are preserved, over-routing stays limited. Verification: run routing fixtures, confirm explanations survive the route, confirm secondary routes only appear when justified. Risks: over-routing and unstable rules. Rollback: collapse to a single primary route and revert to opportunity-router behavior if noisy.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-4-routing-2026-06-03"
}
```

============================================================
P0-5 — Learning note output
============================================================
Payload
```json
{
  "title": "P0-5: learning note output",
  "assignee": "backend-engineer",
  "priority": "P0",
  "parents": ["FX0_ID"],
  "body": "Problem: the analyzer needs a human-readable learning note that is actionable, short, and easy to review. Scope: add a markdown note template and note writer, cover dedupe-by-id behavior, preserve source URL, author, and project bucket. Non-goals: no long-form essay generation, no content marketing output, no dashboard dependency. Inputs: routed bookmark items and existing opportunity memo behavior. Outputs: a concise learning note artifact and round-trippable metadata. Acceptance: the note is readable and short, traceable to the source item, and duplicate notes are avoided on repeated runs. Verification: render a note from a known bookmark, confirm metadata round-trips, confirm the note is not duplicative across repeated runs. Risks: notes becoming too verbose or too generic. Rollback: fall back to the existing opportunity memo output if the new note format is too heavy.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-5-note-2026-06-03"
}
```

============================================================
P0-VALUE-GATE — Product decision checkpoint
============================================================
Payload
```json
{
  "title": "P0-VALUE-GATE: evaluate whether the P0 slice is useful",
  "assignee": "product-manager",
  "priority": "P0",
  "parents": ["P0_1_ID", "P0_2_ID", "P0_3_ID", "P0_4_ID", "P0_5_ID"],
  "body": "Problem: the sprint needs an explicit go/no-go checkpoint before any P1 work starts. Scope: evaluate whether the P0 slice is useful enough to unlock P1 and decide whether to proceed, tighten the MVP, or stop. Non-goals: no implementation work and no P1 dispatch unless the P0 slice proves value. Inputs: output from P0-1 through P0-5 and real run evidence from the analyzer. Outputs: unlock P1 or hold P1 and a clear value judgment. Acceptance: a bookmark can enter once, be deduped, scored, routed, and turned into a usable note; the output is something the user would actually read or act on. Verification: inspect real P0 outputs, confirm the outputs are useful without extra manual cleanup, confirm the value decision is evidence-based. Risks: unlocking P1 too early and confusing technical completeness with product value. Rollback: keep P1 parked and tighten the MVP if the P0 slice is not yet useful.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p0-value-gate-2026-06-03"
}
```

============================================================
P1-6 — Content idea output, parked until gate passes
============================================================
Payload
```json
{
  "title": "P1-6: content idea output",
  "assignee": "marcusgoll-content-growth",
  "priority": "P1",
  "parents": ["P0_VALUE_GATE_ID"],
  "body": "Problem: convert high-value bookmarks into a content idea without becoming generic. Scope: extract hook, angle, audience, and proof point; add novelty checks and duplicate suppression tests. Non-goals: no public publishing workflow, no giant knowledge graph, no broad editorial pipeline. Inputs: P0 outputs and routed bookmark items. Outputs: content idea draft and novelty/duplication checks. Acceptance: the idea is specific, grounded in source material, and not a generic content prompt. Verification: run on sample bookmarks and compare against prior ideas. Risks: generic-copy drift and duplicate ideas. Rollback: disable idea generation and keep note/routing live.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p1-6-content-ideas-2026-06-03"
}
```

============================================================
P1-7 — Weekly digest, parked until gate passes
============================================================
Payload
```json
{
  "title": "P1-7: weekly digest",
  "assignee": "backend-engineer",
  "priority": "P1",
  "parents": ["P0_VALUE_GATE_ID"],
  "body": "Problem: summarize the week's bookmark activity in one digest. Scope: aggregate notes, routes, and ideas into digest input and snapshot-test digest rendering against a fixed week. Non-goals: no heavy reporting layer and no replacement of the existing lightweight digest path unless needed. Inputs: output from P0 and historical weekly digest behavior. Outputs: digest input aggregation and rendered weekly digest. Acceptance: digest is deterministic for a fixed week, includes the important signals, and stays readable. Verification: snapshot-test a fixed week and review for repetition. Risks: nondeterminism and overly repetitive summaries. Rollback: revert to the current lightweight weekly_bookmark_digest.py behavior.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p1-7-weekly-digest-2026-06-03"
}
```

============================================================
P1-8 — Metrics dashboard, parked until gate passes
============================================================
Payload
```json
{
  "title": "P1-8: metrics dashboard",
  "assignee": "frontend-engineer",
  "priority": "P1",
  "parents": ["P0_VALUE_GATE_ID"],
  "body": "Problem: the analyzer needs a small local-first dashboard or report page to show whether it is actually useful. Scope: emit metrics JSON for processed, deduped, routed, note, idea, digest, and cache-hit counts; render a small local-first dashboard/report page. Non-goals: no enterprise analytics layer, no knowledge graph, no complex charting. Inputs: P0 metrics and route outputs. Outputs: metrics JSON and a small dashboard/report page. Acceptance: the dashboard shows proof-of-value metrics without hiding failures. Verification: confirm counts are emitted and the page renders the same numbers. Risks: dashboard bloat and obscuring failure modes. Rollback: reduce to a minimal run summary if the dashboard is too heavy.",
  "created_by": "kanban-orchestrator",
  "idempotency_key": "x-bookmark-p1-8-dashboard-2026-06-03"
}
```

Run notes
- Replace FX0_ID / P0_1_ID / P0_2_ID / P0_3_ID / P0_4_ID / P0_5_ID / P0_VALUE_GATE_ID with the real task IDs returned by your kanban create calls.
- Keep P1 payloads uncreated until the value gate passes.
- If you want strict execution, create and dispatch one P0 workflow at a time, then review before the next.
