# Hermes Agent OS — Bookmark-Driven Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` for task-by-task execution or `executing-plans` for inline execution. Keep each task bite-sized and independently verifiable.

**Goal:** Turn the highest-signal bookmark themes into a practical Hermes operating layer: reusable agent OS conventions, a worktree-backed multi-agent loop, and a deterministic quality gate for taste/design so the system stays LLM-agnostic and reusable.

**Source of Truth:**
- /home/orchestrator/browser-agent/output/bookmark_summary_20260607_183850.json
- /home/orchestrator/browser-agent/output/bookmark_analysis_20260607_183850.json
- /home/orchestrator/repos/local/browser-agent/scripts/process_bookmarks.py
- /home/orchestrator/repos/local/browser-agent/scripts/run_task.py
- /home/orchestrator/repos/local/browser-agent/scripts/proof_bundle.py
- /home/orchestrator/repos/local/browser-agent/scripts/account_context.py
- /home/orchestrator/repos/local/browser-agent/scripts/approval_dispatcher.py
- /home/orchestrator/repos/local/browser-agent/scripts/social_voice_review.py
- /home/orchestrator/repos/local/browser-agent/scripts/browser_agent_status.py
- /home/orchestrator/repos/local/browser-agent/docs/superpowers/plans/2026-06-03-x-bookmark-learning-analyzer-kanban-factory-plan.md

**Architecture:** Implement this as three tightly-scoped slices, not one giant “agent OS” rewrite. First, codify the shared run contract and artifact shape so every agent run looks the same. Second, add a worktree-backed runner so each task has isolated code and clean review boundaries. Third, add a deterministic review gate for design/taste so screenshot-heavy or UI-heavy output is filtered before it reaches a human. Reuse existing browser-agent helpers where they already exist; do not fork new parallel abstractions unless the current files cannot carry the new contract cleanly.

**Tech Stack:** Python 3.12, Docker Compose, pytest, git worktrees, existing browser-agent scripts, local JSON/Markdown artifacts under `/home/orchestrator/browser-agent/output/`.

**Verification Strategy:**
- Add narrow pytest coverage for each new helper or contract change.
- Run the new tests in Docker Compose, not host Python.
- For any runner that mutates worktrees or artifacts, do one dry-run path and one real-path smoke test.
- Every write-capable path must emit a proof bundle and a status line that can be checked without inspecting secrets.

---

## Current State Found

- `scripts/run_task.py` already runs browser-use tasks, but it only emits a minimal JSON result and does not standardize task metadata, worktree context, or review gates.
- `scripts/proof_bundle.py` already exists, so there is a clean place to standardize run evidence instead of sprinkling screenshot/output logic across scripts.
- `scripts/account_context.py` already exists, so visible account/profile validation can be shared rather than reimplemented per workflow.
- `scripts/approval_dispatcher.py` already exists and already models a bounded approve/revise/later/reject flow.
- `scripts/social_voice_review.py` already exists and is a good deterministic pattern for non-LLM quality gates.
- `scripts/browser_agent_status.py` already exists and can become the operator-facing status surface for the new runner contract.
- The bookmark analyzer is already provider-agnostic, so this plan can assume the Hermes side needs similar portability and not another one-off provider lock-in.

---

## Scope Check

Proceed with one practical slice:
1. Shared agent OS contract and run bundle
2. Worktree-backed multi-agent task loop
3. Deterministic design/taste review gate

Non-goals for this plan:
- No new knowledge graph
- No embedding store
- No model training
- No full UI redesign
- No multi-repo orchestration
- No live social publishing changes

---

## File Map

- Create: `docs/ops/hermes-agent-os-contract.md`
  - Responsibility: canonical operator-facing contract for task runs, proof bundles, worktree isolation, review gates, and failure semantics.
  - Used by: `scripts/run_task.py`, `scripts/browser_agent_status.py`, future task runners, human operators.

- Modify: `scripts/proof_bundle.py`
  - Current responsibility: structured proof/run artifacts.
  - Planned change: add task-run fields for `task_id`, `worktree_path`, `review_state`, `runner_version`, and `sanitized_run_summary`.

- Modify: `scripts/account_context.py`
  - Current responsibility: visible account/context checks.
  - Planned change: expose a stricter public validator that can be called before any task execution that depends on a specific account, profile, or workspace.

- Modify: `scripts/run_task.py`
  - Current responsibility: run a browser-use task and store a result blob.
  - Planned change: accept structured task metadata, optional worktree path, optional proof-bundle output directory, and optional review gate hook; emit a stable JSON record that downstream tooling can parse.

- Create: `scripts/task_worktree_runner.py`
  - Responsibility: create a per-task git worktree, run the task in that worktree, capture proof artifacts, and cleanly remove or archive the worktree on completion.
  - Used by: operators, cron jobs, future delegated workers.

- Create: `scripts/design_review_gate.py`
  - Responsibility: deterministic taste/design review for screenshots, layout proofs, and agent-generated UI artifacts.
  - Used by: visual-heavy workflows, browser-based task runs, screenshot proof bundles.

- Modify: `scripts/browser_agent_status.py`
  - Current responsibility: summarize auth/proof outputs for operators.
  - Planned change: surface task-run status, worktree path, latest proof bundle, and review outcome alongside the existing readiness summary.

- Modify: `README.md`
  - Current responsibility: operator guide.
  - Planned change: add a short “Hermes agent OS” section that explains the new run contract, worktree runner, and review gate.

- Create: `tasks/test_task_worktree_runner.py`
  - Covers: worktree lifecycle, task metadata emission, safe cleanup, and failure-path behavior.

- Create: `tasks/test_design_review_gate.py`
  - Covers: deterministic pass/warn/fail output, screenshot metadata handling, and rejection of ambiguous or secret-like inputs.

- Modify: `tasks/test_proof_bundle.py`
  - Covers: new task-run proof fields, path sanitization, and stable artifact shape.

- Modify: `tasks/test_account_context.py`
  - Covers: stricter preflight account/context validation and failure reasons.

---

## Task 1: Canonical Hermes run contract

**Objective:** Define one shared run and proof contract so every agent task emits the same metadata, artifacts, and failure semantics.

**Files:**
- Create: `docs/ops/hermes-agent-os-contract.md`
- Modify: `scripts/proof_bundle.py`
- Modify: `scripts/run_task.py`
- Modify: `tasks/test_proof_bundle.py`

**Step 1: Write failing tests**

Add/extend fixture tests that assert a run record contains:
- `task_id`
- `worktree_path`
- `review_state`
- `runner_version`
- `sanitized_run_summary`
- `proof_bundle_path`
- `secrets_policy`

Also assert the proof bundle redacts or excludes secret-like material.

**Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent -m pytest tasks/test_proof_bundle.py -q
```

Expected:
- Fail until the new proof fields exist.

**Step 3: Implement the minimal change**

Add the new run fields in `scripts/proof_bundle.py` and thread the same metadata through `scripts/run_task.py`.

Keep the schema flat and boring. Do not add a generic event bus or nested abstraction.

**Step 4: Run the narrow test and confirm pass**

Run the same pytest command again.

Expected:
- Pass with the new proof fields and redaction rules.

**Step 5: Document the contract**

Write `docs/ops/hermes-agent-os-contract.md` with:
- what a task run is
- what proof is required
- what is forbidden
- how to read the JSON artifact
- how to tell the difference between a clean run, a blocked run, and a degraded run

---

## Task 2: Worktree-backed multi-agent task loop

**Objective:** Make each Hermes task run in its own isolated worktree so parallel work does not contaminate the main checkout.

**Files:**
- Create: `scripts/task_worktree_runner.py`
- Modify: `scripts/run_task.py`
- Modify: `scripts/browser_agent_status.py`
- Create: `tasks/test_task_worktree_runner.py`

**Step 1: Write failing tests**

Add tests for:
- creating a worktree path for a task ID
- refusing to reuse a dirty worktree
- cleaning up the worktree on success
- preserving the worktree on failure when requested for debugging
- emitting a stable task JSON summary

**Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent -m pytest tasks/test_task_worktree_runner.py -q
```

Expected:
- Fail until the worktree runner exists.

**Step 3: Implement the minimal change**

Create `scripts/task_worktree_runner.py` with the smallest possible interface:
- input: repo path, base branch, task id, optional keep-worktree flag
- output: task summary JSON and proof bundle path

Use plain git worktree commands. Do not invent a custom filesystem sandbox unless git worktrees cannot satisfy the requirement.

**Step 4: Wire it into the runner**

Teach `scripts/run_task.py` to accept structured metadata from the worktree runner and write a result record that includes the worktree path and task id.

**Step 5: Update operator status**

Teach `scripts/browser_agent_status.py` to print the latest task state in a compact form so operators can see:
- task id
- worktree path
- review state
- last proof path
- last failure reason if any

**Step 6: Run the narrow test and confirm pass**

Run the worktree tests again.

Expected:
- Worktree lifecycle and summary emission pass.

---

## Task 3: Deterministic taste/design review gate

**Objective:** Add a non-LLM quality gate for UI/taste-heavy outputs so agent-generated interfaces do not ship slop.

**Files:**
- Create: `scripts/design_review_gate.py`
- Modify: `scripts/proof_bundle.py`
- Create: `tasks/test_design_review_gate.py`
- Modify: `README.md`

**Step 1: Write failing tests**

Add tests for a deterministic review contract:
- pass for clear, specific, non-generic UI text
- warn for overly structured or generic hooks
- fail for hype language, engagement bait, or AI-signposting
- reject secret-like inputs or ambiguous screenshot references

**Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent -m pytest tasks/test_design_review_gate.py -q
```

Expected:
- Fail until the review gate exists.

**Step 3: Implement the minimal change**

Create `scripts/design_review_gate.py` as a pure deterministic rule engine, following the same spirit as `scripts/social_voice_review.py`:
- no LLM calls
- no rewrite
- only pass/warn/fail and reasons
- accept screenshot metadata or short UI copy snippets

**Step 4: Wire proof output**

Add the review gate result to the proof bundle so the task runner can show exactly why something was blocked or warned.

**Step 5: Update the operator docs**

Add a short README section explaining when to use the design review gate:
- screenshots
- landing pages
- browser UI changes
- generated copy that will be seen by humans

**Step 6: Run the narrow test and confirm pass**

Run the gate tests again.

Expected:
- Deterministic pass/warn/fail behavior with stable reasons.

---

## Task 4: End-to-end smoke test and operator closeout

**Objective:** Prove the three slices work together and leave the repo with a clean operator-readable contract.

**Files:**
- Modify: `docs/ops/hermes-agent-os-contract.md`
- Modify: `README.md`
- Modify: `scripts/browser_agent_status.py`

**Step 1: Run the combined tests**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent -m pytest tasks/test_proof_bundle.py tasks/test_account_context.py tasks/test_task_worktree_runner.py tasks/test_design_review_gate.py -q
```

Expected:
- All tests pass.

**Step 2: Run one smoke path**

Use the new worktree runner on a harmless local task that only emits a proof bundle and status record.

Expected:
- a valid proof bundle
- a clean status line
- no secret inspection
- no dirty worktree left behind unless debugging was explicitly requested

**Step 3: Close out the contract**

Make sure the README and contract doc explain:
- what the agent OS is
- how to run one task
- how to review the result
- how to stop the run
- what the failure modes mean

---

## Risks

- Worktree cleanup bugs could leave temporary checkouts behind.
- Proof bundles can drift if more fields are added ad hoc instead of through the shared contract.
- A design gate that is too aggressive will block useful output; a gate that is too weak will not prevent slop.
- Do not silently fall back to unstructured output when the new contract fails.

## Rollback Plan

- Keep `scripts/run_task.py` compatible with its current minimal mode until the new contract is proven.
- Make the worktree runner optional at first.
- Keep the design gate deterministic and isolated so it can be disabled without breaking task execution.
- If any new helper causes noisy failures, revert the helper first rather than diluting the contract.

## Success Criteria

- Every agent task emits a standardized proof bundle.
- Every task can run in an isolated git worktree.
- Every UI/taste-heavy artifact can be reviewed without an LLM.
- Operator status output shows the latest task state clearly.
- The implementation stays small, reusable, and LLM-agnostic.
