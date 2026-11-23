"""Validate and atomically restore a SQLite database snapshot."""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


REQUIRED_TABLES = {"plans", "sync_runs"}


def restore_database(
    backup_path: Path | str,
    database_path: Path | str,
    *,
    owner: tuple[int, int] | None = None,
) -> None:
    source_path = Path(backup_path)
    target_path = Path(database_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = target_path.with_name(f".{target_path.name}.restore")
    temporary_path.unlink(missing_ok=True)

    source = sqlite3.connect(source_path)
    source.execute("PRAGMA query_only = ON")
    target: sqlite3.Connection | None = None
    try:
        tables = {
            row[0]
            for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if not REQUIRED_TABLES.issubset(tables):
            raise ValueError("Backup is missing required DSB tables")

        target = sqlite3.connect(temporary_path)
        source.backup(target)
        integrity = target.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise ValueError(f"Backup integrity check failed: {integrity!r}")
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise
    finally:
        if target is not None:
            target.close()
        source.close()

    for suffix in ("-wal", "-shm"):
        Path(f"{target_path}{suffix}").unlink(missing_ok=True)
    if owner is not None:
        os.chown(temporary_path, *owner)
    os.replace(temporary_path, target_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("database", type=Path)
    args = parser.parse_args()
    restore_database(args.backup, args.database, owner=(10001, 10001))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
