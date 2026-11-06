import logging
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from dsb_bot.models import FetchedDocument, PlanCandidate
from dsb_bot.parser import PlanParseError, parse_student_document, parse_teacher_document
from dsb_bot.repository import ScheduleRepository


logger = logging.getLogger(__name__)
FRANKFURT = ZoneInfo("Europe/Berlin")


@dataclass(frozen=True)
class SyncResult:
    status: str
    student_status: str
    teacher_status: str
    changed_dates: tuple[date, ...]
    errors: tuple[str, ...]
    started_at: datetime
    finished_at: datetime


class Synchronizer:
    def __init__(
        self,
        repository: ScheduleRepository,
        student_client,
        teacher_client=None,
        *,
        clock=None,
    ):
        self.repository = repository
        self.student_client = student_client
        self.teacher_client = teacher_client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def run_once(self) -> SyncResult:
        started_at = self.clock()
        local_today = started_at.astimezone(FRANKFURT).date()
        student_status = "failed"
        teacher_status = "disabled" if self.teacher_client is None else "failed"
        changed_dates: list[date] = []
        errors: list[str] = []

        try:
            student_documents = self.student_client.fetch_schedules()
            student_candidates = self._student_candidates(
                student_documents,
                local_today,
                local_today + timedelta(days=1),
                started_at,
            )
            student_status = "success" if student_candidates else "empty"
            for candidate in student_candidates:
                if self.repository.save(candidate):
                    changed_dates.append(candidate.date)
        except Exception as exc:
            student_status = "failed"
            errors.append(f"Student source: {exc}")
            logger.exception("Student schedule retrieval or processing failed")

        if self.teacher_client is not None:
            try:
                teacher_documents = self.teacher_client.fetch_schedules()
                teacher_candidates = self._teacher_candidates(
                    teacher_documents, local_today + timedelta(days=2), started_at
                )
                teacher_status = "success" if teacher_candidates else "empty"
                for candidate in teacher_candidates:
                    if self.repository.save(candidate):
                        changed_dates.append(candidate.date)
            except Exception as exc:
                teacher_status = "failed"
                errors.append(f"Teacher source: {exc}")
                logger.exception("Teacher schedule retrieval or processing failed")

        status = "failed" if student_status == "failed" or teacher_status == "failed" else "success"
        finished_at = self.clock()
        self.repository.record_sync(
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            student_status=student_status,
            teacher_status=teacher_status,
            errors=errors,
        )
        return SyncResult(
            status=status,
            student_status=student_status,
            teacher_status=teacher_status,
            changed_dates=tuple(sorted(set(changed_dates))),
            errors=tuple(errors),
            started_at=started_at,
            finished_at=finished_at,
        )

    @staticmethod
    def _student_candidates(
        documents: list[FetchedDocument],
        today: date,
        tomorrow: date,
        retrieved_at: datetime,
    ) -> list[PlanCandidate]:
        candidates: list[PlanCandidate] = []
        for document in documents:
            candidate = parse_student_document(
                document.body, document.content_type, retrieved_at=retrieved_at
            )
            if candidate.date in {today, tomorrow}:
                candidates.append(candidate)
        counts = Counter(candidate.date for candidate in candidates)
        duplicates = [target for target, count in counts.items() if count > 1]
        if duplicates:
            raise PlanParseError(
                f"Multiple student documents have the same date: {duplicates!r}"
            )
        return candidates

    @staticmethod
    def _teacher_candidates(
        documents: list[FetchedDocument],
        earliest_date: date,
        retrieved_at: datetime,
    ) -> list[PlanCandidate]:
        candidates: list[PlanCandidate] = []
        for document in documents:
            candidates.extend(
                parse_teacher_document(
                    document.body,
                    earliest_date=earliest_date,
                    retrieved_at=retrieved_at,
                    content_type=document.content_type,
                )
            )
        counts = Counter(candidate.date for candidate in candidates)
        duplicates = [target for target, count in counts.items() if count > 1]
        if duplicates:
            raise PlanParseError(
                f"Multiple teacher tables have the same date: {duplicates!r}"
            )
        return candidates
