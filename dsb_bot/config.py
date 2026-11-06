import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_path: Path
    frontend_origin: str
    dsb_username: str | None
    dsb_password: str | None
    dsb_teacher_username: str | None
    dsb_teacher_password: str | None
    discord_warning_webhook: str | None
    discord_plans_webhook: str | None
    discord_ping_role_id: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        data_directory = Path(os.getenv("DATA_DIRECTORY", "./data"))
        database_path = Path(
            os.getenv("DATABASE_PATH", str(data_directory / "dsb.sqlite3"))
        )
        return cls(
            database_path=database_path,
            frontend_origin=os.getenv(
                "FRONTEND_ORIGIN", "https://dsb-bot.github.io"
            ),
            dsb_username=os.getenv("DSB_USER") or None,
            dsb_password=os.getenv("DSB_PASS") or None,
            dsb_teacher_username=os.getenv("DSB_TEACHER_USER") or None,
            dsb_teacher_password=os.getenv("DSB_TEACHER_PASS") or None,
            discord_warning_webhook=os.getenv("DISCORD_WEBHOOK_WARN") or None,
            discord_plans_webhook=os.getenv("DISCORD_WEBHOOK_PLANS") or None,
            discord_ping_role_id=os.getenv("DISCORD_PING_ROLE_ID") or None,
        )

    def validate_worker(self) -> None:
        missing = [
            name
            for name, value in (
                ("DSB_USER", self.dsb_username),
                ("DSB_PASS", self.dsb_password),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"Missing required worker configuration: {', '.join(missing)}")
        if bool(self.dsb_teacher_username) != bool(self.dsb_teacher_password):
            raise ValueError(
                "DSB_TEACHER_USER and DSB_TEACHER_PASS must either both be set or both be empty"
            )
