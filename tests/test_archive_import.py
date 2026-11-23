from datetime import datetime, timezone

import pytest

from dsb_bot.archive_import import (
    ArchiveValidationError,
    import_archive,
    load_archive,
    load_manifest,
)
from dsb_bot.models import PlanSource
from dsb_bot.repository import ScheduleRepository


def plan_html(target_date: str) -> bytes:
    year, month, day = target_date.split("-")
    return (
        '<html><head><meta charset="utf-8"></head><body>'
        f'<div class="mon_title">{int(day)}.{int(month)}.{year} Freitag</div>'
        '<table class="mon_list"><tr><th>Plan</th></tr></table>'
        '</body></html>'
    ).encode()


def test_archive_validation_preserves_html_and_requires_explicit_apply(tmp_path):
    archive = tmp_path / "plans"
    archive.mkdir()
    body = plan_html("2026-11-06")
    (archive / "2026-11-06.html").write_bytes(body)
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()

    candidates = load_archive(
        archive,
        PlanSource.TEACHER_CONVERTED,
        retrieved_at=datetime(2026, 11, 6, tzinfo=timezone.utc),
    )
    assert candidates[0].html_content == body
    assert candidates[0].source is PlanSource.TEACHER_CONVERTED
    assert repository.count() == 0

    assert import_archive(archive, repository, PlanSource.TEACHER_CONVERTED) == (1, 0)
    assert repository.count() == 0
    assert import_archive(
        archive, repository, PlanSource.TEACHER_CONVERTED, apply=True
    ) == (1, 0)
    assert repository.count() == 1


def test_archive_date_mismatch_fails_before_any_write(tmp_path):
    archive = tmp_path / "plans"
    archive.mkdir()
    (archive / "2026-11-06.html").write_bytes(plan_html("2026-11-07"))
    repository = ScheduleRepository(tmp_path / "plans.sqlite3")
    repository.initialize()

    with pytest.raises(ArchiveValidationError, match="nothing was imported"):
        import_archive(archive, repository, PlanSource.STUDENT, apply=True)
    assert repository.count() == 0


def test_mixed_archive_requires_complete_per_date_provenance(tmp_path):
    archive = tmp_path / "plans"
    archive.mkdir()
    (archive / "2026-11-06.html").write_bytes(plan_html("2026-11-06"))
    manifest = tmp_path / "sources.csv"
    manifest.write_text("date,source\n2026-11-06,teacher_converted\n", encoding="utf-8")

    source_by_date = load_manifest(manifest)
    plans = load_archive(archive, None, source_by_date=source_by_date)
    assert plans[0].source is PlanSource.TEACHER_CONVERTED

    with pytest.raises(ArchiveValidationError, match="no provenance"):
        load_archive(archive, None, source_by_date={})
