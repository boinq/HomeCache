import sqlite3
from pathlib import Path

from fastapi import HTTPException

from app.database import engine


def get_sqlite_database_path() -> Path:
    if engine.url.get_backend_name() != "sqlite":
        raise HTTPException(
            status_code=400,
            detail="Database backups are only supported for SQLite databases.",
        )

    database = engine.url.database
    if not database or database == ":memory:":
        raise HTTPException(
            status_code=400,
            detail="Database backups require a file-backed SQLite database.",
        )

    database_path = Path(database).resolve()
    if not database_path.exists():
        raise HTTPException(status_code=404, detail="Database file not found.")

    return database_path


def backup_sqlite_database(source_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(backup_path)

    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def validate_sqlite_backup(backup_path: Path) -> None:
    connection = sqlite3.connect(backup_path)

    try:
        integrity_result = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity_result or integrity_result[0] != "ok":
            raise HTTPException(status_code=400, detail="Backup integrity check failed.")

        table_rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        table_names = {row[0] for row in table_rows}
        required_tables = {"item", "itembatch", "appsetting"}

        if not required_tables.issubset(table_names):
            raise HTTPException(
                status_code=400,
                detail="Backup does not look like a HomeCache database.",
            )
    finally:
        connection.close()
