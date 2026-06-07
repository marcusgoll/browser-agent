# Hermes Agent OS Contract

This contract defines the minimum run shape for browser-agent task execution.
It keeps runs LLM-agnostic, reviewable, and safe to inspect without touching secrets.

## What a task run is

A task run is one isolated browser-agent execution that produces:
- a standardized proof bundle under `output/runs/<run_id>/proof.json`
- a standardized task result record under `output/runs/<run_id>/task-run.json`
- latest-pointer files at the output root for operator tooling

## Required proof fields

Every proof bundle must include:
- `run_id`
- `workflow`
- `platform`
- `profile`
- `started_at`
- `completed_at`
- `normalized_status`
- `reason`
- `sanitized_url`
- `title`
- `action_type`
- `next_action`
- `screenshots`
- `account_context`
- `secrets_policy`
- `proof_bundle_path`

Task-oriented runs should also include:
- `task_id`
- `worktree_path`
- `review_state`
- `runner_version`
- `sanitized_run_summary`

## Required result fields

Every task result record must include:
- `task_id`
- `proof_run_id`
- `proof_bundle_path`
- `proof_bundle`
- `task`
- `profile`
- `headless`
- `worktree_path`
- `review_state`
- `runner_version`
- `status`
- `sanitized_run_summary`
- `started_at`
- `completed_at`

## What is forbidden

Do not write any of the following into proof bundles or result records:
- cookies
- tokens
- session storage
- local storage
- saved passwords
- browser profile databases
- raw secret keys or secret-like metadata keys

If a field name looks secret-like, the proof helper rejects it.

## Clean vs blocked vs degraded

- Clean run: `normalized_status=completed`, `status=completed`
- Blocked run: execution was intentionally stopped before action; record why in `reason`
- Degraded run: execution finished but returned warnings or partial failure; keep the proof and result record, and make the degradation obvious in `status`, `reason`, and `sanitized_run_summary`

## How to read the JSON artifact

1. Start with `proof.json` for the run contract and safety state.
2. Use `task-run.json` for the agent-facing summary and worktree metadata.
3. Use the latest pointer files for quick operator inspection.
4. If a run failed, inspect the error field and rerun only after correcting the root cause.

## Operator rule

If a task needs a worktree, the worktree path must be explicit in the result record.
If a task needs a review gate, the review state must be explicit in the result record.
No silent fallbacks.
