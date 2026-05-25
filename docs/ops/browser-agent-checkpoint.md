# Browser Agent Ops Checkpoint

Date: 2026-05-24
Location: /home/orchestrator/browser-agent

## Scope decision

This workspace remains a live ops workspace for now instead of being moved under /home/orchestrator/repos in this change.

Reason:
- Cron jobs currently use absolute paths under /home/orchestrator/browser-agent.
- Browser profiles under profiles/ are credential-bearing runtime state and must not be moved casually or committed.
- output/ contains run artifacts consumed by downstream digest, wiki-sync, agent-feed, and public-web-followup jobs.
- Moving the workspace safely requires a dedicated migration with cron path updates, profile/output preservation, and post-move run verification.

## Current safety posture

- The scheduled X bookmark processor is report-only by default.
- Destructive move/delete execution is isolated to /home/orchestrator/.hermes/scripts/x-bookmark-processor-approved-execute.sh.
- Approved execute requires:
  - X_BOOKMARK_APPROVED_EXECUTE=1
  - X_BOOKMARK_APPROVAL_NOTE set to the human approval context
- The scheduled processor wrapper blocks attempts to enable execute mode via X_BOOKMARK_APPROVED_EXECUTE.
- Processor wrappers inspect the newest summary file and surface degraded action_summary.error counts.

## Canonical test command

Run tests inside Docker, not host Python:

```bash
cd /home/orchestrator/browser-agent
docker compose build browser-agent
docker compose run --rm browser-agent scripts/run_tests.py
```

Host pytest is not authoritative because host Python may not have browser-agent dependencies such as langchain_openai.

## Repo migration follow-up

A future repo-ization task should:

1. Create /home/orchestrator/repos/local/browser-agent or the chosen upstream repo location.
2. Keep profiles/ and output/ as runtime state, not committed source.
3. Add .gitignore entries for .env, profiles/, output/, __pycache__, and generated reports.
4. Update cron job workdir/script assumptions and all absolute paths.
5. Run the canonical Docker tests.
6. Run the dry-run processor and agent-feed wrappers after migration.
7. Only then retire the old /home/orchestrator/browser-agent path or replace it with a deliberate symlink.

## Minimal processor split plan

Do not split process_bookmarks.py until the safety gates above are stable. When ready, extract one seam at a time:

1. x_bookmark_graphql.py
   - GraphQL interception and bookmark extraction.
   - Tests for deleted/ghost tweets, author extraction, media/card/quoted tweet extraction.
2. x_bookmark_actions.py
   - Folder lookup/create, move, delete, apply action.
   - Tests for mutation payload shape and failed mutation handling.
3. bookmark_enrichment.py
   - Public URL and media enrichment with private-network blocking.
   - Tests for URL safety, byte/time bounds, and fallback behavior.
4. bookmark_analysis.py
   - Prompt/context construction and deterministic fallback analysis.
   - Tests for context shape and low-value/delete classification guardrails.
5. process_bookmarks.py
   - Thin CLI orchestration only.

Each extraction should preserve the existing CLI behavior and pass the canonical Docker test command before the next seam is touched.
