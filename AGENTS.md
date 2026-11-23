# Project Instructions

These instructions apply to the whole repository. Read them before changing code or project documentation.

## Product scope

This repository contains the DSB-Bot backend. The existing frontend is a separate, already substantially implemented GitHub Pages project. Backend work must preserve its useful behavior and integrate with it through the agreed REST API; do not treat frontend creation or a rewrite as part of this repository's default scope.

## Mandatory schedule rules

- The frontend receives only student-compatible schedules.
- An original student schedule always takes precedence over a converted teacher schedule for the same calendar date.
- Preserve original student HTML byte-for-byte.
- Convert teacher schedules only as fallback data. Do not expose teacher schedules directly.
- Use Europe/Berlin calendar dates. Student plans cover today and tomorrow; teacher sections are eligible beginning the day after tomorrow.
- Keep exactly one current schedule per date. A later genuine student plan may replace a converted teacher plan; a teacher plan must never replace a genuine student plan.
- Retrieval, decoding, or parsing failure is not an empty result and must never delete or downgrade a valid stored plan.
- A successful empty result alone does not remove a previously stored plan.
- Do not retain additional raw DSB response archives by default.

## DSB evidence and security

- Do not invent DSB request, response, menu, or HTML behavior. Confirm assumptions against repository fixtures or sanitized real response samples; mark unresolved behavior explicitly.
- Never commit or request credentials in chat. Keep secrets in environment configuration, not source control.
- Keep API delivery read-only unless a separately approved requirement says otherwise. Do not expose internal plan provenance or credentials.
- Do not deploy, provision infrastructure, change external services, or perform a production cutover without explicit user approval.

## Engineering approach

- Inspect existing code and fixtures before changing behavior. Preserve useful DSB authentication, Discord notifications, and existing frontend functionality.
- Keep DSB communication, parsing/conversion, synchronization, persistence, notifications, and API delivery separated and testable.
- Add or update automated tests for business-rule changes, using authentic fixtures and never inventing DSB markup.
- Keep README and implementation-roadmap status aligned with the code. Distinguish implemented backend work from outstanding DSB verification, existing-frontend integration, and deployment work.
- Prefer small, maintainable changes and explain validation performed and remaining evidence gaps.

## Current project boundary

The backend currently provides a FastAPI read-only API, one-shot synchronization worker, SQLite repository, teacher-to-student conversion, Docker Compose configuration, pytest tests, CI, and Linux deployment templates. The worker is not automatically scheduled in local Compose. DSB protocol assumptions still require sanitized authenticated response evidence before production use.

