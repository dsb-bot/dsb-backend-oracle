import json
import logging
import sys
from datetime import datetime, timezone

from dsb_bot.cloudflare_publisher import CloudflarePublisher
from dsb_bot.config import Settings
from dsb_bot.discord_notifier import DiscordNotifier
from dsb_bot.dsb_client import DSBClient
from dsb_bot.repository import ScheduleRepository
from dsb_bot.sync import Synchronizer


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # HTTP client INFO logs include full request URLs; Discord webhook URLs
    # contain bearer-like tokens, so keep those URLs out of worker logs.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings.from_env()
    try:
        settings.validate_worker()
    except ValueError as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 2

    repository = ScheduleRepository(settings.database_path)
    repository.initialize()
    student_client = DSBClient(settings.dsb_username or "", settings.dsb_password or "")
    teacher_client = None
    if settings.dsb_teacher_username and settings.dsb_teacher_password:
        teacher_client = DSBClient(
            settings.dsb_teacher_username, settings.dsb_teacher_password
        )
    notifier = DiscordNotifier(
        settings.discord_warning_webhook,
        settings.discord_plans_webhook,
        settings.discord_ping_role_id,
    )
    publisher = None
    if settings.cloudflare_api_url and settings.cloudflare_publish_token:
        publisher = CloudflarePublisher(
            settings.cloudflare_api_url, settings.cloudflare_publish_token
        )
    cloudflare_status = "disabled" if publisher is None else "success"
    try:
        result = Synchronizer(
            repository,
            student_client=student_client,
            teacher_client=teacher_client,
        ).run_once()
        if publisher is not None:
            try:
                publisher.publish_pending(
                    repository,
                    last_successful_sync=(
                        result.finished_at.isoformat()
                        if result.status == "success"
                        else None
                    ),
                )
            except Exception:
                cloudflare_status = "failed"
                logging.getLogger(__name__).exception(
                    "Cloudflare publication failed; queued plans will be retried"
                )
        if result.changed_dates:
            plans = [
                (target.isoformat(), plan.title)
                for target in result.changed_dates
                if (plan := repository.get(target)) is not None
            ]
            notifier.send_plan_update(plans)
        if result.status == "failed" and repository.should_send_warning(
            "sync-failure", datetime.now(timezone.utc), cooldown_seconds=3600
        ):
            notifier.send_warning("Ein DSB-Synchronisierungslauf ist fehlgeschlagen.")
        print(
            json.dumps(
                {
                    "status": result.status,
                    "student_status": result.student_status,
                    "teacher_status": result.teacher_status,
                    "cloudflare_status": cloudflare_status,
                    "changed_dates": [item.isoformat() for item in result.changed_dates],
                    "errors": list(result.errors),
                },
                ensure_ascii=False,
            )
        )
        return 1 if result.status == "failed" or cloudflare_status == "failed" else 0
    finally:
        student_client.close()
        if teacher_client is not None:
            teacher_client.close()
        notifier.close()
        if publisher is not None:
            publisher.close()


if __name__ == "__main__":
    sys.exit(main())
