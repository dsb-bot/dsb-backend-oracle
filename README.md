# DSB-Bot Backend

The backend stores one current student-compatible schedule per calendar date in SQLite and serves schedules through a read-only REST API. Original student schedules are kept byte-for-byte and always take priority over converted teacher schedules.

## Local development

Python 3.11 or newer is supported; Python 3.13 is the intended deployment runtime.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
```

The API can run without DSB credentials:

```powershell
$env:DATABASE_PATH = ".\data\dsb.sqlite3"
uvicorn dsb_bot.api:app --reload
```

## Docker Compose

Copy `.env.example` to `.env`, set secrets only in `.env`, and start the API:

```powershell
Copy-Item .env.example .env
docker compose up --build api
```

The API is available at `http://localhost:8000`. To run one synchronization manually, configure valid credentials in `.env` and use:

```powershell
docker compose --profile sync run --rm worker
```

The worker performs one run and exits. It is not automatically scheduled by local Compose; Linux host timer templates are provided under `deploy/systemd/`. Do not run this command against DSB until credentials and the current DSB response behavior have been verified.

For a Linux-host deployment layout with Caddy, a five-minute systemd worker timer, and a daily SQLite backup, see [deploy/README.md](deploy/README.md). These files do not provision OCI resources or an off-instance backup destination.

## Historical archive import

The importer validates date-named HTML files before writing anything. It defaults to a dry run and requires an explicit provenance choice because the legacy archive may contain both original and converted schedules. Use `--source` only after confirming every file has that provenance. For a mixed archive, create a CSV that assigns every date:

```csv
date,source
2025-08-27,student
2026-11-13,teacher_converted
```

The dates above are examples only; do not infer provenance from age or formatting. Then run:

```sh
python -m dsb_bot.archive_import ./plans \
  --database ./data/dsb.sqlite3 \
  --manifest ./archive-sources.csv
```

For a confirmed single-source archive, the shorter form is:

```sh
python -m dsb_bot.archive_import ./plans \
  --database ./data/dsb.sqlite3 \
  --source teacher_converted
```

After confirming every date's provenance and reviewing the validation count, repeat with `--apply`. Student plans already in SQLite remain protected from converted-plan imports. Keep the existing frontend pointed at its current source until archive coverage and cutover have been verified.

## API

- `GET /healthz`
- `GET /api/v1/plans?from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /api/v1/plans/{date}`
- `GET /api/v1/plans/{date}/html`
- `GET /api/v1/sync-status`

The API never returns the internal schedule source. Original student HTML is delivered unchanged; teacher HTML is stored only after conversion to the student-facing format.

## DSB protocol status

Sanitized authenticated menu responses from both configured accounts confirmed the gzip/Base64 JSON envelope, `Resultcode`, and `Inhalte > Pläne` menu path on 2026-11-23. A controlled staging sync then fetched and parsed six student-compatible plans successfully. Genuinely empty, authentication-failure, and transient-failure responses have not yet been observed, so those cases remain a production verification gap. The worker distinguishes a successful empty menu from transport, HTTP, decoding and DSB-result failures. See [tools/README.md](tools/README.md) for the local capture helper. Never put DSB credentials in source control or send them in chat.

## Data and deployment

SQLite and schedule bodies live in `DATA_DIRECTORY` (default `/data` in Compose). OCI remains the source of truth: only finalized student-compatible plan records are published from its worker to the separate Cloudflare read API. DSB credentials stay on OCI; Cloudflare receives schedule HTML and a publisher bearer token only. The Cloudflare Worker is deployed at `https://dsb-bot-api.dsb-bot.workers.dev` with D1 in the EU jurisdiction. The OCI publisher is installed and its current seven plans are live in D1. The existing frontend's API configuration now points at Cloudflare and is published on GitHub Pages. The OCI `dsb-sync.timer` is enabled every five minutes and has passed multiple scheduled runs. The daily backup timer uploads SQLite snapshots to the private OCI Standard-tier bucket `dsb-bot-backups`; the first 192,512-byte backup passed SQLite integrity and OCI checksum verification. A bucket-scoped lifecycle rule deletes backup objects after 30 days. Discord plan and warning webhooks are configured on the OCI host with mode-600 `.env`; warnings use the configured role mention. No test Discord message has been sent. A restore rehearsal remains open; see [ROADMAP.md](ROADMAP.md). See [deploy/README.md](deploy/README.md) for host configuration.
