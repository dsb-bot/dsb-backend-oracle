"""Validate and optionally import a date-named HTML plan archive into SQLite."""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Mapping

from dsb_bot.models import PlanCandidate, PlanSource
from dsb_bot.parser import PlanParseError, parse_student_document
from dsb_bot.repository import ScheduleRepository


CHARSET_PATTERN = re.compile(rb"charset\s*=\s*['\"]?([^;'\"\s>]+)", re.IGNORECASE)
logger = logging.getLogger(__name__)


class ArchiveValidationError(ValueError):
    pass


def load_archive(
    archive_directory: Path,
    source: PlanSource | None,
    *,
    source_by_date: Mapping[date, PlanSource] | None = None,
    retrieved_at: datetime | None = None,
) -> list[PlanCandidate]:
    if (source is None) == (source_by_date is None):
        raise ArchiveValidationError("Choose exactly one source or per-date source manifest")
    files = sorted(archive_directory.glob("*.html"))
    if not files:
        raise ArchiveValidationError(f"No .html plans found in {archive_directory}")

    timestamp = retrieved_at or datetime.now(timezone.utc)
    candidates: list[PlanCandidate] = []
    errors: list[str] = []
    seen_dates: set[date] = set()

    for path in files:
        try:
            filename_date = datetime.strptime(path.stem, "%Y-%m-%d").date()
            body = path.read_bytes()
            if not body.strip():
                logger.warning("Skipping empty archive placeholder %s", path.name)
                continue
            match = CHARSET_PATTERN.search(body[:4096])
            charset = match.group(1).decode("ascii") if match else None
            content_type = (
                f"text/html; charset={charset}" if charset else "text/html"
            )
            candidate = parse_student_document(body, content_type, timestamp)
            if candidate.date != filename_date:
                raise ArchiveValidationError(
                    f"filename date {filename_date} differs from document date {candidate.date}"
                )
            if candidate.date in seen_dates:
                raise ArchiveValidationError(f"duplicate plan date {candidate.date}")
            seen_dates.add(candidate.date)
            provenance = source_by_date.get(candidate.date) if source_by_date is not None else source
            if provenance is None:
                raise ArchiveValidationError(
                    f"manifest has no provenance for {candidate.date}"
                )
            candidates.append(replace(candidate, source=provenance))
        except (OSError, ValueError, PlanParseError) as exc:
            errors.append(f"{path.name}: {exc}")

    if errors:
        details = "\n".join(errors)
        raise ArchiveValidationError(
            f"Archive validation failed; nothing was imported:\n{details}"
        )
    if source_by_date is not None:
        archive_dates = {candidate.date for candidate in candidates}
        extra_dates = set(source_by_date) - archive_dates
        if extra_dates:
            raise ArchiveValidationError(
                f"Manifest contains dates absent from the archive: {sorted(extra_dates)!r}"
            )
    return candidates


def load_manifest(manifest_path: Path) -> dict[date, PlanSource]:
    source_by_date: dict[date, PlanSource] = {}
    try:
        with manifest_path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != ["date", "source"]:
                raise ArchiveValidationError("Manifest header must be exactly: date,source")
            for row in reader:
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"] or ""):
                        raise ValueError("date must use YYYY-MM-DD")
                    target_date = date.fromisoformat(row["date"])
                    provenance = PlanSource(row["source"])
                except (TypeError, ValueError) as exc:
                    raise ArchiveValidationError(
                        f"Invalid manifest row {reader.line_num}: use YYYY-MM-DD and a valid source"
                    ) from exc
                if target_date in source_by_date:
                    raise ArchiveValidationError(
                        f"Duplicate manifest date at row {reader.line_num}: {target_date}"
                    )
                source_by_date[target_date] = provenance
    except OSError as exc:
        raise ArchiveValidationError(f"Could not read manifest {manifest_path}: {exc}") from exc
    return source_by_date


def import_archive(
    archive_directory: Path,
    repository: ScheduleRepository,
    source: PlanSource | None,
    *,
    source_by_date: Mapping[date, PlanSource] | None = None,
    apply: bool = False,
) -> tuple[int, int]:
    candidates = load_archive(
        archive_directory, source, source_by_date=source_by_date
    )
    if not apply:
        return len(candidates), 0

    imported = 0
    skipped = 0
    for candidate in candidates:
        if repository.save(candidate):
            imported += 1
        else:
            skipped += 1
    return imported, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a date-named HTML plan archive. Import requires --apply and "
            "an explicit provenance choice."
        )
    )
    parser.add_argument("archive", type=Path)
    parser.add_argument("--database", type=Path, required=True)
    provenance = parser.add_mutually_exclusive_group(required=True)
    provenance.add_argument(
        "--source",
        choices=[item.value for item in PlanSource],
        help="Provenance of every imported plan; choose only after verifying the archive.",
    )
    provenance.add_argument(
        "--manifest",
        type=Path,
        help="CSV with exactly two columns (date,source) for mixed-source archives.",
    )
    parser.add_argument("--apply", action="store_true", help="Write validated plans to SQLite.")
    args = parser.parse_args(argv)

    try:
        source = PlanSource(args.source) if args.source else None
        source_by_date = load_manifest(args.manifest) if args.manifest else None
        candidates = load_archive(
            args.archive, source, source_by_date=source_by_date
        )
        if not args.apply:
            print(
                f"Validated {len(candidates)} plans; database unchanged. "
                "Review provenance, then rerun with --apply."
            )
            return 0
        repository = ScheduleRepository(args.database)
        repository.initialize()
        imported = sum(repository.save(candidate) for candidate in candidates)
        print(
            f"Imported {imported} plans; "
            f"{len(candidates) - imported} unchanged or protected by source priority."
        )
        return 0
    except (ArchiveValidationError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
