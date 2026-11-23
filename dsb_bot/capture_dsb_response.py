"""Capture a structurally useful, sanitized DSB menu response fixture."""

from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

from dsb_bot.dsb_client import DSBClient, DSBRequestError


SAFE_LABEL = re.compile(r"^[a-z][a-z0-9_-]{0,39}$")
KNOWN_MENU_TITLES = {"inhalte", "pläne", "plÃ¤ne"}
DATE_VALUE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def sanitize(value, key: str | None = None):
    """Keep protocol shape while removing account, school, and plan-specific values."""
    normalized_key = (key or "").lower()
    if (
        normalized_key == "id"
        or normalized_key.endswith("id")
        or any(
            secret in normalized_key
            for secret in ("password", "userid", "username", "token", "school", "account")
        )
    ):
        return "[REDACTED]"
    if key == "Detail":
        return "https://example.invalid/redacted.html"
    if key == "Title":
        if isinstance(value, str) and value.casefold() in KNOWN_MENU_TITLES:
            return value
        return "[REDACTED]"
    if key == "Date":
        return value if isinstance(value, str) and DATE_VALUE.fullmatch(value) else "[REDACTED]"
    if key == "Resultcode":
        return value if isinstance(value, (int, float, type(None))) else "[REDACTED]"
    if isinstance(value, dict):
        return {name: sanitize(item, name) for name, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item, key) for item in value]
    if isinstance(value, str):
        return "[REDACTED]"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return "[REDACTED]"


def sanitize_envelope(envelope: dict) -> dict:
    clean_envelope = {}
    for key, value in envelope.items():
        if key == "d" and isinstance(value, str):
            try:
                decoded = json.loads(gzip.decompress(base64.b64decode(value)))
            except (ValueError, OSError, TypeError, EOFError):
                clean_envelope[key] = "[UNDECODABLE PAYLOAD REDACTED]"
            else:
                safe_payload = sanitize(decoded)
                compressed = gzip.compress(
                    json.dumps(safe_payload, ensure_ascii=False).encode("utf-8")
                )
                clean_envelope[key] = base64.b64encode(compressed).decode("ascii")
        else:
            clean_envelope[key] = sanitize(value, key)
    return clean_envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--label",
        required=True,
        help="A short label such as success, empty, auth_failure, or transport_failure.",
    )
    parser.add_argument(
        "--account",
        choices=("student", "teacher"),
        default="student",
        help="Which locally configured account to use (default: student).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("captures"),
        help="Local-only output directory (ignored by Git).",
    )
    args = parser.parse_args(argv)
    if not SAFE_LABEL.fullmatch(args.label):
        parser.error("label must start with a lowercase letter and contain only a-z, 0-9, _ or -")

    load_dotenv()
    account_prefix = "DSB_TEACHER_" if args.account == "teacher" else "DSB_"
    username = os.getenv(f"{account_prefix}USER")
    password = os.getenv(f"{account_prefix}PASS")
    if not username or not password:
        names = f"{account_prefix}USER and {account_prefix}PASS"
        print(f"Set {names} in the local .env file first.", file=sys.stderr)
        return 2

    args.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_path = args.output_dir / f"{args.label}-{timestamp}.json"
    response_summary: dict[str, object] = {"http_status": None, "fixture": None}

    def capture_response(response: httpx.Response) -> None:
        if not response.request.url.path.lower().endswith("/getdata"):
            return
        response.read()
        response_summary["http_status"] = response.status_code
        try:
            envelope = response.json()
        except ValueError:
            fixture = {
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "body": "[NON-JSON BODY REDACTED]",
                "body_bytes": len(response.content),
            }
        else:
            if isinstance(envelope, dict):
                fixture = sanitize_envelope(envelope)
            else:
                fixture = {"http_status": response.status_code, "body": "[REDACTED]"}
        response_summary["fixture"] = fixture
        output_path.write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    http = httpx.Client(event_hooks={"response": [capture_response]}, timeout=15)
    dsb = DSBClient(username, password, client=http)
    try:
        links = dsb.fetch_menu_links()
        outcome = "success_with_links" if links else "successful_empty_menu"
        link_count = len(links)
    except DSBRequestError as exc:
        outcome = "dsb_result_or_decode_error"
        link_count = None
        response_summary["error_type"] = type(exc).__name__
    except httpx.HTTPError as exc:
        outcome = "transport_or_http_error"
        link_count = None
        response_summary["error_type"] = type(exc).__name__
    finally:
        dsb.close()
        http.close()

    if response_summary["fixture"] is None:
        output_path.write_text(
            json.dumps(
                {
                    "capture_label": args.label,
                    "http_status": response_summary["http_status"],
                    "outcome": outcome,
                    "body": "No HTTP response body was available to capture.",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"Observed outcome: {outcome}; menu links: {link_count}")
    print(f"Sanitized fixture written to: {output_path.resolve()}")
    print("Review the fixture before sharing it; never share .env or raw captures.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
