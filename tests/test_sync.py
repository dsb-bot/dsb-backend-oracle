from datetime import date, datetime, timezone

from dsb_bot.models import FetchedDocument, PlanCandidate, PlanSource
from dsb_bot.repository import ScheduleRepository
from dsb_bot.sync import Synchronizer


class FakeClient:
    def __init__(self, documents=None, error=None):
        self.documents = documents or []
        self.error = error

    def fetch_schedules(self):
        if self.error:
            raise self.error
        return self.documents


def plan(target_date, source, body):
    return PlanCandidate(
        date=target_date,
        title="Plan",
        html_content=body,
        content_type="text/html; charset=utf-8",
        source=source,
        retrieved_at=datetime.now(timezone.utc),
    )


def test_failed_student_request_does_not_destroy_existing_schedule(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    target_date = date(2026, 11, 9)
    repository.save(plan(target_date, PlanSource.STUDENT, b"valid"))
    sync = Synchronizer(
        repository,
        student_client=FakeClient(error=RuntimeError("offline")),
        teacher_client=None,
        clock=lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
    )

    result = sync.run_once()

    stored = repository.get(target_date)
    assert stored is not None
    assert stored.html_content == b"valid"
    assert result.student_status == "failed"


def test_successful_empty_student_result_preserves_existing_schedule(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    target_date = date(2026, 11, 6)
    repository.save(plan(target_date, PlanSource.STUDENT, b"valid"))
    sync = Synchronizer(
        repository,
        student_client=FakeClient(),
        teacher_client=None,
        clock=lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
    )

    result = sync.run_once()

    stored = repository.get(target_date)
    assert result.student_status == "empty"
    assert stored is not None
    assert stored.html_content == b"valid"


def test_student_date_window_uses_frankfurt_midnight(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    student_html = b"""<html><body><div class="mon_title">7.11.2026 Samstag</div>
    <table class="mon_list"><tr><th>Plan</th></tr></table></body></html>"""
    student = FakeClient(
        [
            FetchedDocument(
                title="student tomorrow",
                detail_url="https://example.invalid/student.html",
                body=student_html,
                content_type="text/html; charset=utf-8",
            )
        ]
    )
    sync = Synchronizer(
        repository,
        student_client=student,
        teacher_client=None,
        clock=lambda: datetime(2026, 11, 6, 23, 30, tzinfo=timezone.utc),
    )

    sync.run_once()

    assert repository.get(date(2026, 11, 7)) is not None


def test_student_source_window_and_teacher_calendar_cutoff(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    student_html = b"""<html><body><div class="mon_title">6.11.2026 Freitag</div>
    <table class="mon_list"><tr><th>Plan</th></tr></table></body></html>"""
    teacher_html = b"""<html><body>
    <table class="mon_head"></table><div class="mon_title">7.11.2026 Samstag</div>
    <table class="mon_list"><tr><th>Vertreter</th><th>Stunde</th><th>Klasse(n)</th>
    <th>Fach</th><th>Raum</th><th>(Lehrer)</th><th>Vertr. von</th><th>Art</th>
    <th>Text</th></tr></table>
    <table class="mon_head"></table><div class="mon_title">8.11.2026 Sonntag</div>
    <table class="mon_list"><tr><th>Vertreter</th><th>Stunde</th><th>Klasse(n)</th>
    <th>Fach</th><th>Raum</th><th>(Lehrer)</th><th>Vertr. von</th><th>Art</th>
    <th>Text</th></tr></table></body></html>"""
    student = FakeClient(
        [
            FetchedDocument(
                title="student today",
                detail_url="https://example.invalid/student.html",
                body=student_html,
                content_type="text/html; charset=utf-8",
            )
        ]
    )
    teacher = FakeClient(
        [
            FetchedDocument(
                title="Lehrerzimmer morgen",
                detail_url="https://example.invalid/teacher.html",
                body=teacher_html,
                content_type="text/html; charset=utf-8",
            )
        ]
    )
    sync = Synchronizer(
        repository,
        student_client=student,
        teacher_client=teacher,
        clock=lambda: datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc),
    )

    result = sync.run_once()

    assert result.changed_dates == (date(2026, 11, 6), date(2026, 11, 8))
    assert repository.get(date(2026, 11, 7)) is None
    assert repository.get(date(2026, 11, 8)) is not None
    assert repository.get(date(2026, 11, 8)).source is PlanSource.TEACHER_CONVERTED
