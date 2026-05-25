# Browser Agent Readiness Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` for task-by-task execution or `executing-plans` for inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Productionize the browser agent's auth readiness, visual proof, and account/context safety foundation before expanding social publishing automation.

**Source of Truth:** Marcus approved the ROI sequence: 1) Auth readiness + session persistence monitor, 2) Visual proof bundles, 3) Account/context safety guard, 4) One-at-a-time approval dispatcher, 5) X approved-publish engine, 6) X bookmarks/opportunity extractor, 7) X reply opportunity queue, 8) LinkedIn approved-publish engine, 9) Daily operator brief, 10) Recorder/replay system.

**Architecture:** Treat the full ROI list as a roadmap, but implement the first coherent slice now: a shared read-only readiness/proof/safety layer used by all future write-capable workflows. Existing scripts already cover pieces of this (`scripts/social_auth_check.py`, `scripts/publish_x_approved.py`, `scripts/publish_linkedin_approved.py`, `scripts/process_bookmarks.py`), so this plan consolidates and hardens rather than creating parallel abstractions.

**Tech Stack:** Python 3.12, Playwright persistent Chromium profiles, Docker Compose, pytest, JSON run artifacts under `/home/orchestrator/browser-agent/output/`.

**Verification Strategy:** Use deterministic unit tests for classification/proof-bundle/account-context behavior, then run read-only browser auth checks in Docker for X, LinkedIn, and Reddit. Do not inspect cookies, localStorage, sessionStorage, saved passwords, token files, or browser profile databases.

**Approval Source:** Explicit user instruction via approved ROI sequence in this session.

---

## Scope Check

Proceeding with one plan: readiness foundation for items 1-3.

Split recommended for the remaining roadmap:
- Plan 2: one-at-a-time approval dispatcher and event log (item 4).
- Plan 3: X approved-publish engine hardening (item 5).
- Plan 4: X bookmark/opportunity extractor productionization (item 6).
- Plan 5: X reply opportunity queue and publisher hardening (item 7).
- Plan 6: LinkedIn approved-publish engine hardening (item 8).
- Plan 7: daily operator brief (item 9).
- Plan 8: recorder/replay system (item 10).

Reason for split: items 4-10 have independent workflows, risk levels, verification strategies, and live-write boundaries. Shipping items 1-3 first lowers risk for every later plan.

## Current State Found

- `/home/orchestrator/browser-agent` exists but is not a git repository. Commit steps below are retained as worker discipline, but execution must either initialize/relocate into a repo with approval or replace commit steps with a checkpoint report.
- `scripts/social_auth_check.py` already performs visible-state auth checks for X, LinkedIn, and Reddit.
- Existing auth statuses are `authenticated`, `login_required`, `mfa_or_challenge_required`, and `unknown`.
- Existing auth checks only capture screenshots when a state requires manual review.
- Existing publish scripts create ad hoc screenshots and JSON outputs but do not share a standard proof-bundle schema.
- `scripts/publish_x_approved.py` has a partial account-context check via `extract_handle()`.
- `scripts/publish_linkedin_approved.py` has LinkedIn composer safety logic but no common preflight context contract.
- `scripts/process_bookmarks.py` and related tests already support X bookmark opportunity extraction.
- Host-side pytest collection currently fails for `tasks/test_bookmark_actions.py` because host Python lacks `langchain_openai`; use Docker for full test verification or add dependency-isolated imports in a later plan.

## File Map

- Create: `scripts/proof_bundle.py`
  - Responsibility: Create structured run directories, write JSON metadata, capture screenshots, sanitize URLs, and record non-secret proof artifacts.
  - Used by: `scripts/social_auth_check.py`, future publishers, tests.

- Create: `scripts/account_context.py`
  - Responsibility: Extract visible account/platform context and validate it against expected platform/profile/account constraints without reading secrets.
  - Used by: auth checks and write-capable publishers.

- Modify: `scripts/social_auth_check.py`
  - Current responsibility: Read-only auth-state checks for X, LinkedIn, and Reddit.
  - Planned change: Normalize status vocabulary for monitor use, always emit a proof bundle, optionally compare with previous latest state, and write stable latest JSON outputs.

- Modify: `scripts/publish_x_approved.py`
  - Current responsibility: Publish one approved X post with exact text verification.
  - Planned change: Use shared account-context preflight and proof bundle helpers before any live write. Keep publishing behavior unchanged.

- Modify: `scripts/publish_linkedin_approved.py`
  - Current responsibility: Publish an approved LinkedIn packet with exact composer verification.
  - Planned change: Use shared account-context preflight and proof bundle helpers before any live write. Keep publishing behavior unchanged.

- Create: `scripts/browser_agent_status.py`
  - Responsibility: Read latest auth/proof outputs and print a concise terminal status report for operators and cron jobs.
  - Used by: manual ops, future daily operator brief.

- Test: `tasks/test_proof_bundle.py`
  - Covers: run ID creation, URL sanitization, metadata shape, screenshot path redaction boundaries, latest symlink/copy behavior if implemented.

- Test: `tasks/test_account_context.py`
  - Covers: platform/account context extraction from visible text/URLs and hard-stop decisions for account mismatch or ambiguous account state.

- Modify: `tasks/test_social_auth_check.py`
  - Covers: new status vocabulary mapping, proof-required semantics, latest-state output behavior through pure helper functions.

## Status Vocabulary Contract

Keep backward compatibility while exposing monitor-friendly normalized statuses:

- `authenticated`: profile is ready for read-only and approved write workflows.
- `requires_user`: MFA, passkey, OAuth consent, account challenge, or security verification needs Marcus.
- `expired`: login screen or unauthenticated state detected.
- `ambiguous`: visible state is not safe to classify.
- `infra_error`: navigation, browser startup, timeout, or dependency failure.

Existing statuses may remain internally, but JSON outputs must include `normalized_status` so cron/briefing code does not need platform-specific branching.

## Proof Bundle Contract

Each meaningful run writes a run directory or equivalent stable artifact containing:

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
- `action_type`: `read_only`, `approved_write`, or `blocked`
- `screenshots`: before/after/blocked paths when available
- `account_context`: visible account/org/handle fields only
- `next_action`
- `secrets_policy`: fixed string stating cookies/tokens/storage/browser DBs were not inspected

Screenshots are proof artifacts. They must not be posted to public channels automatically.

## Account Context Contract

Before any approved write, the caller must provide expected context:

- platform
- profile
- expected account handle/name when known
- expected URL/domain pattern
- action type
- item ID

The preflight must return:

- `ok: true` only when visible account context is present and matches expectations, or when expectations are explicitly absent and platform policy allows it.
- `ok: false` with reason `account_mismatch`, `account_ambiguous`, `domain_mismatch`, or `not_authenticated` otherwise.

No live-write script may click Submit/Post when preflight returns false.

---

### Task 1: Add Shared Proof Bundle Helper

**Purpose:** Standardize audit artifacts before adding more automation.

**Files:**
- Create: `scripts/proof_bundle.py`
- Test: `tasks/test_proof_bundle.py`

**Acceptance Criteria:**
- [ ] A helper can create a deterministic run metadata object with no secrets.
- [ ] URLs are sanitized before storage.
- [ ] Metadata JSON includes the proof bundle contract fields.
- [ ] Helper works without Playwright so unit tests are fast.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_proof_bundle.py` with tests named:

```python
def test_proof_bundle_metadata_sanitizes_urls_and_records_policy(): ...
def test_proof_bundle_writes_json_under_output_runs(): ...
def test_proof_bundle_rejects_secret_like_metadata_keys(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_proof_bundle.py -q
```

Expected:

```text
FAIL because scripts/proof_bundle.py does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/proof_bundle.py` with:

```python
SECRET_KEY_PATTERNS = ("cookie", "token", "localstorage", "sessionstorage", "password", "secret")
SECRETS_POLICY = "visible browser state only; cookies/tokens/storage/passwords/browser databases not inspected"

def sanitize_url(url: str) -> str: ...
def build_run_id(workflow: str, platform: str | None = None, item_id: str | None = None) -> str: ...
def assert_no_secret_keys(data: dict) -> None: ...
def build_metadata(...): ...
def write_metadata(output_dir: Path, metadata: dict, latest_name: str | None = None) -> Path: ...
```

Use only stdlib. Do not import Playwright.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_proof_bundle.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/proof_bundle.py tasks/test_proof_bundle.py
cd /home/orchestrator/browser-agent && git commit -m "feat: add browser proof bundle helper"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

### Task 2: Normalize Auth Monitor Outputs

**Purpose:** Make auth checks suitable for cron/watchdog use and future daily brief ingestion.

**Files:**
- Modify: `scripts/social_auth_check.py`
- Modify: `tasks/test_social_auth_check.py`

**Acceptance Criteria:**
- [ ] Auth result JSON includes `normalized_status`.
- [ ] `mfa_or_challenge_required` maps to `requires_user`.
- [ ] `login_required` maps to `expired`.
- [ ] `unknown` maps to `ambiguous`.
- [ ] Auth check writes a stable latest JSON when `--json-out` is not provided and output directory is available.
- [ ] Auth check exits `0` for expected user-action states when invoked with monitor mode, but still exits non-zero for explicit one-shot checks unless existing callers require otherwise.

- [ ] **Step 1: Write the failing test**

Modify `tasks/test_social_auth_check.py` and add tests named:

```python
def test_normalize_status_for_monitor_vocabulary(): ...
def test_build_auth_result_includes_normalized_status_and_policy(): ...
def test_default_latest_output_path_is_platform_scoped(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py -q
```

Expected:

```text
FAIL because normalized status helpers/result builder do not exist.
```

- [ ] **Step 3: Implement the minimal change**

Modify `scripts/social_auth_check.py`:

```python
NORMALIZED_STATUS = {
    AUTHENTICATED: "authenticated",
    LOGIN_REQUIRED: "expired",
    MFA_OR_CHALLENGE_REQUIRED: "requires_user",
    UNKNOWN: "ambiguous",
}

def normalize_status(status: str) -> str:
    return NORMALIZED_STATUS.get(status, "infra_error")
```

Refactor result creation into a pure helper so tests do not launch a browser. Add `--monitor-mode` if exit behavior needs to distinguish cron from one-shot CLI.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/social_auth_check.py tasks/test_social_auth_check.py
cd /home/orchestrator/browser-agent && git commit -m "feat: normalize browser auth readiness status"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

### Task 3: Add Account Context Preflight

**Purpose:** Prevent correct actions from running in the wrong account, platform, or browser profile.

**Files:**
- Create: `scripts/account_context.py`
- Test: `tasks/test_account_context.py`

**Acceptance Criteria:**
- [ ] Preflight accepts visible account context and expected constraints.
- [ ] Preflight blocks account mismatch.
- [ ] Preflight blocks ambiguous account state for approved writes.
- [ ] Preflight blocks domain mismatch.
- [ ] Module contains no cookie/token/storage/database access.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_account_context.py` with tests named:

```python
def test_preflight_allows_matching_x_context(): ...
def test_preflight_blocks_account_mismatch(): ...
def test_preflight_blocks_ambiguous_write_context(): ...
def test_preflight_blocks_domain_mismatch(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_account_context.py -q
```

Expected:

```text
FAIL because scripts/account_context.py does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/account_context.py` with pure functions first:

```python
def extract_handle_from_visible_text(text: str) -> str | None: ...
def domain_matches(url: str, allowed_domains: list[str]) -> bool: ...
def validate_preflight(context: dict, expected: dict, action_type: str) -> dict: ...
```

Do not add browser automation in this task. Keep browser-specific extraction inside callers or a later helper once the pure policy is tested.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_account_context.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py tasks/test_account_context.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/account_context.py tasks/test_account_context.py
cd /home/orchestrator/browser-agent && git commit -m "feat: add browser account context preflight"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

### Task 4: Wire Proof Bundles Into Auth Checks

**Purpose:** Every auth readiness run should leave operator-readable proof without requiring manual screenshot hunting.

**Files:**
- Modify: `scripts/social_auth_check.py`
- Modify: `tasks/test_social_auth_check.py`

**Acceptance Criteria:**
- [ ] Every auth run writes proof metadata.
- [ ] Screenshots are captured for blocked/ambiguous states and optionally for authenticated states when `--proof-screenshot` is set.
- [ ] Latest output path remains stable per platform.
- [ ] JSON does not include raw visible body text.

- [ ] **Step 1: Write the failing test**

Add tests to `tasks/test_social_auth_check.py` named:

```python
def test_auth_result_omits_raw_body_text(): ...
def test_auth_result_references_proof_bundle_path(): ...
def test_blocked_state_requires_screenshot_in_proof_bundle(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py -q
```

Expected:

```text
FAIL because proof bundle path/result fields are missing.
```

- [ ] **Step 3: Implement the minimal change**

Modify `check_platform_auth()` to create proof metadata after classification and before returning. Keep screenshots viewport-only. Do not store raw body text in JSON.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run Docker read-only auth checks**

Run:

```bash
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py x --monitor-mode --json-out /app/output/social-auth-x-latest.json
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py linkedin --monitor-mode --json-out /app/output/social-auth-linkedin-latest.json
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py reddit --monitor-mode --json-out /app/output/social-auth-reddit-latest.json
```

Expected:

```text
Each command exits 0 for authenticated/requires_user/expired/ambiguous expected monitor states, non-zero only for infra_error. Each writes JSON with normalized_status and proof bundle metadata.
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/social_auth_check.py tasks/test_social_auth_check.py
cd /home/orchestrator/browser-agent && git commit -m "feat: write proof bundles for auth readiness checks"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

### Task 5: Enforce Account Context In Existing Publishers

**Purpose:** Apply the safety guard to existing live-write scripts without changing their publishing behavior.

**Files:**
- Modify: `scripts/publish_x_approved.py`
- Modify: `scripts/publish_linkedin_approved.py`
- Test: `tasks/test_account_context.py`

**Acceptance Criteria:**
- [ ] X publisher blocks before composing when visible account context mismatches expected handle.
- [ ] LinkedIn publisher blocks before composing when context is ambiguous or domain mismatches.
- [ ] Both publishers include preflight result in JSON output.
- [ ] Both publishers write proof metadata for blocked and published outcomes.
- [ ] No test performs a live post.

- [ ] **Step 1: Write the failing test**

Extend tests with pure policy coverage and import-safe smoke tests:

```python
def test_x_publish_preflight_result_shape_blocks_mismatch(): ...
def test_linkedin_publish_preflight_result_shape_blocks_ambiguous_context(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_account_context.py -q
```

Expected:

```text
FAIL because publisher-facing preflight helpers are not wired.
```

- [ ] **Step 3: Implement the minimal change**

Modify publishers to accept optional expected context flags:

```text
--expected-handle <handle>
--expected-account-name <name>
```

Before composing, call shared preflight using visible URL/title/body/account markers. Return JSON `status: blocked` and reason without clicking composer if validation fails.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_account_context.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py tasks/test_account_context.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/publish_x_approved.py scripts/publish_linkedin_approved.py tasks/test_account_context.py
cd /home/orchestrator/browser-agent && git commit -m "feat: enforce account preflight for browser publishers"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

### Task 6: Add Terminal Status Report

**Purpose:** Give Marcus and cron jobs one concise readiness report without reading raw JSON.

**Files:**
- Create: `scripts/browser_agent_status.py`
- Test: `tasks/test_browser_agent_status.py`
- Modify: `README.md`

**Acceptance Criteria:**
- [ ] CLI reads latest auth JSON files and prints compact status lines.
- [ ] Missing latest files are reported as `missing`, not stack traces.
- [ ] Output includes platform, profile, normalized status, age, reason, and next action.
- [ ] README documents the command and status meanings.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_browser_agent_status.py` with tests named:

```python
def test_status_report_summarizes_latest_auth_files(): ...
def test_status_report_handles_missing_latest_files(): ...
def test_status_report_does_not_print_secret_fields(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_browser_agent_status.py -q
```

Expected:

```text
FAIL because scripts/browser_agent_status.py does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/browser_agent_status.py` with pure formatter functions and CLI:

```bash
python3 scripts/browser_agent_status.py --output-dir /home/orchestrator/browser-agent/output
```

In Docker:

```bash
docker compose run --rm browser-agent scripts/browser_agent_status.py --output-dir /app/output
```

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_browser_agent_status.py -q
```

Expected:

```text
PASS
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py tasks/test_account_context.py tasks/test_browser_agent_status.py -q
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/browser_agent_status.py --output-dir /app/output
```

Expected:

```text
PASS. Status CLI prints concise platform lines and no secrets.
```

- [ ] **Step 6: Commit or checkpoint**

```bash
cd /home/orchestrator/browser-agent && git status --short
cd /home/orchestrator/browser-agent && git add scripts/browser_agent_status.py tasks/test_browser_agent_status.py README.md
cd /home/orchestrator/browser-agent && git commit -m "feat: add browser agent readiness status report"
```

Expected:

```text
If still not a git repository, skip commit and record a checkpoint with changed files and test output.
```

## Final Verification

Run:

```bash
cd /home/orchestrator/browser-agent && python3 -m pytest tasks/test_social_auth_check.py tasks/test_proof_bundle.py tasks/test_account_context.py tasks/test_browser_agent_status.py -q
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py x --monitor-mode --json-out /app/output/social-auth-x-latest.json
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py linkedin --monitor-mode --json-out /app/output/social-auth-linkedin-latest.json
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/social_auth_check.py reddit --monitor-mode --json-out /app/output/social-auth-reddit-latest.json
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/browser_agent_status.py --output-dir /app/output
```

Expected:

```text
Unit tests pass. Docker auth checks produce normalized latest JSON and proof metadata. Status CLI prints a concise report. No cookies, tokens, storage, saved passwords, browser databases, or token stores are inspected or printed.
```

## Rollout Notes

- This plan is read-only except for existing approved publisher preflight guards. Do not perform live social writes during verification.
- If cron jobs call `social_auth_check.py`, switch them to `--monitor-mode` after verifying exit-code behavior.
- Existing output files under `/home/orchestrator/browser-agent/output/` should be preserved.
- Browser profile permissions should remain restricted; this plan does not modify profile ownership or cookie stores.
- Because `/home/orchestrator/browser-agent` is not currently a git repository, execution should either:
  - initialize/move it into a repo after explicit approval, or
  - use checkpoint reports instead of commits for this workspace.

## Self-Review

- Every requirement in items 1-3 maps to at least one task.
- Remaining ROI items are explicitly split into later plans.
- File paths are exact.
- Commands are exact and start with `cd /home/orchestrator/browser-agent &&`.
- Tests are deterministic and avoid live posting.
- The plan avoids inspecting secrets and browser databases.
- Existing scripts are reused rather than replaced.
- No implementation work is included in this plan.

## Execution Handoff

Recommended execution mode: Inline Execution for Task 1-2, then Subagent-Driven for Tasks 3-6 if desired.

Reason: this workspace is not a git repository, so task-by-task commits are currently blocked. Inline execution lets us checkpoint carefully until repo ownership is resolved. Once the workspace is repo-backed, subagent-driven execution is safer for independent tasks.
