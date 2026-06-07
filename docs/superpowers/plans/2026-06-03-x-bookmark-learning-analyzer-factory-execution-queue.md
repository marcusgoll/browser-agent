# X Bookmark Learning Analyzer — Factory Execution Queue

Goal: convert the approved MVP plan into a dependency-gated factory queue where P0 cards become implementation workflows first, and P1 cards stay parked until MVP value is proven.

Source of truth:
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-kanban-factory-plan.md
- /home/orchestrator/repos/local/browser-agent/scripts/process_bookmarks.py
- /home/orchestrator/repos/local/browser-agent/scripts/feed_to_agents.py
- /home/orchestrator/repos/local/browser-agent/scripts/weekly_bookmark_digest.py
- /home/orchestrator/repos/local/browser-agent/tasks/test_bookmark_actions.py
- /home/orchestrator/repos/local/browser-agent/tasks/test_bookmark_opportunities.py

Profiles available on this machine:
- factory
- backend-engineer
- frontend-engineer
- pr-reviewer
- product-manager
- social-media-manager
- devops-engineer
- marcusgoll-content-growth

Queue policy:
- Factory owns decomposition and workflow synthesis.
- P0 cards are the only inputs the factory should dispatch immediately.
- Each P0 card becomes its own implementation workflow: implement -> test -> review -> verify.
- P1 cards are blocked behind a value gate and should not enter the active queue until the P0 slice proves useful in real runs.
- No knowledge graph or entity-network work in this sprint.

Dependency legend:
- `parent -> child` means the child stays blocked until the parent finishes.
- `value_gate` is the post-P0 decision point that unlocks P1 work only if MVP value is proven.

Factory intake and workflow synthesis
- FX-0 [factory]: synthesize the P0 implementation workflows from the approved plan
  - Purpose: convert the five P0 cards into bounded execution chains, confirm assignees, and enforce the MVP guard.
  - Output: ready-to-run workflow cards for schema, dedupe/caching, scoring, routing, and learning notes.

P0 workflows
1) Schema workflow
- FX-0 -> P0-1 [backend-engineer]: bookmark schema implementation
  - Child chain:
    - P0-1.1 [backend-engineer]: add canonical schema / versioned artifact shapes
    - P0-1.2 [backend-engineer]: add schema fixtures and validation tests
    - P0-1.3 [pr-reviewer]: review schema contract and rollback safety
    - P0-1.4 [backend-engineer]: verify round-trip compatibility with existing summary/analysis outputs
  - Rollback: keep legacy summary/analysis adapters active.

2) Deduplication and caching workflow
- FX-0 -> P0-2 [backend-engineer]: deduplication/caching implementation
  - Child chain:
    - P0-2.1 [backend-engineer]: normalize URLs and content hashes
    - P0-2.2 [backend-engineer]: add cache keys and reuse path for repeated analysis
    - P0-2.3 [backend-engineer]: add repeat-run regression tests
    - P0-2.4 [pr-reviewer]: review cache invalidation risk and duplicate suppression behavior
  - Rollback: disable cache reuse and fall back to per-run analysis.

3) Triage scoring workflow
- FX-0 -> P0-3 [backend-engineer]: triage scoring model implementation
  - Child chain:
    - P0-3.1 [backend-engineer]: implement deterministic scoring and reason codes
    - P0-3.2 [backend-engineer]: add score fixture tests and threshold assertions
    - P0-3.3 [pr-reviewer]: review explainability and threshold drift risk
    - P0-3.4 [backend-engineer]: verify stable ordering on repeated runs
  - Rollback: fall back to the current heuristic router weights.

4) Project routing workflow
- FX-0 -> P0-4 [backend-engineer]: project routing implementation
  - Child chain:
    - P0-4.1 [backend-engineer]: route items into primary project buckets
    - P0-4.2 [backend-engineer]: preserve explanations and secondary-route rules
    - P0-4.3 [backend-engineer]: add routing fixture tests for representative bookmarks
    - P0-4.4 [pr-reviewer]: review for over-routing and noise
  - Rollback: collapse to a single primary route and revert to opportunity-router behavior if needed.

5) Learning note output workflow
- FX-0 -> P0-5 [backend-engineer]: learning note output implementation
  - Child chain:
    - P0-5.1 [backend-engineer]: add markdown note template and note writer
    - P0-5.2 [backend-engineer]: add note fixture tests and dedupe-by-id coverage
    - P0-5.3 [pr-reviewer]: review note brevity, actionability, and dry-run safety
    - P0-5.4 [backend-engineer]: verify notes round-trip source URL, author, and project bucket
  - Rollback: fall back to the existing opportunity memo output if the note format is too heavy.

P0 value gate
- P0-VALUE-GATE [product-manager]: assess whether the P0 slice is useful enough to unlock P1
  - Parent: P0-1, P0-2, P0-3, P0-4, P0-5
  - Criteria: a bookmark can enter once, be deduped, scored, routed, and turned into a usable note; the output is something the user would actually read or act on.
  - Outcome: either unlock P1 or stop and tighten the MVP.

P1 workflows, parked behind value gate
6) Content idea output
- P0-VALUE-GATE -> P1-6 [marcusgoll-content-growth]: content idea output
  - Child chain:
    - P1-6.1 [marcusgoll-content-growth]: extract hook/angle/audience/proof point
    - P1-6.2 [marcusgoll-content-growth]: add novelty check and duplicate suppression tests
    - P1-6.3 [pr-reviewer]: review for generic-copy drift and publish-safety
  - Rollback: disable idea generation entirely and keep note/routing live.

7) Weekly digest
- P0-VALUE-GATE -> P1-7 [backend-engineer]: weekly digest aggregation
  - Child chain:
    - P1-7.1 [backend-engineer]: aggregate notes/routes/ideas into digest input
    - P1-7.2 [backend-engineer]: snapshot-test digest rendering against a fixed week
    - P1-7.3 [pr-reviewer]: review for determinism and repetition
  - Rollback: revert to the current lightweight weekly_bookmark_digest.py behavior.

8) Metrics dashboard
- P0-VALUE-GATE -> P1-8 [frontend-engineer]: metrics dashboard
  - Child chain:
    - P1-8.1 [backend-engineer]: emit metrics JSON for processed/deduped/routed/note/idea/digest/cache-hit counts
    - P1-8.2 [frontend-engineer]: render the small local-first dashboard/report page
    - P1-8.3 [pr-reviewer]: review for noise, missing failures, and proof-of-value visibility
  - Rollback: reduce to a minimal run summary if the dashboard is too heavy.

Execution order recommendation
1. FX-0 factory intake and workflow synthesis
2. P0-1 schema
3. P0-2 dedupe/caching
4. P0-3 triage scoring
5. P0-4 project routing
6. P0-5 learning note output
7. P0-VALUE-GATE decision
8. Only if value is proven: P1-6 content ideas, P1-7 weekly digest, P1-8 metrics dashboard

Hard guardrails
- No giant knowledge graph before value is proven.
- No entity-network rebuild, embedding-heavy reranking, or cross-bookmark semantic graph work in sprint 1.
- Keep every workflow bounded enough for a separate review and rollback.
- Prefer flat artifacts and deterministic IDs over speculative abstractions.
