# Hermes Chrome Sidebar Extension Design

## Goal

Build a Chrome extension side panel that connects a dedicated Chrome profile/window to Hermes through a narrow local bridge. The extension lets Marcus prompt Hermes from the browser sidebar, select tabs that are in scope, inspect or scrape those tabs, and draft/fill forms while keeping final submissions under manual user control.

## Current State Found

- Hermes already supports browser automation, including local Chromium-family CDP attachment through `/browser connect` and lower-level `browser_cdp`.
- Hermes browser CDP support includes a supervisor for dialogs and frame-tree state.
- `/browser connect` is currently CLI-only and not a sidebar/gateway-dispatched product surface.
- The browser-agent repo already uses Playwright/browser-use patterns, persistent profiles, local artifacts, proof bundles, and account/context safety checks.
- The relevant product posture is user-controlled assistant/copilot, not unattended bot or auto-submit.

## Decisions

- Use a dedicated Hermes-attached Chrome profile/window for MVP instead of the user's everyday Chrome profile.
- Use a hybrid architecture: Chrome extension UI plus lightweight local bridge plus Hermes backend.
- MVP authority is assisted-write with no final submit. Hermes can draft, fill, inspect, scrape, and research selected tabs, but final submit/send/purchase/post/delete actions remain manual.
- Long-term unattended automation is a future promotion path for named workflows only, not general unlimited browser control.
- MVP workflows are form drafting/filling, multi-tab research, and data scraping.
- Data scraping writes local artifacts automatically, shows sidebar/clipboard previews, and can promote to Hermes/wiki/notes only through an explicit user action.
- Hermes sees user-selected tabs only for MVP.
- Default page context is a structured DOM summary. Text/accessibility-only privacy mode and screenshot/full-DOM escalation can be added, but network/API capture is excluded from MVP.

## Architecture

The selected architecture is a narrow local bridge contract:

Chrome Extension -> Local Bridge -> Hermes Backend -> Bridge-validated page actions

### Chrome Extension

Responsibilities:

- Provide the Chrome side panel terminal/chat UI.
- List currently open tabs and let the user select tabs for a run.
- Run content scripts in selected tabs.
- Extract structured page summaries from selected tabs.
- Execute safe page-local actions validated by the bridge.
- Show run status, Hermes plan, extracted data previews, field diffs, blocked actions, and artifact paths.

The extension must not store model/provider API keys. It should also avoid becoming a full agent runtime. Its job is UI, tab selection, page context extraction, and page-local execution.

### Local Bridge

Responsibilities:

- Pair the extension to Hermes with a local token or equivalent local auth mechanism.
- Create run IDs and maintain run state.
- Receive selected-tab context bundles from the extension.
- Persist sanitized proof and artifact metadata.
- Send bounded prompts/context to Hermes.
- Receive structured action proposals from Hermes.
- Validate all actions against the run policy before forwarding them to the extension.
- Fail closed when policy, tab scope, schema, pairing, or storage checks fail.

The bridge is the main safety boundary. Hermes proposes actions; the bridge validates; the extension executes.

### Hermes Backend

Responsibilities:

- Run the agent loop and use existing Hermes skills, memory, model routing, and tools.
- Interpret the user prompt and selected-tab context.
- Produce a short plan, extraction results, field-fill proposals, warnings, and a structured action list.
- Avoid arbitrary browser-control commands for this extension path.

Hermes receives only the selected-tab context and explicitly approved escalation artifacts.

## Run Data Flow

1. User opens the sidebar in the dedicated Hermes-attached Chrome profile/window.
2. User selects tabs that belong to the run.
3. User enters a prompt.
4. Extension extracts structured DOM summaries from selected tabs.
5. Bridge creates a run ID, selected-tab inventory, sanitized context bundle, and policy constraints.
6. Hermes receives the prompt, selected-tab summaries, and constraints.
7. Hermes returns a short plan, extracted data, proposed field fills, warnings, and a structured action list.
8. Bridge validates the action list.
9. Extension executes only allowed actions.
10. Sidebar shows changed fields, extracted data, blocked actions, and artifact paths.
11. User manually performs any final submit/send/purchase/post/delete action.

## Structured DOM Summary

Default selected-tab context should include:

- tab ID
- URL, domain, and page title
- visible headings and text blocks
- links
- forms
- field labels, names, types, current values, required/disabled state
- buttons and likely action role
- tables, lists, cards, and repeated records when detectable

Privacy mode can downgrade this to text/accessibility snapshot only. Screenshot/full DOM should require explicit escalation. Network/API capture is out of scope for MVP.

## MVP Action Contract

Allowed action examples:

- inspect_tabs
- extract_structured_data
- fill_field
- set_select
- check_checkbox
- click_non_final_navigation
- save_local_artifact
- copy_to_clipboard
- propose_promotion_to_wiki

Blocked action examples:

- click_submit
- send_message
- post_social
- purchase
- delete_record
- approve_mfa
- read_all_tabs
- capture_network
- scrape_password_or_token_storage

Every Hermes action proposal must use a strict schema. The bridge rejects malformed output or action types outside the MVP allowlist.

## Data Scraping Outputs

Every scrape/research run writes a local run folder first. Typical files:

- extracted.json
- extracted.csv or extracted.md when useful
- run_summary.json
- selected_tabs.json
- sanitized_context.json
- actions_proposed.json
- actions_executed.json
- blocked_actions.json

Sidebar display and clipboard copy are presentation surfaces over the same local artifacts. Promotion to Hermes/wiki/notes is a separate explicit action and should record the promotion target in the run summary.

Google Drive, Sheets, Docs, public publishing, social posting, and other external writes are outside MVP unless separately approved.

## Security Boundaries

- Use a dedicated Hermes-attached Chrome profile/window for MVP.
- Pair extension and bridge before any run.
- Do not store model/provider secrets in the extension.
- Do not inspect cookies, localStorage, sessionStorage, browser profile databases, password stores, or token files.
- Use selected tabs only.
- Exclude network/API capture from MVP.
- Block final submits and irreversible actions.
- Require explicit escalation for screenshots/full DOM.
- Record enough non-secret proof to debug a run without leaking credentials.

## Bridge Policy Gates

The bridge must reject an action when:

- the extension is unpaired
- the tab ID was not selected for the run
- the current tab URL/domain drifted from the observed run context
- the action type is not in the allowlist
- a field selector cannot be resolved uniquely
- the target looks hidden, password-like, token-like, or secret-like
- the target button/control looks like final submit/send/purchase/post/delete
- Hermes output is malformed or not schema-valid
- the page changed enough that re-inspection is required

## Error Handling

- DOM extraction failure returns `inspection_failed`; no page actions execute.
- Ambiguous Hermes actions are shown as a plan only; no page actions execute.
- Ambiguous field resolution shows candidates in the sidebar and waits for user selection.
- Page drift stops the run and requires re-inspection.
- Bridge or Hermes disconnect marks the run interrupted and stops content-script execution.
- Artifact write failure keeps the sidebar preview available but disables export/promotion until storage works.
- Malformed Hermes JSON is treated as a blocked action set, not as best-effort execution.

## Testing Strategy

Unit tests:

- bridge policy enforcement
- extension pairing/auth checks
- selected-tab scope checks
- domain drift checks
- action schema validation
- blocked final-submit detection
- secret-like field rejection
- malformed Hermes output handling

Fixture tests:

- content-script DOM summary extraction for forms, tables, lists, and repeated cards
- field matching from labels/names/placeholders
- fake Hermes action proposals for allowed fills, malformed actions, tab mismatch, and submit attempts

End-to-end smoke test:

- load unpacked extension into a local Chrome test profile
- open fixture tabs
- select tabs in the side panel
- run a fake form-fill prompt through the local bridge
- verify non-submit fields are filled
- verify final submit remains blocked
- verify local artifacts are written

Manual dogfood:

- run in a dedicated Hermes-attached Chrome profile
- test one form drafting/filling workflow
- test one multi-tab research workflow
- test one data scraping workflow

## Future Promotion Path Toward Unattended Automation

Do not implement unattended automation as generic unlimited browser authority. Future unattended mode should be limited to named workflow recipes on named domains with:

- deterministic preflight
- domain/action allowlists
- dry-run mode
- proof bundles
- explicit configured limits
- audit log
- kill switch
- rollback/undo where possible
- manual approval before promotion from assisted-write to unattended

The path is:

1. MVP assisted-write/no final submit.
2. Approved one-click actions for narrow low-risk flows.
3. Named unattended recipes after evidence, tests, and approval gates exist.

## Non-Goals

- General control of the user's everyday Chrome profile.
- All-tab access by default.
- Network/API capture.
- Password/MFA/token extraction.
- Final submit/send/purchase/post/delete in MVP.
- Extension-native LLM agent runtime.
- Public distribution, billing, or Chrome Web Store packaging.
- Google Drive/Sheets/Docs publishing without separate approval.

## Open Questions For Later

- Exact bridge transport: native messaging, localhost WebSocket/HTTP, or both.
- Whether to build the bridge as a browser-agent service, Hermes plugin, or standalone process.
- Exact pairing UX and token rotation policy.
- Whether the first implementation lives in browser-agent, hermes-agent, or a new repo under `/home/orchestrator/repos/`.
- Which wiki/notes promotion target should be first.

## Success Criteria

The MVP succeeds when Marcus can:

1. Open a dedicated Hermes-attached Chrome profile/window.
2. Open the Hermes sidebar extension.
3. Pair it with a local bridge/Hermes backend.
4. Select one or more tabs.
5. Ask Hermes to inspect/scrape/research/fill within those selected tabs.
6. See a plan and any proposed changes before execution.
7. Let the extension fill non-final fields or extract data.
8. See blocked final-submit actions clearly explained.
9. Review local artifacts and optionally copy/promote results.
10. Verify from proof files exactly what tabs, prompts, actions, and artifacts were involved.
