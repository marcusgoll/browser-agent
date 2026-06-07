# X Bookmark Learning Analyzer — Kanban + Factory Delegation Plan

Goal: upgrade the X Bookmark Learning Analyzer in one MVP-first sprint without turning it into a giant knowledge graph.

Source of truth:
- /home/orchestrator/repos/local/browser-agent/scripts/process_bookmarks.py
- /home/orchestrator/repos/local/browser-agent/scripts/feed_to_agents.py
- /home/orchestrator/repos/local/browser-agent/scripts/weekly_bookmark_digest.py
- /home/orchestrator/repos/local/browser-agent/tasks/test_bookmark_actions.py
- /home/orchestrator/repos/local/browser-agent/tasks/test_bookmark_opportunities.py
- /home/orchestrator/repos/local/browser-agent/docs/ops/source-checkpoint.md

Existing pieces to reuse:
- process_bookmarks.py already produces bookmark_analysis_*.json and bookmark_summary_*.json
- feed_to_agents.py already produces routed opportunities and high-ROI operator task lists
- weekly_bookmark_digest.py already turns the latest summary into a digest artifact
- The current wrappers already support a safe dry-run / approved-execute split
- Tests already cover GraphQL mutations, opportunity routing, and high-ROI task shaping

Sprint rule:
- Ship the minimum useful pipeline first.
- No knowledge graph, entity graph, or cross-bookmark semantic network until the MVP proves value through use.
- Favor flat artifacts, deterministic IDs, and simple routing over clever abstraction.

Kanban shape:
- P0 cards are the factory input.
- Factory converts each P0 card into a bounded implementation workflow: implement -> test -> review -> verify.
- Keep each workflow narrow and single-purpose.
- Do not create one giant end-to-end card that mixes schema, caching, scoring, routing, notes, ideas, digesting, and metrics.

Dependency order:
1. Bookmark schema
2. Deduplication/caching
3. Triage scoring model
4. Project routing
5. Learning note output
6. Content idea output
7. Weekly digest
8. Metrics dashboard

Card map:
- P0: 1-5
- P1: 6-8

Factory rule for P0 cards:
- Each P0 card becomes a separate implementation workflow with its own test boundary and rollback note.
- The factory should not batch unrelated P0 work into a single mega-PR.
- A P0 card is done only when its artifact is stable, its tests pass, and the rollback path is documented.

Factory rule for P1 cards:
- Do not dispatch P1 cards until P0 cards show real value in dry-run / dogfood usage.
- P1 cards stay parked until the MVP proves that users actually consume the note/routing output.

Card 1 — Bookmark schema
Priority: P0
Problem: current bookmark analysis, routing, note, and digest artifacts are loosely coupled and will drift unless the contract is explicit.
Scope:
- Define the canonical bookmark record and derived artifact shapes for analysis, score, route, note, idea, digest, and metrics events.
- Add versioned schema fields and stable IDs.
- Keep the schema simple enough for flat JSON and markdown artifacts.
Non-goals:
- Knowledge graph construction
- Semantic entity resolution across the entire archive
- Database migration of historical artifacts beyond lightweight adapters
Inputs:
- Raw X bookmark payloads
- Existing bookmark_summary_*.json and bookmark_analysis_*.json files
- Existing route/digest outputs
Outputs:
- Canonical schema spec
- Versioned Python types / JSON schema / fixture examples
- Backward-compat adapter for current summary/analysis shapes
Acceptance criteria:
- One schema exists for raw bookmark, scored bookmark, routed item, learning note, content idea, digest row, and metric event.
- Schema version is explicit and persisted in every generated artifact.
- Legacy inputs can be normalized into the new schema without losing the source URL, source ID, author, or timestamp.
- Invalid or partial records fail validation loudly.
Verification steps:
- Add fixture-based tests for valid and invalid records.
- Round-trip a sample bookmark through normalize -> serialize -> parse.
- Confirm existing summary and analysis outputs can be adapted without manual editing.
Risks:
- Overfitting the schema to current outputs and making future fields awkward.
- Schema churn if hidden edge cases surface after rollout.
Rollback plan:
- Keep the legacy parser/adapters intact.
- If the new schema causes breakage, route generation can fall back to the old summary/analysis shapes while the schema stays versioned.

Card 2 — Deduplication/caching
Priority: P0
Problem: repeated bookmarks, repeated fetches, and repeated analysis waste time and make the output noisy.
Scope:
- Normalize URLs and bookmark identifiers.
- Add cache keys for fetched content, analysis results, and routing decisions.
- Deduplicate repeated items within a run and across runs.
- Preserve the first-seen source while suppressing duplicate downstream artifacts.
Non-goals:
- Global identity graph
- Cross-account person/entity merging
- Cache invalidation tied to a knowledge graph or embedding store
Inputs:
- Canonical bookmark schema
- Fetched page snippets / metadata
- Previous analysis outputs and cache records
Outputs:
- Cache-aware deduped candidate set
- Hit/miss counters
- Reuse of prior analysis where content and version match
Acceptance criteria:
- Identical bookmark inputs produce one downstream analysis record, not many.
- URL fragments and trivial tracking noise do not defeat dedupe.
- Cache reuse is deterministic and keyed by content version.
- Duplicate suppression is visible in run logs and metrics.
Verification steps:
- Unit tests for normalized URL dedupe.
- Regression test for repeated runs with the same bookmark set.
- Confirm the second run reuses cached results instead of re-fetching/re-analyzing everything.
Risks:
- Over-deduping distinct bookmarks that share a URL but differ in relevant content context.
- Stale cache entries hiding fresh content.
Rollback plan:
- Disable cache reuse and fall back to per-run analysis.
- Keep dedupe strictly on normalized URL plus content hash until more evidence exists.

Card 3 — Triage scoring model
Priority: P0
Problem: the analyzer needs a transparent way to decide what matters now versus what should be parked.
Scope:
- Score bookmarks for actionability, novelty, relevance to active projects, and confidence.
- Produce explicit reason codes for each score.
- Separate high-priority operator actions from research-only and knowledge-only items.
Non-goals:
- Train a learned ranking model in sprint 1
- Personalization beyond simple project weight rules
- Black-box scoring that cannot be explained in a fixture test
Inputs:
- Canonical bookmark schema
- Dedupe/cached records
- Active project keywords and current weighting rules
Outputs:
- Numeric score
- Priority bucket
- Reason codes
- Confidence / uncertainty flags
Acceptance criteria:
- Same input always produces the same score.
- Every scored item has a readable why/reason field.
- The model can explain why an item landed in immediate action, research, or knowledge promotion.
- Thresholds are documented and fixture-tested.
Verification steps:
- Add deterministic fixture tests with known expected scores.
- Verify score ordering is stable across repeated runs.
- Confirm a sample item can be traced from raw bookmark -> score -> reason code.
Risks:
- Heuristics over-optimizing for obvious keywords instead of true value.
- Thresholds becoming brittle as the bookmark mix changes.
Rollback plan:
- Fall back to the current heuristic router weights.
- Keep the score model behind a single function boundary so the scoring rule can be swapped back quickly.

Card 4 — Project routing
Priority: P0
Problem: scored bookmarks still need a destination that matches active workstreams.
Scope:
- Route items into project buckets such as browser-agent, wiki/skills, trading, logbook, ops, or general research.
- Emit one primary route and optional secondary route only when justified.
- Preserve source links and reasons for routing decisions.
Non-goals:
- Auto-creating downstream project tasks everywhere
- Routing based on graph traversal or multi-hop entity inference
- Large fan-out to many projects from one bookmark
Inputs:
- Scored bookmark items
- Active project registry / keyword map
- Existing route artifacts from feed_to_agents.py
Outputs:
- Route artifact with primary bucket, optional secondary bucket, and justification
- Operator-facing queue for follow-up actions
- Project-aligned note labels/tags
Acceptance criteria:
- Every routed item has one clear primary project destination.
- Routes are stable and explainable from the source text.
- No bookmark spawns a giant cascade of project targets.
- Items relevant to current browser-agent work are surfaced first.
Verification steps:
- Fixture tests for representative routes and edge cases.
- Confirm route output aligns with active project keyword priorities.
- Validate that deleted/low-value items do not leak into the routed queue.
Risks:
- Over-routing items into too many projects.
- Missing an important project because the keyword map is too narrow.
Rollback plan:
- Collapse secondary routes and keep a single primary route.
- Revert to the current opportunity router if project mapping proves noisy.

Card 5 — Learning note output
Priority: P0
Problem: the analyzer needs a durable human-readable artifact, not just scores and routes.
Scope:
- Generate concise learning notes from routed, high-value bookmarks.
- Use a stable note template with source, summary, why it matters, project fit, and next step.
- Keep notes short, actionable, and easy to review manually.
Non-goals:
- Long-form essays
- Knowledge graph pages
- Automated wiki rewriting beyond a simple note artifact
Inputs:
- Routed bookmark items
- Score/reason context
- Source URL and bookmark metadata
Outputs:
- Markdown learning note files
- Optional note index/manifest for later digesting
Acceptance criteria:
- Each note has a title, source link, summary, why-it-matters section, and action recommendation.
- Notes are deduped by canonical bookmark ID.
- Notes can be generated in dry-run mode without mutating external systems.
Verification steps:
- Snapshot test the note template on a small fixture set.
- Confirm notes round-trip source URL, author, and project bucket.
- Verify duplicates do not produce duplicate notes.
Risks:
- Notes becoming too verbose to skim.
- Notes drifting into speculative synthesis instead of concrete takeaways.
Rollback plan:
- Fall back to the current opportunity memo output if the note format is too heavy.
- Keep note generation as a separate writer so it can be disabled without breaking routing.

Card 6 — Content idea output
Priority: P1
Problem: some bookmarks are inspiration for future public writing, not immediate learning notes.
Scope:
- Convert selected notes into content ideas for X, LinkedIn, or blog posts.
- Capture hook, angle, audience, proof point, and call to action.
- Require a clear novelty check so the analyzer does not emit repetitive ideas.
Non-goals:
- Auto-publishing
- Thread scheduling
- Broad content calendar management
Inputs:
- Learning notes
- Routed bookmark items
- Project context and novelty signals
Outputs:
- Content idea cards / markdown files
- Optional queue for human approval
Acceptance criteria:
- Each idea is distinct from the underlying learning note.
- Ideas have a specific audience and publishing angle.
- Ideas can be rejected without affecting the note pipeline.
Verification steps:
- Fixture tests for idea extraction from 2-3 representative note types.
- Confirm a note can yield zero, one, or multiple ideas depending on novelty.
Risks:
- Content ideas turning into generic social copy.
- Duplicate ideas across similar bookmarks.
Rollback plan:
- Disable idea generation entirely while keeping note output and routing live.

Card 7 — Weekly digest
Priority: P1
Problem: weekly summary output should stitch the week together without introducing new analysis complexity.
Scope:
- Aggregate notes, routes, ideas, and top scores into a weekly digest.
- Reuse existing digest generation as much as possible.
- Keep the digest readable and stable enough to email or share.
Non-goals:
- New ranking logic
- Historical backfill engine
- A second opinion model for weekly synthesis
Inputs:
- Weekly learning notes
- Route artifacts
- Content ideas
- Existing bookmark_summary_*.json outputs
Outputs:
- Weekly digest markdown/text artifact
- Send-ready copy for email or messaging
Acceptance criteria:
- Digest summarizes what was processed, what was worth action, and what became durable knowledge.
- Digest is deterministic for the same input week.
- Digest uses existing outputs instead of recomputing the world.
Verification steps:
- Snapshot test a fixed week fixture.
- Confirm the digest includes counts and the top items from the week.
Risks:
- Digest becoming a second analytics system.
- Too much repetition of content already visible in notes.
Rollback plan:
- Revert to the current lightweight weekly_bookmark_digest.py behavior.
- Keep digest generation as a thin view over existing artifacts only.

Card 8 — Metrics dashboard
Priority: P1
Problem: the project needs proof of value, not just more output files.
Scope:
- Track processing volume, dedupe rate, cache hit rate, route distribution, note volume, idea volume, and digest generation frequency.
- Surface run-level status and trend counts over 7/30 days.
- Keep the dashboard simple and local-first.
Non-goals:
- Real-time OLAP
- A BI warehouse
- A knowledge graph visualization layer
Inputs:
- Run logs
- Summary/analysis/routing/note/digest artifacts
- Cache and validation events
Outputs:
- Metrics JSON
- A small dashboard or report page
- Trend summaries by project and by artifact type
Acceptance criteria:
- Dashboard shows enough to answer: is this analyzer producing useful work, and where is it wasting time?
- Metrics include at least processed, deduped, routed, note-generated, idea-generated, digest-generated, and cache-hit counts.
- Runs with failures are visible, not hidden.
Verification steps:
- Fixture test for metric aggregation.
- Render-check for the dashboard/report output.
- Confirm values reconcile with sample artifact counts.
Risks:
- Metrics becoming too complex before the MVP proves value.
- Dashboard copying the same noise the analyzer is supposed to reduce.
Rollback plan:
- Reduce metrics to a minimal run summary if the dashboard is too heavy.
- Keep raw artifact counts available even if the UI is removed.

Recommended factory execution order:
1. P0-1 schema
2. P0-2 dedupe/caching
3. P0-3 triage scoring
4. P0-4 project routing
5. P0-5 learning note output
6. Reassess value with real runs and operator review
7. Only then open P1-6 content ideas, P1-7 weekly digest, P1-8 metrics dashboard

Hard anti-scope guard:
- No giant knowledge graph before the MVP proves value.
- No embedding-heavy or entity-network rebuild unless the note and routing outputs are clearly useful in daily use.
- If the first sprint does not produce something the user would actually read or act on, stop and tighten the pipeline instead of adding more machinery.

Definition of success for the sprint:
- A bookmark can enter the system once, be deduped, scored, routed, and turned into a usable learning note.
- The factory can take the P0 cards and spin them into implementation workflows without mixing unrelated concerns.
- The output is useful enough that the next sprint can be justified by observed value, not by architectural enthusiasm.
