# Project status and next steps

This repository contains the DSB-Bot backend. The separate GitHub Pages frontend already has its current and historical views, theme system, plan popup, reload controls, and preferences. Integration preserves that interface.

## Implemented locally

- FastAPI read-only endpoints for health, plan metadata, plan HTML, and sync status.
- SQLite storage with one current plan per date and student-over-converted-teacher priority.
- One-shot DSB synchronization worker, HTML parsing/conversion, and best-effort Discord notifications.
- Docker Compose services, HTTPS Caddy configuration, systemd worker and backup timers, restore tooling, and CI workflow.
- Sanitized response capture helper and tests. It is ready for authentic DSB samples, which have not yet been supplied or verified.
- Dry-run-first archive import. The confirmed manifest attributes 219 archived plans to `student` and six dates (2026-11-03, 2026-11-04, 2026-11-10 through 13) to `teacher_converted`. Dry-run validated 225 plans and skipped one empty placeholder (`2026-06-12.html`). No production database has been migrated.
- Existing frontend checkout wired to the API client for current and historical plans. Configure `assets/js/apiConfig.js` with the real API origin before publishing; backend CORS must use the exact published frontend origin.

## Remaining before a deployment can be reviewed

1. Run the capture helper against the real DSB account and review sanitized success, genuinely empty, auth-failure, and transient-failure responses. This is needed to validate the DSB protocol assumptions without risking account lockouts or logging secrets.
2. Run backend CI and verify Caddy/Compose plus AMD64/ARM64 image builds on a Docker-enabled runner. Local Docker daemon is unavailable in this workspace.
3. Confirm the target host, DNS/API domain, frontend origin, secrets provisioning, and offsite backup bucket; then configure staging.
4. Import the manifest into the selected staging database and compare available date coverage/content before cutover.
5. Rehearse staging sync, CORS from the real frontend origin, backup/restore, monitoring, and rollback. Only then is the project ready for a separately approved production deployment.

## Historical planning material

`agent-docs/IMPLEMENTATION_PLAN.md` and the ignored archive snapshots are reference material. `AGENTS.md` is the canonical source for AI and project instructions; keep this roadmap current with actual implementation state.
