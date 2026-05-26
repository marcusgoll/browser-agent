# Hermes Chrome Sidebar Extension MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` for task-by-task execution or `executing-plans` for inline execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-only MVP Chrome side panel that pairs selected tabs with a narrow Python bridge, lets Hermes-style prompts inspect/scrape/fill selected pages, blocks final-submit actions, and writes non-secret run artifacts.

**Source of Truth:** `docs/superpowers/specs/2026-05-26-hermes-chrome-sidebar-extension-design.md`

**Architecture:** Implement the first slice in `browser-agent` as a standalone localhost Python bridge plus an unpacked Chrome extension under `chrome_extension/`. The bridge owns pairing, run IDs, policy validation, fake-Hermes/deterministic adapter plumbing, and artifacts; the extension owns side panel UI, selected-tab collection, content-script DOM summaries, and execution of bridge-validated page-local actions.

**Tech Stack:** Python 3, stdlib HTTP server, pytest, Playwright Python for content-script fixture tests, Chrome Manifest V3 side panel extension, vanilla JavaScript modules, local JSON/CSV/Markdown artifacts under `output/sidebar-runs/`.

**Verification Strategy:** Add policy and bridge pytest coverage, Playwright-backed content-script fixture tests, static extension tests, and a fake-run smoke test. Run narrow tests after each task, then run `docker compose run --rm browser-agent scripts/run_tests.py`, host Node syntax checks, and a source-to-live dry run.

**Approval Source:** Marcus approved the written spec and said "Approved and proceed".

---

## Planning Assumptions Chosen From Deferred Spec Questions

- Bridge transport for the MVP is localhost HTTP JSON bound to `127.0.0.1`; native messaging remains a later hardening option.
- The bridge is a standalone `browser-agent` Python process for the first slice, not a Hermes plugin and not a new repo.
- Pairing uses an operator-visible pairing code to mint an in-memory bearer token for the running bridge process.
- Hermes backend integration is represented by an adapter interface plus a deterministic `FakeHermesAdapter` for the first testable loop. Replacing that adapter with a real Hermes gateway call is a later task once the local contract is proven.
- Wiki/notes promotion is represented as a proposed action and local artifact metadata only. External writes are not performed in this MVP plan.

## Hard Gates

- Scope is one coherent slice: localhost bridge plus unpacked extension MVP with fake-Hermes adapter and local artifacts.
- The extension operates on user-selected tabs only.
- No all-tab access, network/API capture, cookie/storage/password inspection, final submit, social post, purchase, delete, MFA approval, or external publishing is introduced.
- The bridge fails closed for malformed output, unpaired requests, tab mismatch, URL/domain drift, blocked actions, secret-like fields, and ambiguous selectors.
- Tests do not require authenticated websites or a real Hermes gateway.

## File Map

- Create: `scripts/sidebar_bridge_contract.py`
  - Responsibility: Typed dictionaries/constants, action allowlist/blocklist, URL sanitization, selected-tab policy, action schema validation, field/action safety checks, artifact payload shaping.
  - Used by: `scripts/sidebar_bridge_server.py`, `tasks/test_sidebar_bridge_policy.py`, `tasks/test_sidebar_bridge_server.py`.

- Create: `scripts/sidebar_bridge_server.py`
  - Responsibility: Localhost HTTP bridge with `/health`, `/pair`, `/runs`, and `/runs/<run_id>/actions` endpoints; run state; fake-Hermes adapter; artifact writes under `output/sidebar-runs/`.
  - Used by: operator command, extension side panel, `tasks/test_sidebar_bridge_server.py`.

- Create: `chrome_extension/manifest.json`
  - Responsibility: Manifest V3 side panel extension declaration with minimal permissions for active tab, scripting, side panel, and localhost bridge access.
  - Used by: Chrome load-unpacked flow and static tests.

- Create: `chrome_extension/background.js`
  - Responsibility: Opens/enables the side panel and relays selected-tab inventory requests when needed.
  - Used by: Chrome extension runtime and static tests.

- Create: `chrome_extension/sidepanel.html`
  - Responsibility: Sidebar UI skeleton for bridge status, pairing, selected tabs, prompt input, plan/results, blocked actions, and artifact paths.
  - Used by: Chrome side panel.

- Create: `chrome_extension/sidepanel.css`
  - Responsibility: Terminal-like compact styling for the side panel.
  - Used by: `chrome_extension/sidepanel.html`.

- Create: `chrome_extension/sidepanel.js`
  - Responsibility: Pair with bridge, list selected/current tabs, request content summaries, submit runs, show plans/results, and dispatch validated actions to content scripts.
  - Used by: Chrome side panel and static tests.

- Create: `chrome_extension/content_script.js`
  - Responsibility: Extract structured DOM summaries and execute safe validated actions: fill fields, set selects, check checkboxes, non-final navigation clicks, copy display data.
  - Used by: Chrome tabs and Playwright fixture tests.

- Create: `chrome_extension/shared/action_contract.js`
  - Responsibility: Shared browser-side action constants, blocked-action labels, and defensive client-side action checks mirroring the bridge allowlist.
  - Used by: `sidepanel.js`, `content_script.js`, and static tests.

- Create: `tasks/test_sidebar_bridge_policy.py`
  - Covers: allowed/blocked action validation, selected-tab scope, URL/domain drift, secret-like target rejection, final-submit rejection, malformed Hermes output rejection, sanitized proof payloads.

- Create: `tasks/test_sidebar_bridge_server.py`
  - Covers: pairing flow, unpaired rejection, fake run creation, fake-Hermes proposal validation, artifact files, and blocked action reporting.

- Create: `tasks/test_sidebar_content_script.py`
  - Covers: Playwright fixture extraction for forms/tables/lists, field-label matching, safe fill execution, final-submit button blocking, and no password/token field filling.

- Create: `tasks/test_sidebar_extension_static.py`
  - Covers: manifest permission boundaries, side panel files present, localhost-only bridge URL default, no all-tab read behavior, and no submit/send/purchase/delete client actions.

- Modify: `scripts/run_tests.py`
  - Current responsibility: run all pytest tests under `tasks` inside Docker.
  - Planned change: no behavior change unless the new Playwright fixture test needs an environment variable default such as `PLAYWRIGHT_BROWSERS_PATH`; prefer leaving this file unchanged.

- Modify: `README.md`
  - Current responsibility: operator guide for browser-agent Docker, profiles, VNC, tests, and safety notes.
  - Planned change: add Chrome sidebar MVP runbook: start bridge, load unpacked extension, pair, select tabs, run fake-Hermes loop, inspect artifacts.

- Modify: `.gitignore`
  - Current responsibility: ignore secrets, runtime profiles, output, caches, and local companion artifacts.
  - Planned change: add any extension-local build/cache files discovered during implementation, while keeping source extension files tracked.

## Task 1: Bridge policy contract

**Purpose:** Create the fail-closed contract before any server or extension can execute page actions.

**Files:**
- Create: `scripts/sidebar_bridge_contract.py`
- Create: `tasks/test_sidebar_bridge_policy.py`

**Acceptance Criteria:**
- [ ] Allowed actions include `inspect_tabs`, `extract_structured_data`, `fill_field`, `set_select`, `check_checkbox`, `click_non_final_navigation`, `save_local_artifact`, `copy_to_clipboard`, and `propose_promotion_to_wiki`.
- [ ] Blocked actions include submit/send/post/purchase/delete/MFA/network/all-tab/storage/token/password behaviors.
- [ ] Validation rejects unselected tab IDs, URL/domain drift, malformed actions, unknown action types, secret-like selectors/labels, password fields, hidden targets, and final-submit-like controls.
- [ ] Sanitized context omits query strings/fragments and rejects secret-like metadata keys.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_sidebar_bridge_policy.py` with tests named:

```python
def test_validate_allowed_fill_field_for_selected_tab(): pass
def test_rejects_action_for_unselected_tab(): pass
def test_rejects_url_domain_drift(): pass
def test_rejects_final_submit_like_click(): pass
def test_rejects_secret_like_or_password_targets(): pass
def test_rejects_malformed_or_unknown_action_type(): pass
def test_sanitize_selected_tab_context_redacts_query_and_fragment(): pass
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_bridge_policy.py -q
```

Expected:

```text
FAIL because scripts/sidebar_bridge_contract.py does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/sidebar_bridge_contract.py` with these public names:

```text
Constants:
- ALLOWED_ACTION_TYPES containing: inspect_tabs, extract_structured_data, fill_field, set_select, check_checkbox, click_non_final_navigation, save_local_artifact, copy_to_clipboard, propose_promotion_to_wiki
- BLOCKED_ACTION_TYPES containing: click_submit, send_message, post_social, purchase, delete_record, approve_mfa, read_all_tabs, capture_network, scrape_password_or_token_storage
- FINAL_ACTION_WORDS containing: submit, send, post, purchase, buy, delete, approve, confirm
- SECRET_TARGET_WORDS containing: password, passwd, token, secret, api_key, apikey, mfa, otp, cookie, localstorage, sessionstorage

Public functions:
- sanitize_url(url: str) -> str
- sanitize_tab_context(tab: dict) -> dict
- build_run_policy(selected_tabs: list[dict]) -> dict
- validate_action(action: dict, policy: dict) -> dict
- validate_action_list(actions: list[dict], policy: dict) -> dict
```

Return validation dictionaries shaped as `{"ok": bool, "reason": str, "action": dict | None}`. Do not import browser or Hermes dependencies in this module.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_bridge_policy.py -q
```

Expected:

```text
PASS for bridge policy contract tests.
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
cd /home/orchestrator/repos/local/browser-agent && git add scripts/sidebar_bridge_contract.py tasks/test_sidebar_bridge_policy.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add sidebar bridge policy contract"
```

## Task 2: Local bridge server, pairing, fake-Hermes run loop, and artifacts

**Purpose:** Provide a testable localhost service that the extension can pair with before any real Hermes gateway integration is attempted.

**Files:**
- Create: `scripts/sidebar_bridge_server.py`
- Create: `tasks/test_sidebar_bridge_server.py`
- Modify: `scripts/sidebar_bridge_contract.py`

**Acceptance Criteria:**
- [ ] `GET /health` returns service status without requiring a token.
- [ ] `POST /pair` accepts the configured pairing code and returns an in-memory bearer token; bad codes fail.
- [ ] Authenticated `POST /runs` accepts prompt plus selected-tab summaries, creates a run ID, calls `FakeHermesAdapter`, validates action proposals, and writes local artifacts.
- [ ] Artifacts include `run_summary.json`, `selected_tabs.json`, `sanitized_context.json`, `actions_proposed.json`, `actions_executed.json`, `blocked_actions.json`, and `extracted.json` when extracted data exists.
- [ ] Unpaired requests and malformed fake-Hermes actions fail closed with no executable actions.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_sidebar_bridge_server.py` with tests named:

```python
def test_health_endpoint_returns_local_bridge_status(tmp_path): pass
def test_pairing_requires_configured_code(tmp_path): pass
def test_unpaired_run_request_is_rejected(tmp_path): pass
def test_fake_run_writes_expected_artifacts(tmp_path): pass
def test_malformed_adapter_actions_are_blocked(tmp_path): pass
def test_artifacts_never_include_secret_like_keys(tmp_path): pass
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_bridge_server.py -q
```

Expected:

```text
FAIL because scripts/sidebar_bridge_server.py does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `scripts/sidebar_bridge_server.py` with these public names:

```text
Classes and methods:
- FakeHermesAdapter.propose(prompt: str, selected_tabs: list[dict], policy: dict) -> dict
- SidebarBridgeState.pair(code: str) -> dict
- SidebarBridgeState.create_run(token: str, payload: dict) -> dict
- SidebarBridgeState.apply_action_results(token: str, run_id: str, payload: dict) -> dict

Public functions:
- create_handler(state: SidebarBridgeState)
- run_server(host: str = "127.0.0.1", port: int = 8765, output_dir: Path | None = None) -> None
- main(argv: list[str] | None = None) -> int
```

Use `http.server.ThreadingHTTPServer` and JSON only. Default output directory is `Path(os.environ.get("OUTPUT_DIR", "output")) / "sidebar-runs"` when run from the repo. Bind only to `127.0.0.1` unless an explicit CLI flag changes it.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_bridge_server.py -q
```

Expected:

```text
PASS for local bridge server tests.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_bridge_policy.py tasks/test_sidebar_bridge_server.py -q
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
```

Expected:

```text
PASS for sidebar bridge tests and all browser-agent tests.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add scripts/sidebar_bridge_contract.py scripts/sidebar_bridge_server.py tasks/test_sidebar_bridge_server.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add local sidebar bridge server"
```

## Task 3: Extension scaffold, side panel UI, and pairing client

**Purpose:** Create the load-unpacked Chrome extension shell with a terminal-like side panel that can pair with the local bridge and submit selected-tab runs.

**Files:**
- Create: `chrome_extension/manifest.json`
- Create: `chrome_extension/background.js`
- Create: `chrome_extension/sidepanel.html`
- Create: `chrome_extension/sidepanel.css`
- Create: `chrome_extension/sidepanel.js`
- Create: `chrome_extension/shared/action_contract.js`
- Create: `tasks/test_sidebar_extension_static.py`

**Acceptance Criteria:**
- [ ] Manifest uses MV3 and declares side panel support.
- [ ] Permissions are limited to `activeTab`, `scripting`, `sidePanel`, and localhost bridge host permissions.
- [ ] Side panel includes bridge URL, pairing code, selected-tab list, prompt input, run button, plan/results pane, blocked actions pane, and artifact paths pane.
- [ ] Client defaults to `http://127.0.0.1:8765` and does not request all tabs automatically.
- [ ] Client has no API keys, model provider secrets, submit/send/post/purchase/delete executors, or network capture code.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_sidebar_extension_static.py` with tests named:

```python
def test_manifest_uses_mv3_side_panel_and_minimal_permissions(): pass
def test_sidepanel_has_required_operator_controls(): pass
def test_client_defaults_to_localhost_bridge_only(): pass
def test_extension_source_does_not_include_forbidden_action_executors(): pass
def test_shared_contract_lists_allowed_and_blocked_actions(): pass
```

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_extension_static.py -q
```

Expected:

```text
FAIL because chrome_extension/manifest.json and side panel files do not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create the extension files. Keep `sidepanel.js` browser-only and dependency-free. Expose small pure helpers for static inspection by assigning them under `window.HermesSidebarPanel` when `window` exists:

```javascript
const DEFAULT_BRIDGE_URL = "http://127.0.0.1:8765";
async function pairBridge(bridgeUrl, pairingCode) { throw new Error("not implemented"); }
async function createRun(bridgeUrl, token, prompt, selectedTabs) { throw new Error("not implemented"); }
function renderRunResult(result) { throw new Error("not implemented"); }
```

Do not add bundlers or package managers in this task.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_extension_static.py -q
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/background.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/sidepanel.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/shared/action_contract.js
```

Expected:

```text
PASS for static extension tests and JavaScript syntax checks.
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
cd /home/orchestrator/repos/local/browser-agent && git add chrome_extension/manifest.json chrome_extension/background.js chrome_extension/sidepanel.html chrome_extension/sidepanel.css chrome_extension/sidepanel.js chrome_extension/shared/action_contract.js tasks/test_sidebar_extension_static.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add hermes sidebar extension scaffold"
```

## Task 4: Content-script DOM summaries and safe page-local execution

**Purpose:** Let the extension summarize selected pages and execute only bridge-validated safe actions.

**Files:**
- Create: `chrome_extension/content_script.js`
- Modify: `chrome_extension/manifest.json`
- Modify: `chrome_extension/sidepanel.js`
- Modify: `chrome_extension/shared/action_contract.js`
- Create: `tasks/test_sidebar_content_script.py`

**Acceptance Criteria:**
- [ ] DOM summary includes tab metadata supplied by the side panel plus visible headings/text blocks, links, forms, field labels/names/types/values/required/disabled state, buttons with likely roles, tables, lists, and repeated cards when detectable.
- [ ] Privacy-sensitive values are redacted for password/token/secret-like fields.
- [ ] Safe actions can fill text fields, set selects, and check checkboxes by unique selector.
- [ ] Final-submit-like clicks are refused by the content script even if the bridge already validated.
- [ ] Ambiguous selectors return a blocked result instead of best-effort execution.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_sidebar_content_script.py` with tests named:

```python
def test_dom_summary_extracts_forms_tables_lists_and_buttons(tmp_path): pass
def test_dom_summary_redacts_password_and_token_like_fields(tmp_path): pass
def test_execute_fill_field_updates_unique_text_input(tmp_path): pass
def test_execute_action_blocks_final_submit_click(tmp_path): pass
def test_execute_action_blocks_ambiguous_selector(tmp_path): pass
```

Use Playwright Python to load fixture HTML, inject `chrome_extension/shared/action_contract.js` and `chrome_extension/content_script.js`, then call `window.HermesSidebarContent.extractDomSummary()` and `window.HermesSidebarContent.executeValidatedAction(action)`.

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_content_script.py -q
```

Expected:

```text
FAIL because chrome_extension/content_script.js does not exist.
```

- [ ] **Step 3: Implement the minimal change**

Create `chrome_extension/content_script.js` with these browser-exposed functions:

```javascript
function extractDomSummary(options = {}) { throw new Error("not implemented"); }
function executeValidatedAction(action) { throw new Error("not implemented"); }
function resolveUniqueElement(selector) { throw new Error("not implemented"); }
function looksFinalAction(element, action = {}) { throw new Error("not implemented"); }
function looksSecretLikeField(element) { throw new Error("not implemented"); }
window.HermesSidebarContent = { extractDomSummary, executeValidatedAction };
```

Modify `sidepanel.js` to request summaries only for tabs the user selected in the side panel, then send those summaries to the bridge.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_content_script.py -q
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/content_script.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/sidepanel.js
```

Expected:

```text
PASS for content-script fixture tests and JavaScript syntax checks.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_extension_static.py tasks/test_sidebar_content_script.py -q
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
```

Expected:

```text
PASS for extension-related tests and all browser-agent tests.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add chrome_extension/content_script.js chrome_extension/manifest.json chrome_extension/sidepanel.js chrome_extension/shared/action_contract.js tasks/test_sidebar_content_script.py
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: add sidebar content script actions"
```

## Task 5: End-to-end fake run, README runbook, and operator proof

**Purpose:** Prove the MVP loop without real credentials: start the bridge, pair, submit selected-tab context, validate proposed actions, execute safe actions against a fixture page, and write artifacts.

**Files:**
- Modify: `scripts/sidebar_bridge_server.py`
- Modify: `chrome_extension/sidepanel.js`
- Modify: `README.md`
- Create: `tasks/test_sidebar_fake_run_e2e.py`
- Modify: `.gitignore`

**Acceptance Criteria:**
- [ ] Fake E2E test exercises pairing, selected-tab summary submission, bridge action validation, safe fill execution against a fixture page, final-submit blocking, and artifact creation.
- [ ] README documents exact operator commands for starting the bridge and loading the unpacked extension in a dedicated Hermes-attached Chrome profile/window.
- [ ] README states that the MVP uses fake-Hermes adapter unless a later real Hermes adapter is implemented.
- [ ] README documents local artifact paths and the blocked-action policy.
- [ ] Source-to-live sync dry run still succeeds and does not include secrets/profiles/output.

- [ ] **Step 1: Write the failing test**

Add `tasks/test_sidebar_fake_run_e2e.py` with tests named:

```python
def test_fake_sidebar_run_pairs_submits_executes_and_writes_artifacts(tmp_path): pass
def test_fake_sidebar_run_blocks_submit_action_and_records_reason(tmp_path): pass
```

The test should use `SidebarBridgeState` directly instead of opening a real Chrome extension UI. Use Playwright for the fixture page action execution and the bridge state for pairing/run/artifacts.

- [ ] **Step 2: Run the narrow test and confirm failure**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_fake_run_e2e.py -q
```

Expected:

```text
FAIL because the E2E bridge/content-script orchestration is not wired yet.
```

- [ ] **Step 3: Implement the minimal change**

Update bridge and side panel glue so a fake run returns a plan, extracted data, proposed actions, blocked actions, and artifact paths. Add README section `Hermes Chrome Sidebar MVP` with these commands:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm --service-ports browser-agent scripts/sidebar_bridge_server.py --host 127.0.0.1 --port 8765 --pairing-code dev-local
cd /home/orchestrator/repos/local/browser-agent && google-chrome --user-data-dir=/tmp/hermes-sidebar-profile --load-extension=/home/orchestrator/repos/local/browser-agent/chrome_extension
```

If `google-chrome` is unavailable on the operator machine, document loading `chrome_extension/` through `chrome://extensions` in the dedicated Chrome profile/window.

- [ ] **Step 4: Run the narrow test and confirm pass**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent python -m pytest tasks/test_sidebar_fake_run_e2e.py -q
```

Expected:

```text
PASS for fake sidebar run E2E tests.
```

- [ ] **Step 5: Run broader relevant checks**

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/background.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/sidepanel.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/content_script.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/shared/action_contract.js
cd /home/orchestrator/repos/local/browser-agent && scripts/sync_to_live.sh --dry-run
```

Expected:

```text
PASS for all tests and JavaScript syntax checks. The sync dry run reports planned source-to-live changes without copying secrets, profiles, output, caches, or runtime browser state.
```

- [ ] **Step 6: Commit**

```bash
cd /home/orchestrator/repos/local/browser-agent && git status --short
cd /home/orchestrator/repos/local/browser-agent && git add scripts/sidebar_bridge_server.py chrome_extension/sidepanel.js README.md tasks/test_sidebar_fake_run_e2e.py .gitignore
cd /home/orchestrator/repos/local/browser-agent && git commit -m "feat: prove sidebar fake run loop"
```

## Final Verification

Run:

```bash
cd /home/orchestrator/repos/local/browser-agent && docker compose run --rm browser-agent scripts/run_tests.py
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/background.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/sidepanel.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/content_script.js
cd /home/orchestrator/repos/local/browser-agent && node --check chrome_extension/shared/action_contract.js
cd /home/orchestrator/repos/local/browser-agent && scripts/sync_to_live.sh --dry-run
cd /home/orchestrator/repos/local/browser-agent && git status --short
```

Expected:

```text
All tests and JavaScript syntax checks pass. Sync dry run is non-destructive and excludes secrets/profiles/output/runtime state. Git status is clean after the final commit.
```

## Rollout Notes

- No database migration.
- No external service configuration.
- No Chrome Web Store packaging.
- No real Hermes gateway call in this first implementation slice.
- Operator starts the bridge manually and loads the unpacked extension in a dedicated Chrome profile/window.
- Rollback is removing the unpacked extension from Chrome and stopping the bridge process; no remote state should be changed by this MVP.

## Execution Handoff

Recommended execution mode: Subagent-Driven.

Rationale: Tasks are independent, testable, and commit-sized. The bridge policy/server, extension scaffold, content script, and E2E proof can be implemented by separate workers with review between tasks. The saved spec and this plan provide enough boundaries for autonomous workers without giving them broad browser authority.

## Stop Conditions For Implementers

Stop and report evidence if:

- A task requires reading cookies, localStorage, sessionStorage, saved passwords, browser profile databases, or network/API traffic.
- A task requires final submit/send/post/purchase/delete/MFA approval behavior.
- A real Hermes gateway integration is needed to pass tests.
- Docker tests cannot run after rebuilding the browser-agent image.
- Chrome extension APIs require permissions broader than the plan allows.
- The implementation needs files outside the listed file map, except for narrow test fixtures created under `tasks/fixtures/` with no secrets.
