# TikTok Saved Recipe Intake Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` for task-by-task execution or `executing-plans` for inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only TikTok saved/favorites processor that produces local recipe, tip, digest, grocery, and run summary artifacts for Marcus's family use.

**Source of Truth:** `docs/superpowers/specs/2026-05-25-tiktok-saved-recipe-intake-design.md`

**Architecture:** Add a separate TikTok processor script that reuses the existing Playwright/Docker/browser-profile patterns. Keep live TikTok scraping isolated from pure deterministic transforms so unit tests can validate normalization, classification, card generation, and report output without an authenticated TikTok session.

**Tech Stack:** Python 3, Playwright async API, Docker Compose browser-agent container, pytest via `scripts/run_tests.py`, local JSONL/JSON/Markdown outputs under `/app/output/tiktok/`.

**Verification Strategy:** Add deterministic unit tests in `tasks/test_tiktok_saves.py`, run narrow pytest for that file, then run the canonical Docker test suite and source-to-live dry-run.

**Approval Source:** Marcus said "Yes proceed" after approving the recipe-first TikTok workflow direction.

---

## Hard Gates

- Scope is one coherent slice: read-only TikTok saved/favorites intake and local artifacts.
- No TikTok mutation mode is introduced.
- Existing browser-agent Docker/test/sync patterns are reused.
- Live extraction remains attended/auth-dependent; tests must not require TikTok login.

## File Map

- Create: `scripts/process_tiktok_saves.py`
  - Responsibility: TikTok profile browser launch, safe saved/favorites extraction, deterministic normalization/classification, artifact generation, CLI entry point.
  - Used by: operator command, future Hermes wrapper, tests via imported pure functions.

- Create: `tasks/test_tiktok_saves.py`
  - Responsibility: deterministic tests for URL normalization, hashtag extraction, record normalization, recipe/tip classification, card generation, digest/grocery rendering, and expected auth-state summary behavior.
  - Used by: `scripts/run_tests.py`.

- Modify: `README.md`
  - Current responsibility: browser-agent operator guide for Docker, VNC login, X auth/bookmark safety, tests, and sync.
  - Planned change: add TikTok attended login and read-only saved/favorites runbook.

## Task 1: Deterministic TikTok transforms

**Purpose:** Create pure, tested helpers before touching live browser scraping.

**Files:**
- Create: `scripts/process_tiktok_saves.py`
- Create: `tasks/test_tiktok_saves.py`

**Acceptance Criteria:**
- [ ] TikTok URLs canonicalize to stable video URLs when an ID is present.
- [ ] Hashtags extract from captions as lowercase strings without `#`.
- [ ] Recipe/tip classification follows the design signal rules.
- [ ] Recipe cards and tip cards have the required output fields.
- [ ] Tests run without launching a browser or requiring TikTok auth.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_tiktok_saves.py` with tests named:

```python
def test_canonicalize_tiktok_url_keeps_video_id(): ...
def test_extract_hashtags_lowercases_without_hash(): ...
def test_classify_record_prefers_recipe_when_food_signals_exist(): ...
def test_classify_record_routes_non_food_advice_to_tip(): ...
def test_build_recipe_card_contains_family_fields(): ...
def test_build_tip_card_contains_actionable_fields(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
FAIL because scripts/process_tiktok_saves.py does not exist or required helper functions are missing.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/process_tiktok_saves.py` with these pure helpers:

```python
RECIPE_WORDS = {...}
TIP_WORDS = {...}
RECIPE_HASHTAGS = {...}

def canonicalize_tiktok_url(url: str) -> str: ...
def stable_record_id(record: dict) -> str: ...
def extract_hashtags(text: str) -> list[str]: ...
def classify_record(record: dict) -> dict: ...
def build_recipe_card(record: dict, classification: dict) -> dict: ...
def build_tip_card(record: dict, classification: dict) -> dict: ...
```

Keep LLM-dependent fields empty or confidence `low` when source text lacks ingredients/steps. Do not add browser code in this task beyond imports needed by later tasks.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
PASS for the deterministic helper tests.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
```

Expected:

```text
PASS for all browser-agent tests.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add scripts/process_tiktok_saves.py tasks/test_tiktok_saves.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add tiktok saved item transforms"
```

## Task 2: Artifact writers and summaries

**Purpose:** Produce local output files that are useful even before live TikTok scraping is perfect.

**Files:**
- Modify: `scripts/process_tiktok_saves.py`
- Modify: `tasks/test_tiktok_saves.py`

**Acceptance Criteria:**
- [ ] Writer creates `raw_saves.jsonl`, `recipes.jsonl`, `tips.jsonl`, `weekly_digest.md`, `grocery_list.md`, and `run_summary.json` under a supplied output directory.
- [ ] Writer creates parent directories.
- [ ] Summary includes `status`, processed counts, recipe count, tip count, partial/error count, and collected timestamp.
- [ ] Digest includes recipe and tip sections.
- [ ] Grocery output groups ingredient-like strings by category when known and keeps unknowns in `other`.

- [ ] **Step 1: Write the failing test**

Extend `tasks/test_tiktok_saves.py` with tests named:

```python
def test_write_artifacts_creates_expected_files(tmp_path): ...
def test_render_weekly_digest_includes_recipe_and_tip_sections(): ...
def test_render_grocery_list_groups_unknown_items_under_other(): ...
def test_build_run_summary_counts_statuses(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
FAIL because artifact writer and render functions are missing.
```

- [ ] **Step 3: Implement the minimal change**

Add these functions to `scripts/process_tiktok_saves.py`:

```python
def render_weekly_digest(recipes: list[dict], tips: list[dict], summary: dict) -> str: ...
def render_grocery_list(recipes: list[dict]) -> str: ...
def build_run_summary(raw_records: list[dict], recipes: list[dict], tips: list[dict], status: str) -> dict: ...
def write_jsonl(path: Path, rows: list[dict]) -> None: ...
def write_artifacts(output_dir: Path, raw_records: list[dict], recipes: list[dict], tips: list[dict], status: str = "ok") -> dict: ...
```

Use `ensure_ascii=False` JSON output and never write secrets or full page HTML.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
PASS for transform and artifact tests.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
```

Expected:

```text
PASS for all browser-agent tests.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add scripts/process_tiktok_saves.py tasks/test_tiktok_saves.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: write tiktok recipe artifacts"
```

## Task 3: Read-only Playwright extraction CLI

**Purpose:** Add the live browser runner while preserving read-only behavior and auth-state reporting.

**Files:**
- Modify: `scripts/process_tiktok_saves.py`
- Modify: `tasks/test_tiktok_saves.py`

**Acceptance Criteria:**
- [ ] CLI defaults to `--dry-run` and has no execute/mutation option.
- [ ] CLI accepts `--profile`, `--max`, `--output-dir`, and `--headless`.
- [ ] Missing login can be represented as `requires_user` and writes a summary artifact.
- [ ] Extraction helpers avoid clicking mutation controls.
- [ ] Browser-dependent code is isolated so unit tests can mock it.

- [ ] **Step 1: Write the failing test**

Extend `tasks/test_tiktok_saves.py` with tests named:

```python
def test_parse_args_defaults_to_dry_run_and_tiktok_profile(): ...
def test_parse_args_exposes_no_execute_flag(): ...
def test_requires_user_summary_written_when_auth_missing(tmp_path): ...
def test_normalize_visible_video_card_builds_raw_record(): ...
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
FAIL because CLI parser, auth-state handler, and visible card normalizer are missing.
```

- [ ] **Step 3: Implement the minimal change**

Add CLI/browser functions to `scripts/process_tiktok_saves.py`:

```python
DEFAULT_PROFILE = "tiktok-profile"
DEFAULT_OUTPUT_DIR = Path("/app/output/tiktok")

def build_parser() -> argparse.ArgumentParser: ...
def normalize_visible_video_card(card: dict, collected_at: str) -> dict: ...
async def extract_saved_items(page, max_items: int) -> list[dict]: ...
async def process_tiktok_saves(profile: str, output_dir: Path, max_items: int, headless: bool) -> dict: ...
async def main_async(argv: list[str] | None = None) -> int: ...
def main() -> int: ...
```

Implementation notes:

- Use `async_playwright().chromium.launch_persistent_context(user_data_dir=f"{PROFILE_DIR}/{profile}", headless=headless, args=["--no-sandbox"])`.
- Navigate only to TikTok profile/saved/favorites surfaces.
- Detect login-required screens by visible login text or missing authenticated navigation and write `status: requires_user`.
- Prefer collecting links, captions, handles, and hashtags from visible DOM. Do not click like/save/follow/comment/share/delete/message controls.
- Return `0` for expected `requires_user`; return non-zero only for unexpected code/infrastructure failure.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
PASS for CLI and extraction-seam tests.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
```

Expected:

```text
PASS for all browser-agent tests.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add scripts/process_tiktok_saves.py tasks/test_tiktok_saves.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add read-only tiktok saved extractor"
```

## Task 4: Operator documentation and sync verification

**Purpose:** Make the workflow usable safely from the homelab runtime.

**Files:**
- Modify: `README.md`
- Modify: `scripts/process_tiktok_saves.py`
- Modify: `tasks/test_tiktok_saves.py`

**Acceptance Criteria:**
- [ ] README documents attended TikTok login via VNC into `tiktok-profile`.
- [ ] README documents read-only dry-run command.
- [ ] README states that v0 performs no mutation and has no execute mode.
- [ ] Source-to-live dry-run is clean enough to review before apply.
- [ ] All tests pass.

- [ ] **Step 1: Write the failing test**

Add a README contract test to `tasks/test_tiktok_saves.py`:

```python
def test_readme_documents_tiktok_read_only_workflow(): ...
```

The test should read `README.md` and assert it mentions `process_tiktok_saves.py`, `tiktok-profile`, `--dry-run`, and `no execute mode` or equivalent explicit no-mutation wording.

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
FAIL because README does not document the TikTok workflow yet.
```

- [ ] **Step 3: Implement the minimal change**

Update `README.md` with a `TikTok Saved/Favorites Processor` section containing:

```text
Attended login:
cd /home/orchestrator/browser-agent && docker compose -f docker-compose.vnc.yml up -d
cd /home/orchestrator/browser-agent && docker exec -d browser-agent-vnc python3 /app/scripts/vnc_login_secure.py https://www.tiktok.com --profile tiktok-profile

Read-only run:
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/process_tiktok_saves.py --dry-run --max 50

Safety:
The v0 TikTok processor has no execute mode and does not like, favorite, save, follow, comment, share, delete, message, shop, publish, or schedule anything.
```

Adjust wording to match README style.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
```

Expected:

```text
PASS for TikTok tests including README contract.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
cd /home/orchestrator/repos/local/browser-agent && scripts/sync_to_live.sh --dry-run
```

Expected:

```text
All tests pass. Sync dry-run shows only expected source-to-live changes for TikTok processor, tests, and README.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add README.md scripts/process_tiktok_saves.py tasks/test_tiktok_saves.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "docs: document tiktok saved processor"
```

## Final Verification

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_tiktok_saves.py -q
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
cd /home/orchestrator/repos/local/browser-agent && scripts/sync_to_live.sh --dry-run
cd /home/orchestrator/repos/local/browser-agent && git status --short
```

Expected:

```text
TikTok tests pass. Full browser-agent tests pass. Sync dry-run is reviewable. Git status is clean after commits.
```

## Rollout Notes

- Do not schedule cron in this slice.
- Do not run live TikTok extraction until Marcus completes attended TikTok login into `profiles/tiktok-profile`.
- First live command after sync should be bounded:

```bash
cd /home/orchestrator/browser-agent && docker compose run --rm browser-agent scripts/process_tiktok_saves.py --dry-run --max 10
```

- Review `/home/orchestrator/browser-agent/output/tiktok/run_summary.json` before increasing max count.
- Only after the read-only loop works reliably should a future plan add weekly Telegram digests or deeper transcript extraction.

## Self-Review

- Every requirement from the design maps to a task.
- No mutation, cron, shopping, calendar, or publishing behavior is added.
- File paths are exact.
- Commands are exact and start with `cd /home/orchestrator/repos/local/browser-agent &&` for source verification.
- Tests are deterministic and do not require TikTok auth.
- Tasks are independently commit-sized.
- Implementation is intentionally v0 and avoids speculative abstractions.
