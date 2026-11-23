"""Publish stored, student-compatible plans to the read API's Cloudflare D1 store."""

from __future__ import annotations

import base64
import logging
from urllib.parse import urlsplit

import httpx

from dsb_bot.repository import ScheduleRepository


logger = logging.getLogger(__name__)
PUBLISH_BATCH_SIZE = 5


class CloudflarePublishError(RuntimeError):
    """Raised when a pending plan batch cannot be delivered."""


class CloudflarePublisher:
    def __init__(
        self,
        api_url: str,
        publish_token: str,
        *,
        client: httpx.Client | None = None,
    ):
        parsed_url = urlsplit(api_url)
        local_http = parsed_url.scheme == "http" and parsed_url.hostname in {
            "localhost",
            "127.0.0.1",
            "::1",
        }
        if (
            (parsed_url.scheme != "https" and not local_http)
            or not parsed_url.hostname
            or parsed_url.username
            or parsed_url.password
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("Cloudflare API URL must use HTTPS")
        self.api_url = api_url.rstrip("/")
        self.publish_token = publish_token
        self._client = client or httpx.Client(timeout=20, follow_redirects=False)
        self._owns_client = client is None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def publish_pending(
        self,
        repository: ScheduleRepository,
        *,
        last_successful_sync: str | None = None,
    ) -> int:
        published = 0
        headers = {"Authorization": f"Bearer {self.publish_token}"}
        while plans := repository.pending_publication(PUBLISH_BATCH_SIZE):
            payload = {
                "plans": [
                    {
                        "date": plan.date.isoformat(),
                        "title": plan.title,
                        "content_type": plan.content_type,
                        "content_hash": plan.content_hash,
                        "updated_at": plan.updated_at.isoformat(),
                        "html_base64": base64.b64encode(plan.html_content).decode(
                            "ascii"
                        ),
                    }
                    for plan in plans
                ]
            }
            try:
                response = self._client.post(
                    f"{self.api_url}/internal/v1/plans",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "Cloudflare plan publication failed (%s)", type(exc).__name__
                )
                raise CloudflarePublishError(
                    "A plan batch could not be published"
                ) from None
            repository.acknowledge_published(plans)
            published += len(plans)

        if last_successful_sync is not None:
            try:
                response = self._client.post(
                    f"{self.api_url}/internal/v1/sync-status",
                    headers=headers,
                    json={"last_successful_sync": last_successful_sync},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.warning(
                    "Cloudflare sync-status publication failed (%s)",
                    type(exc).__name__,
                )
                raise CloudflarePublishError(
                    "The sync status could not be published"
                ) from None
        return published
