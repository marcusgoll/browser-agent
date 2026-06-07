# X Bookmark Learning Analyzer — Factory Prompt Bundle

Purpose
- Dispatch-ready prompt bundle for the P0 slice of the MVP-first bookmark analyzer upgrade.
- Factory converts each P0 card into a bounded implementation workflow: implement -> test -> review -> verify.
- P1 work stays parked behind the value gate.
- No giant knowledge graph, no embedding-heavy detour, no entity-network rebuild before the MVP proves useful.

Source of truth
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-kanban-factory-plan.md
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-factory-execution-queue.md

Available profiles on this machine
- factory
- backend-engineer
- frontend-engineer
- pr-reviewer
- product-manager
- social-media-manager
- devops-engineer
- marcusgoll-content-growth

Dispatch rule
1. Create FX-0 [factory] first.
2. FX-0 emits the P0 implementation workflows below.
3. Each P0 workflow becomes its own bounded chain with explicit rollback.
4. Do not dispatch any P1 workflow until P0-VALUE-GATE says the slice is useful.

============================================================
1) FX-0 — Factory intake prompt
============================================================
Role: factory
Priority: P0
Problem
- The bookmark analyzer needs a small, valuable first slice that improves processing quality without over-building the system.

Scope
- Convert the five P0 cards into implementation workflows.
- Preserve the P1 park state.
- Enforce MVP guardrails.
- Confirm assignees, parent links, and rollback paths.

Non-goals
- Do not design a knowledge graph.
- Do not add embedding search.
- Do not widen the sprint beyond the five P0 cards.

Inputs
- Approved MVP plan.
- Existing bookmark processing and digest scripts.
- Existing tests and output shapes.

Outputs
- One workflow chain per P0 card.
- Parent/child dependency map.
- Verification and rollback plan per workflow.
- A clear note that P1 remains gated.

Acceptance criteria
- Every P0 card has a bounded implement -> test -> review -> verify workflow.
- Every workflow names the responsible profile.
- Rollback is explicit and low-risk.
- The bundle preserves the no-knowledge-graph guardrail.

Verification steps
- Read back each workflow for scope boundaries.
- Confirm each workflow has a reviewer.
- Confirm the value gate blocks P1.

Risks
- Over-scoping into related analytics work.
- Accidental P1 leakage before value proof.
- Factory producing child tasks that are too broad.

Rollback plan
- Abort P1 entirely if P0 does not prove useful.
- Keep legacy summary/opportunity paths active while P0 stabilizes.

Suggested output
- A short workflow list with task IDs, owners, parents, and rollback notes.

============================================================
2) P0-1 — Bookmark schema workflow prompt
============================================================
Role: backend-engineer
Priority: P0
Problem
- Bookmark processing needs a canonical schema so downstream outputs stay stable and versioned.

Scope
- Define the bookmark schema and versioned artifact shape.
- Add fixtures and validation tests.
- Preserve compatibility with existing summary and analysis outputs.

Non-goals
- No new knowledge model.
- No cross-bookmark semantic graph.
- No UI/dashboard work.

Inputs
- Current bookmark summary/analysis outputs.
- Existing parser and test fixtures.

Outputs
- Canonical schema definition.
- Versioned artifact shape.
- Validation tests and compatibility notes.

Acceptance criteria
- The schema round-trips existing outputs.
- Schema version is explicit.
- Legacy outputs still work through adapters.

Verification steps
- Run schema validation tests.
- Round-trip one or more existing bookmark artifacts.
- Confirm no regression in current summary/analysis generation.

Risks
- Breaking existing consumers.
- Overfitting the schema to one output type.

Rollback plan
- Keep legacy adapters active.
- Revert schema version bump if compatibility fails.

============================================================
3) P0-2 — Deduplication/caching workflow prompt
============================================================
Role: backend-engineer
Priority: P0
Problem
- Repeated bookmark runs waste time and can produce duplicate work.

Scope
- Normalize URLs and content hashes.
- Add cache keys and a reuse path for repeated analysis.
- Add repeat-run regression tests.

Non-goals
- No distributed cache.
- No semantic dedupe model.
- No graph-based identity resolution.

Inputs
- Existing bookmark parser and run outputs.
- Representative repeated bookmarks.

Outputs
- Deterministic dedupe keys.
- Cache reuse path.
- Regression tests for repeated runs.

Acceptance criteria
- Duplicate inputs are suppressed or reused deterministically.
- Cache hits are observable.
- Cache misses still produce correct outputs.

Verification steps
- Run the same input twice and confirm the second path reuses work.
- Confirm duplicate suppression on normalized URLs.
- Confirm no false-positive suppression on distinct items.

Risks
- Stale cache entries.
- Accidental suppression of legitimately distinct bookmarks.

Rollback plan
- Disable cache reuse and fall back to per-run analysis.
- Preserve the existing non-cached path behind a flag or config switch.

============================================================
4) P0-3 — Triage scoring workflow prompt
============================================================
Role: backend-engineer
Priority: P0
Problem
- The analyzer needs a deterministic scoring model to rank bookmarks for actionability.

Scope
- Implement deterministic scoring and reason codes.
- Add threshold and fixture tests.
- Ensure stable ordering on repeated runs.

Non-goals
- No ML ranking.
- No opaque learned weights.
- No cross-bookmark knowledge graph.

Inputs
- Current heuristic router behavior.
- Representative bookmark fixtures.

Outputs
- A score per item.
- Human-readable reason codes.
- Stable ordering across repeated runs.

Acceptance criteria
- Score output is deterministic for the same input.
- Reason codes explain why an item scored high or low.
- Threshold behavior is covered by tests.

Verification steps
- Run scoring twice and compare order.
- Check explainability for top-ranked and low-ranked items.
- Confirm threshold fixtures pass.

Risks
- Hidden drift in threshold tuning.
- Scores that are too coarse to be useful.

Rollback plan
- Fall back to the current heuristic router weights.
- Keep the new model behind a switch until proven.

============================================================
5) P0-4 — Project routing workflow prompt
============================================================
Role: backend-engineer
Priority: P0
Problem
- Scored bookmarks need to route into the right project buckets with minimal noise.

Scope
- Route items into primary project buckets.
- Preserve explanations and secondary-route rules.
- Add routing fixture tests.

Non-goals
- No auto-creation of new projects.
- No multi-hop project graph.
- No knowledge-graph routing.

Inputs
- Scored bookmark items.
- Existing opportunity router behavior.

Outputs
- Primary route assignment.
- Secondary-route rationale where needed.
- Fixture-tested routing rules.

Acceptance criteria
- Representative bookmarks route to the expected project buckets.
- Explanations are preserved.
- Noise and over-routing are limited.

Verification steps
- Run routing fixtures on representative bookmark samples.
- Check that explanations survive the route.
- Confirm secondary routes only appear when justified.

Risks
- Over-routing into too many buckets.
- Routes becoming unstable as rules evolve.

Rollback plan
- Collapse to a single primary route.
- Revert to opportunity-router behavior if the new routing is noisy.

============================================================
6) P0-5 — Learning note output workflow prompt
============================================================
Role: backend-engineer
Priority: P0
Problem
- The analyzer needs a human-readable learning note that is actionable, short, and easy to review.

Scope
- Add a markdown note template and note writer.
- Cover dedupe-by-id behavior.
- Preserve source URL, author, and project bucket.

Non-goals
- No long-form essay generation.
- No content marketing output.
- No dashboard dependency.

Inputs
- Routed bookmark items.
- Existing opportunity memo behavior.

Outputs
- A concise learning note artifact.
- Round-trippable metadata: source URL, author, project bucket.

Acceptance criteria
- The note is readable and short.
- The note can be traced back to the source item.
- Duplicate notes are avoided when the same item is seen again.

Verification steps
- Render a note from a known bookmark.
- Confirm metadata round-trips.
- Confirm the note is not duplicative across repeated runs.

Risks
- Notes becoming too verbose.
- Notes becoming too generic to be useful.

Rollback plan
- Fall back to the existing opportunity memo output if the new note format is too heavy.

============================================================
7) P0 value gate prompt
============================================================
Role: product-manager
Priority: P0
Problem
- The sprint needs an explicit go/no-go checkpoint before any P1 work starts.

Scope
- Evaluate whether the P0 slice is useful enough to unlock P1.
- Decide whether to proceed, tighten the MVP, or stop.

Non-goals
- No implementation work.
- No P1 dispatch unless the P0 slice proves value.

Inputs
- Output from P0-1 through P0-5.
- Real run evidence from the analyzer.

Outputs
- Unlock P1 or hold P1.
- Clear value judgment.

Acceptance criteria
- A bookmark can enter once, be deduped, scored, routed, and turned into a usable note.
- The output is something the user would actually read or act on.

Verification steps
- Inspect the actual P0 outputs from a real run.
- Confirm the outputs are useful without extra manual cleanup.
- Confirm the value decision is based on evidence, not enthusiasm.

Risks
- Unlocking P1 too early.
- Misreading technical completeness as product value.

Rollback plan
- Keep P1 parked.
- Tighten the MVP if the P0 slice is not yet useful.

============================================================
P1 park notice
============================================================
Do not dispatch these until the value gate passes:
- Content idea output
- Weekly digest
- Metrics dashboard

Reminder
- Keep the sprint flat and bounded.
- Prefer deterministic IDs and flat artifacts.
- No giant knowledge graph before value is proven.
