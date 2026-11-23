# Deployment preparation

These files prepare a single Linux Docker host for an OCI Always Free Ampere A1 instance. They do not provision the OCI instance, DNS, firewall rules, secrets, or an external backup destination.

## OCI Always Free target

The current Always Free allocation is 1,500 OCPU-hours and 9,000 GB-hours per month, equivalent to up to 2 OCPUs and 12 GB RAM for one VM.Standard.A1.Flex instance. The tenancy also has 200 GB total Always Free boot/block volume storage, with a 50 GB default boot volume. Create Always Free resources in the tenancy's home region and verify the Always Free eligible label before provisioning. A1 capacity may be temporarily unavailable in a region. Oracle may reclaim instances it classifies as idle, so monitor utilization and availability after launch. See Oracle's [Always Free resource limits](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

For this service, one A1 VM with 1 OCPU, 6 GB RAM, Ubuntu ARM64, and a 50 GB boot volume is a reasonable starting point. The Docker image and CI are configured to support ARM64. Confirm the selected image and shape are marked Always Free in the OCI console; do not create paid resources to work around regional capacity without reviewing the cost first.

The existing frontend is served from the same OCI host by Caddy. Keep its checkout as a sibling directory at `/opt/dsb-beta` next to `/opt/dsb-backend-oracle`; Compose mounts that checkout read-only into Caddy. Caddy serves the site at the root domain and proxies `/api/*` and `/healthz` to FastAPI on the private Compose network. A domain is optional: Caddy 2.11.4 can request a publicly trusted Let's Encrypt IP certificate with the `shortlived` ACME profile. Set `.env` `API_DOMAIN` and `FRONTEND_ORIGIN` to the VM's public IPv4 address (without a scheme in `API_DOMAIN`). Allow TCP ports 80/443 in both OCI network security rules and the VM firewall. The certificate is valid for 160 hours, so keep Caddy running for automatic renewal. The frontend uses the same origin for its API, so it does not need a separate API hostname.

## Prerequisites

- A supported Linux host with Docker Engine and the Docker Compose plugin.
- A public IPv4 address; Caddy 2.11.4 and inbound TCP 80/443 are required for trusted HTTPS.
- Verified DSB behavior from sanitized authenticated success, empty, authentication-failure, and transient-failure samples.
- A reviewed API/frontend contract and a separate frontend release plan.
- DSB credentials and optional Discord webhook secrets provisioned on the host only.

## First deployment

1. Clone this repository to `/opt/dsb-backend-oracle` and the current frontend checkout to `/opt/dsb-beta`; check out the reviewed release in each.
2. From the backend directory, create `.env` from `.env.example`; set `API_DOMAIN`, DSB credentials, and any notification secrets. Set `FRONTEND_ORIGIN` to `https://<API_DOMAIN>`. Restrict the file with `chmod 600 .env`.
3. Confirm `/data` is backed by the named Docker volume and ensure the VM has enough persistent disk space.
4. Start the API and HTTPS proxy:

   ```sh
   docker compose -f compose.yaml -f compose.production.yaml up -d --build api caddy
   ```

5. Check `https://$API_DOMAIN/healthz`, then install and enable the scheduled worker:

   ```sh
   install -m 0644 deploy/systemd/dsb-sync.service /etc/systemd/system/
   install -m 0644 deploy/systemd/dsb-sync.timer /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now dsb-sync.timer
   ```

6. Inspect the first worker result and stored schedule data before switching the existing frontend to this API.

## Backups

`deploy/backup.sh` uses SQLite's online backup API, verifies the snapshot, and keeps 30 days of local copies. The systemd backup service requires an offsite destination. For OCI, install the OCI CLI on the host, enable instance principals for the VM, create a private Object Storage bucket, and set `OCI_BACKUP_BUCKET=<bucket-name>` in `/etc/dsb-bot/backup.env`; do not put API keys in this file. A bucket-scoped create-only policy can follow this pattern:

```text
Allow dynamic-group <DSB_INSTANCE_GROUP> to manage objects in compartment <BACKUP_COMPARTMENT> where all {target.bucket.name = '<BUCKET_NAME>', request.permission = 'OBJECT_CREATE'}
```

The uploader uses single-part, no-overwrite uploads so this create-only grant is sufficient. Configure bucket retention/lifecycle and encryption to match the recovery policy, then rehearse restoring a backup into a fresh database before production. Oracle documents the CLI's `instance_principal` authentication and `oci os object put` upload operation in its [CLI reference](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html), and its [IAM examples](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/commonpolicies.htm) document bucket-scoped object permissions.

Install `dsb-backup.service` and `dsb-backup.timer` like the sync units to schedule the daily snapshots. The provider, bucket name, retention period, and recovery target depend on the deployment account and must be selected by the operator.

Install the backup timer with:

```sh
install -m 0644 deploy/systemd/dsb-backup.service /etc/systemd/system/
install -m 0644 deploy/systemd/dsb-backup.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now dsb-backup.timer
```

To rehearse a restore on a staging host, copy an offsite backup to a protected local path and run `CONFIRM_RESTORE=YES deploy/restore.sh /path/to/backup.sqlite3`. The script first creates a new encrypted offsite backup of the current database, stops the API, validates the selected database, restores it atomically, then restarts the API. Verify the restored plan dates and API responses before considering the rehearsal complete.

## Cutover

Keep the existing frontend data source available during staging. Compare backend output and historical coverage, verify CORS from the real frontend origin, and rehearse rollback. Switch the existing frontend only after explicit production approval; preserve its current and historical views, plan viewer, reload behavior, and other established UI features.

## Existing frontend configuration

The frontend repo remains separate at `v4-oracle/dsb-beta`, but Caddy serves it on the OCI host. `assets/js/apiConfig.js` uses `window.location.origin`, so the page and API share the deployment hostname. Test the plan list, historical view, and opening an HTML plan at the HTTPS site before considering the deployment live.
## Historical data migration

The preserved HTML plans are historical reference data and remain out of Git because they may contain student information. For staging only, transfer the archive to the host over a protected channel into a private directory outside the web root. Grant the API container's UID `10001` read access while keeping directories and files private. Remove the temporary copy after a verified import and backup. The reviewed source manifest is tracked at `migrations/archive-sources.csv`.

With the API container running, mount the private archive and manifest read-only, then run the import against the shared `/data` volume in dry-run mode first:

```sh
docker compose run --rm \
  -v /secure/path/plans:/archive:ro \
  -v "$PWD/migrations/archive-sources.csv:/archive-sources.csv:ro" \
  api python -m dsb_bot.archive_import /archive \
    --database /data/dsb.sqlite3 --manifest /archive-sources.csv
```

Review the validated count and provenance, then repeat with `--apply`. The current confirmed manifest expects 225 non-empty plans: 219 student plans and six converted teacher plans. It skips the empty `2026-06-12.html` placeholder. Back up the database before and after import and verify date coverage from `/api/v1/plans` before switching the frontend.
