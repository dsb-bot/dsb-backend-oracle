# Sanitized DSB response samples

The backend's DSB protocol has not been verified against an authenticated live response. This helper makes one menu request using the local `DSB_USER` and `DSB_PASS` settings and writes a sanitized response fixture under `captures/`. The output directory is Git-ignored.

From the repository root, after installing the project dependencies and setting the two values in a local `.env` file, run:

```powershell
python tools/capture_dsb_response.py --label success
```

To sample the optional teacher account as well, run:

```powershell
python tools/capture_dsb_response.py --label teacher-success --account teacher
```

Repeat when you observe a genuinely empty menu, a DSB result/authentication error, or a naturally occurring transport/HTTP error. The script reports which outcome it observed; the label is only the filename. It does not deliberately send invalid credentials or induce a failure. Do not repeatedly retry DSB errors.

The helper captures only the menu request, never the credentials or detailed schedule HTML. It retains the JSON/gzip/Base64 envelope and key structure, replaces account and school-specific strings, preserves only the menu labels needed to inspect the current parser path, replaces detail URLs with `example.invalid`, and retains dates/result codes. Review each file before sharing it. Never share `.env`, a raw response, personal schedule data, or credential values.

If a naturally occurring transport failure has no HTTP response body, the helper writes a small outcome summary rather than inventing a DSB response sample. An administrator can provide the separate authentication-failure case from an already observed failure; no credential needs to be shared.
