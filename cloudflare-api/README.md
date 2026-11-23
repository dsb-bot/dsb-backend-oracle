# Cloudflare read API

This Worker is the public, read-only API for already-processed schedules. OCI remains the only DSB client and source of truth. The OCI worker pushes final plan bytes to D1 over HTTPS using a private bearer token. DSB and Discord credentials never go to Cloudflare. The public API omits schedule provenance.

## Provision and deploy

From this directory, install the locked dependencies and authenticate Wrangler in the browser:

```powershell
npm ci
npx wrangler login
```

Create the D1 database in the EU jurisdiction; Wrangler updates `wrangler.jsonc` with its binding and ID:

```powershell
npx wrangler d1 create dsb-bot-api --binding DB --jurisdiction eu --update-config
```

Apply the schema and deploy the Worker:

```powershell
npm run db:migrate:remote
npm run deploy
```

With `workers_dev` enabled, Cloudflare prints a stable `https://dsb-bot-api.<account-subdomain>.workers.dev` URL. Check `/healthz` before configuring OCI. The `workers.dev` address is intended for hobby use and does not provide a business-critical availability commitment.

Generate a long random token locally and add the same value as the Cloudflare Worker secret `PUBLISH_TOKEN` and OCI `.env` setting `CLOUDFLARE_PUBLISH_TOKEN`. Never put it in `wrangler.jsonc`, Git, frontend code, or chat. Set OCI `CLOUDFLARE_API_URL` to the Worker origin, without a path. Keep the file mode at `600`.

After the OCI Worker image contains the publisher integration and the two host settings are present, publish the existing SQLite snapshot once:

```sh
sudo docker compose --profile sync run --rm --no-deps worker python -m dsb_bot.publish_pending --all
```

Normal successful sync runs enqueue changed plans transactionally and retry failed uploads from the SQLite outbox. Only the final, already-prioritized plan bytes are sent. An empty DSB result never deletes a D1 row.

## API

- `GET /healthz`
- `GET /api/v1/plans?from=YYYY-MM-DD&to=YYYY-MM-DD`
- `GET /api/v1/plans/YYYY-MM-DD`
- `GET /api/v1/plans/YYYY-MM-DD/html`
- `GET /api/v1/sync-status`

Only the two `/internal/v1/*` POST routes accept writes, and both require `Authorization: Bearer <PUBLISH_TOKEN>`. They are intended for server-to-server use. Public read routes return student-compatible plans and permit unauthenticated GET requests for the frontend.

D1 Free currently limits each database to 500 MB and each BLOB/string/row to 2 MB; the account-wide storage and daily read/write limits also apply. Monitor D1 usage. If any individual archived HTML exceeds the row limit, store its body in object storage and keep a key in D1 instead.

The current frontend must set `window.DSB_API_BASE_URL` to the deployed Worker origin. Since API calls are cross-origin, this Worker allows public GET CORS requests; no credentials or write capability are exposed to browser code.
