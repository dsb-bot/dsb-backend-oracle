from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from dsb_bot.api import create_app
from dsb_bot.config import Settings
from dsb_bot.models import PlanCandidate, PlanSource
from dsb_bot.repository import ScheduleRepository


def test_read_only_api_lists_and_delivers_student_html(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    body = b"<html>student plan unchanged</html>"
    repository.save(
        PlanCandidate(
            date=date(2026, 11, 6),
            title="6.11.2026 Freitag",
            html_content=body,
            content_type="text/html; charset=windows-1252",
            source=PlanSource.STUDENT,
            retrieved_at=datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc),
        )
    )
    settings = Settings(
        database_path=tmp_path / "plans.sqlite3",
        frontend_origin="https://dsb-bot.github.io",
        dsb_username=None,
        dsb_password=None,
        dsb_teacher_username=None,
        dsb_teacher_password=None,
        discord_warning_webhook=None,
        discord_plans_webhook=None,
        discord_ping_role_id=None,
    )

    with TestClient(create_app(settings, repository)) as client:
        plans = client.get("/api/v1/plans")
        html = client.get("/api/v1/plans/2026-11-06/html")
        missing = client.get("/api/v1/plans/2026-11-07/html")

    assert plans.status_code == 200
    assert plans.json()["plans"][0]["html_url"] == "/api/v1/plans/2026-11-06/html"
    assert "source" not in plans.json()["plans"][0]
    assert html.status_code == 200
    assert html.content == body
    assert html.headers["content-type"] == "text/html; charset=windows-1252"
    assert missing.status_code == 404
