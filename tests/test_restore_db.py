import sqlite3

import pytest

from dsb_bot.restore_db import restore_database


def create_database(path, *, required=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE plans (date TEXT PRIMARY KEY)")
    if required:
        connection.execute("CREATE TABLE sync_runs (id INTEGER PRIMARY KEY)")
    connection.execute("INSERT INTO plans (date) VALUES ('2026-11-06')")
    connection.commit()
    connection.close()


def test_restore_replaces_database_from_validated_snapshot(tmp_path):
    backup = tmp_path / "backup.sqlite3"
    database = tmp_path / "data" / "dsb.sqlite3"
    create_database(backup)
    create_database(database)

    restore_database(backup, database)

    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert connection.execute("SELECT date FROM plans").fetchone() == ("2026-11-06",)
    connection.close()


def test_restore_rejects_non_dsb_database_without_replacing_current(tmp_path):
    backup = tmp_path / "backup.sqlite3"
    database = tmp_path / "current.sqlite3"
    create_database(backup, required=False)
    create_database(database)

    with pytest.raises(ValueError, match="required DSB tables"):
        restore_database(backup, database)

    connection = sqlite3.connect(database)
    assert connection.execute("SELECT date FROM plans").fetchone() == ("2026-11-06",)
    connection.close()
