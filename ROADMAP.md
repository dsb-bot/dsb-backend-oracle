# Project status and next steps

The existing GitHub Pages frontend is a separate, substantially implemented project. OCI continues to read and process DSB data and stores the source-of-truth SQLite database. Cloudflare serves the stable public read API from a Worker and EU D1 database; OCI publishes finalized student-compatible plans to it over authenticated HTTPS.

## Implemented

- FastAPI read-only endpoints, SQLite storage, student-over-converted-teacher priority, and one-shot synchronization worker.
- Cloudflare Worker routes for health, plans, schedule HTML, and sync status; authenticated internal publisher routes; D1 migration; and public `workers.dev` deployment at `https://dsb-bot-api.dsb-bot.workers.dev`.
- OCI-side Cloudflare publisher with a transactional retry outbox and manual snapshot publication command. Local source syntax and Wrangler dry-run/deployment were validated on 2026-11-24.
- The Worker health route responds successfully. OCI publisher code is installed, the publisher bearer token is stored in the OCI `.env` with mode 600, and the current seven-plan snapshot is live in D1. Token rotation was verified by a second successful snapshot publish. The temporary token was removed from its transfer staging path.
- OCI `dsb-sync.timer` is installed and enabled every five minutes; the manual run and repeated scheduled runs succeeded on 2026-11-24. Sync failures are logged to systemd's journal.
- A private Standard-tier Object Storage bucket, instance-specific Dynamic Group, and bucket-scoped create-only policy are configured. The OCI CLI runs in `/opt/oci-cli` using Instance Principals. The daily backup timer is enabled; its first manual run passed SQLite integrity and OCI checksum verification for a 192,512-byte snapshot. A bucket-scoped Object Storage lifecycle policy expires `dsb-*.sqlite3` objects after 30 days.
- The supplied Discord webhook is configured for both plan updates and sync warnings in the OCI `.env` (mode 600); the supplied role is mentioned only by warning messages. No test post was sent, so delivery remains unverified until a real notification event.
- DSB credentials remain on OCI. Cloudflare must receive only the publishing token and finalized student-compatible plan records, never DSB credentials or Discord webhook values.
- Historical archive import is dry-run-first. The confirmed manifest attributes 219 archived plans to `student` and six dates (2026-11-03, 2026-11-04, 2026-11-10 through 13) to `teacher_converted`; dry-run validated 225 plans and skipped one empty placeholder. No production database has been migrated.

## Remaining for hardened production operation

1. Verify current and historical frontend views against the live Worker. The API config was pushed to `dsb-beta/main` in commit `bcf3638`; GitHub Pages now serves the Cloudflare URL.
2. Rehearse restoring an uploaded snapshot into an isolated database and verify the restored plan dates.
3. Confirm Discord delivery on the first real plan change or sync warning; no synthetic message or failure was sent.
4. Capture and review naturally observed genuinely empty, authentication-failure, and transient-failure responses; these cases remain a DSB verification gap.

## Historical planning material

`agent-docs/IMPLEMENTATION_PLAN.md` and ignored archive snapshots are reference material. `AGENTS.md` is the canonical source for AI and project instructions; keep this roadmap aligned with actual implementation state.
