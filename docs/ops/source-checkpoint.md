# Source Checkpoint and Live Workspace Boundary

Date: 2026-05-24

## Source checkpoint

This repository is the managed source checkpoint for the live browser-agent ops workspace.

- Source repo: /home/orchestrator/repos/local/browser-agent
- Live ops workspace: /home/orchestrator/browser-agent

The live workspace remains in place because Hermes cron jobs and runtime artifacts currently reference it directly.

## Runtime state intentionally excluded

Do not commit:

- .env or any credential-bearing environment file
- profiles/ browser profiles and cookies
- output/ generated reports, screenshots, proof bundles, approved post text, and run artifacts
- __pycache__/ and .pytest_cache/

These are excluded by .gitignore and were not copied into the initial checkpoint.

## Deployment model for now

For now, this repo is a checkpoint and review surface, not the live execution path.

Safe flow:

1. Edit source in /home/orchestrator/repos/local/browser-agent.
2. Run source-local tests with Docker from this repo.
3. Copy reviewed source changes into /home/orchestrator/browser-agent.
4. Run the live workspace canonical test command.
5. Run only dry-run/report wrappers unless Marcus explicitly approves execution.

Do not replace /home/orchestrator/browser-agent with this repo or a symlink until a dedicated migration updates and verifies all Hermes cron job workdirs/scripts.

## Current live cron consumers

The following Hermes cron jobs still use /home/orchestrator/browser-agent as workdir:

- x-bookmark-processor
- x-bookmark-digest
- x-bookmark-wiki-sync
- x-bookmark-agent-feed
- x-bookmark-public-web-followup

## Canonical tests

From this source repo:

```bash
cd /home/orchestrator/repos/local/browser-agent
docker compose build browser-agent
docker compose run --rm browser-agent scripts/run_tests.py
```

From the live workspace:

```bash
cd /home/orchestrator/browser-agent
docker compose run --rm browser-agent scripts/run_tests.py
```

## Future migration checklist

1. Pause or reschedule dependent cron jobs during migration.
2. Preserve /home/orchestrator/browser-agent/profiles and output outside git.
3. Update cron workdirs from /home/orchestrator/browser-agent to the chosen final path, or keep a deliberate compatibility symlink.
4. Rebuild Docker image from the repo path.
5. Run canonical tests.
6. Run x-bookmark-processor.sh in dry-run mode.
7. Run x-bookmark-agent-feed.sh and verify opportunity memo/high-ROI task output.
8. Confirm no cron job points to a removed path.
