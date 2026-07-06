# X Bookmark Project Routing Contract

Approval Source: P0-4 kanban scope requires a minimal project-routing contract for the existing X bookmark opportunity router. This contract intentionally limits routing to deterministic, fixed project buckets and preserves the existing scored bookmark explanations.

## Objective

Add a small project-route layer to the existing X bookmark opportunity output so Marcus can see the most likely active project bucket for a bookmark-derived opportunity without creating projects, building a graph, or replacing the current opportunity sections.

## Existing State

Current bookmark analysis is produced by `scripts/process_bookmarks.py`:

- Full scored bookmark records are written to `/app/output/bookmark_analysis_*.json`.
- Summary records are written to `/app/output/bookmark_summary_*.json`.
- `summary.insights[]` contains `{author, insight, url}`.
- `summary.action_items[]` contains `{author, action, url}`.
- Analysis records include bookmark metadata plus LLM fields such as `folder`, `reason`, `insights`, `actionable`, `planned_action`, `planned_folder_name`, and `action_result`.
- Low-value/deleted records are identified by `folder == "delete"`, `deleted == true`, or `action_result.action == "delete"`.

Current opportunity routing is in `scripts/feed_to_agents.py`:

- `build_opportunity_router(summary, analysis, limit_per_section=5)` emits `immediate_actions`, `research_queue`, `knowledge_promotions`, and `skipped`.
- `_section_item(...)` creates existing scored opportunity items with `score` and `why` rationale.
- `render_opportunity_memo(routed, today)` renders those scored items and their `why` explanations.
- `build_high_roi_task_queue(...)` uses the existing opportunity sections; project routing must not silently turn routes into executable tasks.

## Non-goals / hard limits

Do not:

- Auto-create, rename, merge, archive, or delete projects.
- Create a multi-hop project graph, dependency graph, or related-project network.
- Add knowledge-graph routing, embeddings, vector search, cross-run memory expansion, or LLM rerouting.
- Route every bookmark. Noisy, ambiguous, folder-only, deleted, or low-signal records must remain unrouted.
- Replace `immediate_actions`, `research_queue`, `knowledge_promotions`, `score`, or `why` fields.
- Promote secondary routes into additional tasks without separate human-approved scope.

## Routing output contract

Add an optional top-level `project_routes` list to the routed opportunity JSON. Each route item must be derived from an existing summary insight URL and must preserve the existing opportunity explanation when available.

Required fields for each project route:

```json
{
  "author": "bookmark author handle or Unknown",
  "insight": "existing summary insight text",
  "action": "matching summary action text or empty string",
  "url": "bookmark URL",
  "folder": "existing bookmark folder key or null",
  "project": "primary fixed project bucket",
  "route_score": 0,
  "route_why": "deterministic explanation of matched route signals",
  "opportunity_score": 0,
  "opportunity_why": "preserved existing _section_item why text, or empty string",
  "secondary_routes": []
}
```

`project` must be one of the fixed buckets defined in code. Initial allowed buckets are:

- `hermes_agent`
- `trading_research`
- `devops_infrastructure`
- `knowledge_base`
- `product_design`
- `aviation_ops`
- `business_ops`

Adding or renaming buckets is a product decision because it changes downstream expectations. It should be handled by updating this contract and tests first.

## Rule order

Routing must run after normal opportunity scoring, not before it.

1. Build the existing opportunity router output exactly as before.
2. Build `actions_by_url` from `summary.action_items[]`.
3. Build `records_by_url` from `analysis[]`.
4. Build `opportunity_by_url` from the already-ranked opportunity sections so route items can copy `opportunity_score` and `opportunity_why`.
5. For each `summary.insights[]` item:
   - Skip when URL is missing.
   - Skip when matching analysis record is deleted/low-value.
   - Combine `insight + action` for deterministic keyword scoring.
   - Score against fixed project keyword rules only.
   - Apply folder bonus only as a small tie-strengthening signal after at least one project keyword matched.
   - If no project score crosses the primary threshold, emit no route.
   - Emit exactly one primary route when the top score crosses the threshold.
   - Consider at most one secondary route using the criteria below.
6. Sort route items by existing `opportunity_score` descending, then `route_score` descending, then URL for stable output.
7. Cap the route list (`limit=20` is sufficient for the current memo) so routing does not dominate the opportunity memo.

## Primary bucket selection

Primary selection is deterministic:

- Score each fixed bucket using whole-token keyword matches in the combined `insight + action` text.
- Add the existing bookmark folder bonus only when the bucket already has at least one matched keyword.
- Sort candidates by `score desc`, then `project asc` for stable ties.
- Emit the top candidate only when `score >= PROJECT_ROUTE_PRIMARY_MIN_SCORE`.
- If the top score is below threshold, emit no primary bucket.

Tie/noise handling:

- A folder alone must never route an item. Example: `folder=design` with generic "visual reference" text does not become `product_design` unless design-route keywords also match.
- Do not invent a `general`, `misc`, `uncategorized`, or `research` fallback project bucket.
- Low-signal single words with broad meaning should be weighted below the primary threshold unless paired with stronger terms.
- Deterministic ties use project-key alphabetical order only to keep output stable; they do not create multiple primaries.
- Deleted or low-value bookmarks remain excluded even if their text strongly matches a project.

## Secondary route criteria

Secondary routes are allowed only as supporting context for genuinely cross-functional bookmarks.

A secondary route may be emitted when all of these are true:

- The primary route already exists.
- The secondary is the next-highest fixed bucket after the primary.
- `secondary.score >= PROJECT_ROUTE_SECONDARY_MIN_SCORE`.
- The secondary has explicit matched keywords in the bookmark insight/action text; folder bonus can strengthen but cannot be the only reason.
- The route includes `project`, `score`, and a `why` string naming the matched keywords and any folder signal.
- At most one secondary route is emitted per bookmark.

Secondary routes must not:

- Spawn extra tasks.
- Change the primary bucket.
- Create project-to-project edges.
- Reclassify the bookmark's existing opportunity section.

## Explanation preservation

The route layer must preserve, not replace, the scored bookmark opportunity rationale.

- Existing opportunity items keep their `score` and `why` fields unchanged.
- Project route items add `route_score` and `route_why` for routing-specific rationale.
- Project route items copy the existing opportunity rationale into `opportunity_why` when the URL appears in an opportunity section.
- The memo should display both rationales when present: `route:` for routing rationale and `opportunity:` for existing opportunity rationale.
- If no matching opportunity section exists, `opportunity_why` may be empty, but the original opportunity sections still render normally.

## Rollback behavior

Routing must be easy to disable without affecting the existing opportunity memo/task workflow.

Accepted rollback paths:

- Remove or gate only the line that attaches `routed["project_routes"] = build_project_routes(...)`.
- Leave `build_opportunity_router` returning the prior fields: `generated_from`, `total_processed`, `action_summary`, `immediate_actions`, `research_queue`, `knowledge_promotions`, and `skipped`.
- `render_opportunity_memo` must tolerate missing or empty `project_routes` by rendering no routes or `- None` while still rendering existing opportunity sections.
- `build_high_roi_task_queue` must continue to read only the established opportunity sections unless a future approved contract changes task generation.

Rollback must not require changing `scripts/process_bookmarks.py`, deleting generated bookmark analysis files, or changing X bookmark actions.

## Representative examples

| Bookmark signal | Existing folder | Expected primary | Secondary | Why |
| --- | --- | --- | --- | --- |
| `Agent memory needs remember cite forget layers for persistent agents`; action: `Update agent memory docs and add tests for context compression` | `ai_tools` | `hermes_agent` | `knowledge_base` | Strong agent/memory/context/test keywords; knowledge/memory/layers justify one secondary. Preserve opportunity `why`. |
| `Autonomous financial research agent builds stock theses`; action: `Compare this finance agent to the Alpaca/Ross paper pipeline` | `ai_tools` | `trading_research` | none unless secondary crosses threshold | Trading/finance/stock/Alpaca/Ross outweigh generic agent terms. |
| `CSS custom easing functions improve transitions`; action: `Bookmark transition pattern for future UI projects` | `design` | `product_design` | none | CSS/transition/design keywords plus design folder bonus. |
| `A pleasant visual thread with no active project signal`; action: `Save only if a primary project rule matches` | `design` | no route | none | Folder-only/generic visual signal is noise; do not over-route. |
| `UX polishing gallery with attractive onboarding screens`; action: `Save as a visual reference only` | `design` | no route under this P0-4 contract | none | UX alone plus folder signal is intentionally below primary threshold unless stronger design/project terms appear. |
| `Unrealistic profit promise`; planned action delete | `delete` | no route | none | Deleted/low-value records are excluded. |

## Likely implementation targets

Expected code changes should stay small and local:

- `scripts/feed_to_agents.py`
  - Add fixed route rules and thresholds near existing opportunity keyword constants.
  - Add helpers for whole-token keyword matching, project score calculation, URL-to-opportunity lookup, and `build_project_routes(...)`.
  - Attach `project_routes` after existing section scoring in `build_opportunity_router(...)`.
  - Extend `render_opportunity_memo(...)` to show primary/secondary route rationale while preserving existing sections.
- `tasks/test_bookmark_opportunities.py`
  - Add fixture rows for strong project matches, folder-only noise, and deleted/low-value records.
  - Assert primary buckets, secondary route limit/justification, absence of fallback/general routes, and preservation of `opportunity_why`.

No changes are expected in `scripts/process_bookmarks.py` for P0-4 beyond using its existing output shape.

## Acceptance criteria for implementation

- Existing opportunity sections and their `score`/`why` explanations remain unchanged.
- `project_routes` is additive and optional.
- Primary route selection uses fixed deterministic bucket rules and a minimum score threshold.
- Folder bonus cannot route by itself.
- At most one secondary route is emitted and it has explicit justification.
- Deleted/low-value records never receive project routes.
- No project creation, graph routing, knowledge-graph routing, embeddings, or LLM rerouting is introduced.
- Unit tests cover primary buckets, over-routing prevention, explanation preservation, secondary-route limits, memo rendering, and rollback-tolerant missing/empty `project_routes` behavior.
- Canonical verification remains the repo test path documented in `README.md`: `docker compose run --rm browser-agent scripts/run_tests.py`.
