# Project status and next steps

This repository contains the DSB-Bot backend. The separate GitHub Pages frontend already has current and historical views, its theme system, plan popup, reload controls, and preferences. The existing interface is served unchanged from the OCI staging host and uses the backend through the same origin.

## Implemented locally

- FastAPI read-only endpoints for health, plan metadata, plan HTML, and sync status.
- SQLite storage with one current plan per date and student-over-converted-teacher priority.
- One-shot DSB synchronization worker, HTML parsing/conversion, and best-effort Discord notifications.
- Docker Compose services, Caddy HTTPS configuration, systemd worker and backup timers, restore tooling, and CI workflow.
- Sanitized response capture helper and tests. On 2026-11-23, sanitized authenticated menu responses from both configured accounts confirmed the current envelope and plan-menu path. Empty and failure response samples remain outstanding.
- Dry-run-first archive import. The confirmed manifest attributes 219 archived plans to `student` and six dates (2026-11-03, 2026-11-04, 2026-11-10 through 13) to `teacher_converted`. Dry-run validated 225 plans and skipped one empty placeholder (`2026-06-12.html`). No production database has been migrated.
- Existing frontend checkout wired to the API client for current and historical plans. `assets/js/apiConfig.js` uses the page origin.

## OCI staging deployment (2026-11-23)

- Frontend and API run on an OCI `VM.Standard.A1.Flex` instance (1 OCPU, 6 GB RAM, 50 GB boot volume) in `eu-frankfurt-1`.
- Caddy 2.11.4 serves the frontend and proxies `/api/*` and `/healthz`. A publicly trusted short-lived Let’s Encrypt certificate is issued for the VM's IP; Caddy renews it automatically.
- Public HTTPS for the home page, health endpoint, plan list, and plan HTML has been verified. One controlled student/teacher sync succeeded and the API now returns six plans dated 2026-11-23 through 30 (weekdays only).
- DSB credentials are stored in the host `.env` with mode `600`. Discord webhook values were not transferred. The sync and backup timers remain disabled; SSH is not exposed publicly, and administration uses a source-restricted OCI Bastion session.

## Remaining before production operation

1. Capture and review naturally observed genuinely empty, authentication-failure, and transient-failure responses. The successful student and teacher menu paths and one detail-document sync have already been observed; do not deliberately induce authentication or transport failures.
2. Keep the sync timer disabled until notification configuration and monitoring are reviewed. Verify that a later student plan replaces a converted teacher plan and rehearse failure/empty behavior before enabling recurring synchronization.
3. Transfer the archived HTML plans to the host over a protected channel, import from the confirmed manifest in dry-run mode, and verify date coverage/content. The source archives were deliberately not uploaded in this deployment.
4. Configure an OCI Object Storage destination and instance-principal policy for offsite backups; rehearse restore before enabling the backup timer.
5. Verify the existing frontend's current and historical views with real plan data and rehearse monitoring/rollback before production use.

## Historical planning material

`agent-docs/IMPLEMENTATION_PLAN.md` and ignored archive snapshots are reference material. `AGENTS.md` is the canonical source for AI and project instructions; keep this roadmap current with actual implementation state.
