import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator

from dsb_bot.models import PlanCandidate, PlanSource, StoredPlan


class ScheduleRepository:
    def __init__(self, database_path: Path | str):
        self.database_path = str(database_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self) -> None:
        if self.database_path != ":memory:":
            Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    date TEXT PRIMARY KEY,
                    source TEXT NOT NULL CHECK (
                        source IN ('student', 'teacher_converted')
                    ),
                    title TEXT NOT NULL,
                    html_content BLOB NOT NULL,
                    content_type TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    source_retrieved_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    student_status TEXT NOT NULL,
                    teacher_status TEXT NOT NULL,
                    error_message TEXT
                );
                CREATE TABLE IF NOT EXISTS notification_state (
                    name TEXT PRIMARY KEY,
                    last_sent_at TEXT NOT NULL
                );
                """
            )

    def save(self, candidate: PlanCandidate) -> bool:
        content_hash = hashlib.sha256(candidate.html_content).hexdigest()
        updated_at = datetime.now(timezone.utc).isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT source, title, content_hash, content_type "
                "FROM plans WHERE date = ?",
                (candidate.date.isoformat(),),
            ).fetchone()
            if (
                existing is not None
                and existing["source"] == PlanSource.STUDENT.value
                and candidate.source is PlanSource.TEACHER_CONVERTED
            ):
                return False

            if existing is not None and (
                existing["source"] == candidate.source.value
                and existing["title"] == candidate.title
                and existing["content_hash"] == content_hash
                and existing["content_type"] == candidate.content_type
            ):
                return False

            connection.execute(
                """
                INSERT INTO plans (
                    date, source, title, html_content, content_type,
                    content_hash, source_retrieved_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    source = excluded.source,
                    title = excluded.title,
                    html_content = excluded.html_content,
                    content_type = excluded.content_type,
                    content_hash = excluded.content_hash,
                    source_retrieved_at = excluded.source_retrieved_at,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate.date.isoformat(),
                    candidate.source.value,
                    candidate.title,
                    sqlite3.Binary(candidate.html_content),
                    candidate.content_type,
                    content_hash,
                    candidate.retrieved_at.isoformat(),
                    updated_at,
                ),
            )
            return True

    def get(self, target_date: date) -> StoredPlan | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM plans WHERE date = ?", (target_date.isoformat(),)
            ).fetchone()
        return self._stored_plan(row) if row is not None else None

    def list_plans(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[StoredPlan]:
        clauses: list[str] = []
        parameters: list[str] = []
        if start_date is not None:
            clauses.append("date >= ?")
            parameters.append(start_date.isoformat())
        if end_date is not None:
            clauses.append("date <= ?")
            parameters.append(end_date.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM plans{where} ORDER BY date", parameters
            ).fetchall()
        return [self._stored_plan(row) for row in rows]

    def count(self) -> int:
        with self._connection() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM plans").fetchone()[0])

    def last_successful_sync(self) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT finished_at FROM sync_runs "
                "WHERE status = 'success' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return str(row["finished_at"]) if row is not None else None

    def record_sync(
        self,
        *,
        started_at: datetime,
        finished_at: datetime,
        status: str,
        student_status: str,
        teacher_status: str,
        errors: list[str],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_runs (
                    started_at, finished_at, status, student_status,
                    teacher_status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    started_at.isoformat(),
                    finished_at.isoformat(),
                    status,
                    student_status,
                    teacher_status,
                    json.dumps(errors, ensure_ascii=False) if errors else None,
                ),
            )

    def should_send_warning(
        self, name: str, now: datetime, cooldown_seconds: int
    ) -> bool:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT last_sent_at FROM notification_state WHERE name = ?",
                (name,),
            ).fetchone()
            if row is not None:
                previous = datetime.fromisoformat(row["last_sent_at"])
                if (now - previous).total_seconds() < cooldown_seconds:
                    return False
            connection.execute(
                """
                INSERT INTO notification_state (name, last_sent_at)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET last_sent_at = excluded.last_sent_at
                """,
                (name, now.isoformat()),
            )
            return True

    @staticmethod
    def _stored_plan(row: sqlite3.Row) -> StoredPlan:
        return StoredPlan(
            date=date.fromisoformat(row["date"]),
            title=row["title"],
            html_content=bytes(row["html_content"]),
            content_type=row["content_type"],
            source=PlanSource(row["source"]),
            content_hash=row["content_hash"],
            source_retrieved_at=datetime.fromisoformat(row["source_retrieved_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
