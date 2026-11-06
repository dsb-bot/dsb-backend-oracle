from datetime import date, datetime, timezone

from dsb_bot.models import PlanCandidate, PlanSource
from dsb_bot.repository import ScheduleRepository


def candidate(source: PlanSource, content: bytes, title: str = "Plan") -> PlanCandidate:
    return PlanCandidate(
        date=date(2026, 11, 9),
        title=title,
        html_content=content,
        content_type="text/html; charset=utf-8",
        source=source,
        retrieved_at=datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc),
    )


def test_one_current_plan_per_date_and_student_priority(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()

    assert repository.save(candidate(PlanSource.TEACHER_CONVERTED, b"teacher"))
    assert repository.save(candidate(PlanSource.STUDENT, b"student"))
    assert not repository.save(candidate(PlanSource.TEACHER_CONVERTED, b"new teacher"))

    stored = repository.get(date(2026, 11, 9))
    assert stored is not None
    assert stored.source is PlanSource.STUDENT
    assert stored.html_content == b"student"
    assert repository.count() == 1


def test_identical_schedule_is_not_rewritten(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    plan = candidate(PlanSource.STUDENT, b"same")

    assert repository.save(plan)
    original = repository.get(plan.date)
    assert original is not None

    assert not repository.save(plan)
    current = repository.get(plan.date)
    assert current is not None
    assert current.updated_at == original.updated_at


def test_student_schedule_replaces_existing_teacher_schedule(tmp_path):
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()
    plan_date = date(2026, 11, 9)

    assert repository.save(
        PlanCandidate(
            date=plan_date,
            title="Converted plan",
            html_content=b"converted",
            content_type="text/html; charset=utf-8",
            source=PlanSource.TEACHER_CONVERTED,
            retrieved_at=datetime(2026, 11, 6, 11, 0, tzinfo=timezone.utc),
        )
    )
    assert repository.save(candidate(PlanSource.STUDENT, b"original"))

    stored = repository.get(plan_date)
    assert stored is not None
    assert stored.source is PlanSource.STUDENT
    assert stored.html_content == b"original"
    assert repository.count() == 1
