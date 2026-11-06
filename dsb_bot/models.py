from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class PlanSource(StrEnum):
    STUDENT = "student"
    TEACHER_CONVERTED = "teacher_converted"


@dataclass(frozen=True)
class FetchedDocument:
    title: str
    detail_url: str
    body: bytes
    content_type: str


@dataclass(frozen=True)
class PlanCandidate:
    date: date
    title: str
    html_content: bytes
    content_type: str
    source: PlanSource
    retrieved_at: datetime


@dataclass(frozen=True)
class StoredPlan:
    date: date
    title: str
    html_content: bytes
    content_type: str
    source: PlanSource
    content_hash: str
    source_retrieved_at: datetime
    updated_at: datetime
