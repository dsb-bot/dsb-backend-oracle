"""Publish the SQLite outbox to Cloudflare without contacting DSB."""

from __future__ import annotations

import argparse
import logging
import sys

from dsb_bot.cloudflare_publisher import CloudflarePublisher
from dsb_bot.config import Settings
from dsb_bot.repository import ScheduleRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Queue the current SQLite snapshot before publishing it.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    if not settings.cloudflare_api_url or not settings.cloudflare_publish_token:
        parser.error("CLOUDFLARE_API_URL and CLOUDFLARE_PUBLISH_TOKEN are required")

    repository = ScheduleRepository(settings.database_path)
    repository.initialize()
    if args.all:
        repository.enqueue_all_for_publication()

    publisher = CloudflarePublisher(
        settings.cloudflare_api_url, settings.cloudflare_publish_token
    )
    try:
        published = publisher.publish_pending(
            repository, last_successful_sync=repository.last_successful_sync()
        )
    except Exception:
        logging.getLogger(__name__).exception("Cloudflare publication did not finish")
        return 1
    finally:
        publisher.close()

    print(f"Published plan records: {published}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
