Browser Agent Setup for Homelab
================================

Location: /home/orchestrator/browser-agent/
Source checkpoint: /home/orchestrator/repos/local/browser-agent/

What This Is
------------
A self-hosted browser automation stack using browser-use + Playwright.
Runs as Docker containers on your homelab. Supports:
- Data scraping
- Form filling
- Research / multi-page navigation
- Social media posting (after manual login)
- Google OAuth website operations for Marcus-owned sites (attended login only)

Directory Layout
----------------
.
├── Dockerfile                  # Headless browser-use container
├── Dockerfile.vnc              # VNC-enabled container for headed login
├── docker-compose.yml          # Headless service definition
├── docker-compose.vnc.yml      # VNC service definition
├── .env                        # API keys (created from Hermes env)
├── .env.example                # Template for API keys
├── README.md                   # This file
├── LOGIN_INSTRUCTIONS.md       # How to do interactive login via VNC
├── scripts/                    # Reusable automation scripts
│   ├── run_task.py             # Generic natural-language task runner
│   ├── scrape.py               # Page scraper
│   ├── form_filler.py          # Form filler
│   ├── login_helper.py         # Headed browser (local display)
│   └── vnc_login.py            # Headed browser inside VNC container
├── tasks/                      # Your custom task definitions
│   └── test_scrape.py          # Example test task
├── profiles/                   # Persistent browser profiles
│   └── x-profile/              # Created by VNC login (if done)
└── output/                     # Results and downloads

Quick Start
-----------

1. API keys are already configured in .env (pulled from Hermes env)

2. Run a test task:
   docker compose run --rm browser-agent scripts/run_task.py \
     "Go to example.com and extract the page title"

3. Scrape a page:
   docker compose run --rm browser-agent scripts/scrape.py \
     https://news.ycombinator.com --extract "top 10 story titles"

4. Fill a form:
   docker compose run --rm browser-agent scripts/form_filler.py \
     https://httpbin.org/forms/post \
     --fields '{"custname":"Test User","custtel":"555-1234"}' \
     --submit

Interactive Login (for authenticated sites like X.com)
------------------------------------------------------

1. Start the VNC container:
   docker compose -f docker-compose.vnc.yml up -d

2. Connect via VNC from your local machine:
   vncviewer 100.93.148.25:5900

3. Launch the login helper inside VNC:
   docker exec -d browser-agent-vnc \
     python3 /app/scripts/vnc_login_secure.py https://x.com --profile x-profile

4. In the VNC window, log in to X.com manually

5. Stop VNC when done:
   docker compose -f docker-compose.vnc.yml down

6. Run authenticated headless tasks:
   docker compose run --rm browser-agent scripts/run_task.py \
     "Go to x.com and post 'Hello from my homelab agent'" \
     --profile x-profile

X.com Google OAuth E2E Probe
----------------------------

The safe X Google OAuth probe opens X.com, attempts to click the Google login button, and stops at the attended Google boundary. It does not enter passwords, MFA, recovery details, or approve OAuth consent.

Headless smoke test:
   docker compose run --rm browser-agent \
     scripts/x_google_oauth_login.py --profile x-google-oauth-e2e --headless --timeout 45

Attended VNC flow:
   docker compose -f docker-compose.vnc.yml up -d
   docker exec -d browser-agent-vnc \
     python3 /app/scripts/x_google_oauth_login.py --profile x-google-oauth-e2e --timeout 90

Expected safe statuses:
- google_oauth_boundary       -- Marcus must complete Google account/MFA/consent manually.
- logged_in                   -- saved profile already reached X home.
- x_single_sign_on_blocked    -- X blocked OAuth callback; use real-browser cookie import.
- google_insecure_browser_blocked -- Google rejected the browser.

Using Existing Chrome (browserless)
-----------------------------------
You already have browserless/chrome running on the homelab (ports 3333/9222).
To connect to it instead of launching local Chromium, add to .env:
   CHROME_HOST=social-agent-chrome
   CHROME_PORT=9222

Note: browserless/chrome does NOT persist cookies between restarts.
For authenticated work, use the local Playwright browser with persistent profiles.

Profiles Explained
------------------
Each profile is a separate browser user data directory.
- profiles/default/                    -- default anonymous profile
- profiles/x-profile/                  -- logged into X/Twitter (after VNC login)
- profiles/linkedin-profile/           -- logged into LinkedIn (create with VNC)
- profiles/reddit-profile/             -- logged into Reddit (create with VNC)
- profiles/google-oauth-websites/      -- shared low-risk Google OAuth website profile
- profiles/site-<slug>-google/         -- site-specific Google OAuth profile for higher-risk admin surfaces

Profiles survive container restarts because they are bind-mounted from the host.
For Google OAuth flows, use scripts/vnc_login_secure.py and let Marcus handle account selection, MFA, and consent screens manually.

Security Notes
--------------
- API keys live in .env (never commit this file)
- Browser profiles contain cookies/session data -- treat as secrets
- The container runs as root inside (required for Chromium sandbox)
- For social media, use a dedicated automation account when possible

X Bookmark Processor Safety
---------------------------
The scheduled wrapper is report-only by default:
   /home/orchestrator/.hermes/scripts/x-bookmark-processor.sh

It runs process_bookmarks.py in dry-run mode and reports planned moves/deletes without mutating X bookmarks.

Approved execute is intentionally separate:
   X_BOOKMARK_APPROVED_EXECUTE=1 \
   X_BOOKMARK_APPROVAL_NOTE="Marcus approved <scope>" \
   X_BEARER_TOKEN="<x-public-api-bearer-token>" \
   /home/orchestrator/.hermes/scripts/x-bookmark-processor-approved-execute.sh

Do not schedule the approved-execute wrapper. Use it only after reviewing the dry-run report and approving exact scope. X_BEARER_TOKEN is required only for approved move/delete execution and must stay in .env or the process environment, never committed.

Source Repo Sync
----------------

Source repo to live sync:
   cd /home/orchestrator/repos/local/browser-agent
   scripts/sync_to_live.sh --dry-run
   scripts/sync_to_live.sh --apply

The sync helper excludes .env, profiles/, output/, caches, and runtime browser state. It refuses a dirty source tree unless --allow-dirty is passed.

Canonical Tests
---------------
Run tests inside Docker, not host Python:
   cd /home/orchestrator/browser-agent
   docker compose build browser-agent
   docker compose run --rm browser-agent scripts/run_tests.py

Host pytest is not authoritative because host Python may not have browser-agent dependencies such as langchain_openai.

Ops Checkpoint
--------------
This directory is currently a live ops workspace, not a git repo. See:
   docs/ops/browser-agent-checkpoint.md

That checkpoint records why the path was not moved during the safety-gate patch and what a future repo migration must verify.

Troubleshooting
---------------

"playwright not found":
   docker compose build --no-cache

"Browser closed unexpectedly":
   Check memory: the container needs ~1GB RAM for Chromium

"Permission denied on profiles/":
   chown -R $(id -u):$(id -g) profiles/

"CDP connection failed":
   Ensure social-agent-chrome container is running:
   docker ps | grep social-agent-chrome

"No module named 'litellm'":
   Already fixed in Dockerfile -- rebuild if needed

Tested Tasks
------------
- Scrape example.com title and text: WORKING
- Scrape Hacker News top 10 stories: WORKING
- Fill httpbin.org pizza form: WORKING
- VNC headed browser for login: RUNNING (port 5900)
