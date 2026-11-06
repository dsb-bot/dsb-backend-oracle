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

The worker performs one run and exits. It is not automatically scheduled locally; the planned OCI host timer is a later deployment task. Do not run this command against DSB until credentials and the current DSB response behavior have been verified.

## API

- `GET /healthz`
- `GET /api/v1/plans?from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /api/v1/plans/{date}`
- `GET /api/v1/plans/{date}/html`
- `GET /api/v1/sync-status`

The API never returns the internal schedule source. Original student HTML is delivered unchanged; teacher HTML is stored only after conversion to the student-facing format.

## DSB protocol status

The request/response decoder currently follows the existing `dsb_client.py` implementation. Its expected gzip/Base64 JSON envelope has not been confirmed against a live authenticated DSB response. The worker distinguishes a successful empty menu from transport, HTTP, decoding and DSB-result failures, but production readiness still requires sanitized successful, empty and failed response samples. Never put DSB credentials in source control or send them in chat.

## Data and deployment

SQLite and schedule bodies live in `DATA_DIRECTORY` (default `/data` in Compose). Use a persistent volume for deployment. OCI provisioning, public exposure, HTTPS, scheduled execution, backups and frontend cutover are intentionally not performed by this local implementation.
