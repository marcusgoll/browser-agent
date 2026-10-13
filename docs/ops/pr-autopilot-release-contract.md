# PR Autopilot release contract — browser-agent

Status: **verification pilot; production promotion not authorized**.

## Branch and review
- Default branch: `main`; no direct agent pushes.
- Ordinary PR merge requires exact-HEAD passing canonical verification, no blocking review findings, and a guarded merge.
- Auth, secrets, deployment controls, verification policy, and destructive migrations require owner approval.

## Canonical build and verification
- Workflow: `.github/workflows/autopilot-verify.yml`
- Build: `docker compose build browser-agent`
- Tests: `docker compose run --rm browser-agent scripts/run_tests.py`
- Missing, stale, queued, cancelled, or failed verification blocks merge.

## Release artifact
- Immutable image digest: not configured.
- SBOM and signing: not configured.
- Automated tagging and publishing: disabled.

## Environments
- Preview: not configured.
- Staging: not configured.
- Production: disabled pending an approved promotion and rollback contract.
- Existing documented operator dry-run: `scripts/sync_to_live.sh --dry-run`.
- Existing documented operator apply: `scripts/sync_to_live.sh --apply`.
- These source-sync commands are **not** an approved automated deployment mechanism.

## Required before autonomous production
1. Build once and record immutable artifact digest and provenance.
2. Deploy exact artifact to staging and run environment-specific health checks.
3. Define production approval policy and verify rollback against an earlier artifact.
4. Record deployment, health, and rollback evidence against the release ID.

No release or deployment action is authorized by this document.
