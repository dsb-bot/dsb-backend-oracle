import json
import logging
import sys
from datetime import datetime, timezone

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
    try:
        result = Synchronizer(
            repository,
            student_client=student_client,
            teacher_client=teacher_client,
        ).run_once()
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
                    "changed_dates": [item.isoformat() for item in result.changed_dates],
                    "errors": list(result.errors),
                },
                ensure_ascii=False,
            )
        )
        return 1 if result.status == "failed" else 0
    finally:
        student_client.close()
        if teacher_client is not None:
            teacher_client.close()
        notifier.close()


if __name__ == "__main__":
    sys.exit(main())
