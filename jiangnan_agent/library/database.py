"""SQLite connection, schema migration, transaction, and backup support."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Iterator
import uuid

CURRENT_SCHEMA_VERSION = 4


class LibraryDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    @property
    def schema_version(self) -> int:
        if not self.path.exists():
            return 0
        connection = self._connect()
        try:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """Yield a read connection and always close it on return."""

        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def initialize(self) -> int:
        migrations = sorted((Path(__file__).parent / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
        migration_map = {int(path.name.split("_", 1)[0]): path for path in migrations}
        connection = self._connect()
        try:
            current = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if current > CURRENT_SCHEMA_VERSION:
                raise ValueError(
                    f"database schema version {current} is newer than supported {CURRENT_SCHEMA_VERSION}"
                )
            for version in range(current + 1, CURRENT_SCHEMA_VERSION + 1):
                migration_path = migration_map.get(version)
                if migration_path is None:
                    raise ValueError(f"missing SQLite migration {version:03d}")
                sql = migration_path.read_text(encoding="utf-8")
                connection.execute("BEGIN IMMEDIATE")
                try:
                    for statement in sql.split(";"):
                        statement = statement.strip()
                        if statement:
                            connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                        (version, _utc_now()),
                    )
                    connection.execute(f"PRAGMA user_version = {version}")
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
            self._ensure_library_id(connection)
            connection.commit()
            return int(connection.execute("PRAGMA user_version").fetchone()[0])
        finally:
            connection.close()

    def _ensure_library_id(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT value FROM library_meta WHERE key = 'library_id'").fetchone()
        if row is None:
            connection.execute(
                "INSERT INTO library_meta(key, value) VALUES ('library_id', ?)", (str(uuid.uuid4()),)
            )

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError("library database is not initialized at the supported schema version")
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get_meta(self, key: str) -> str | None:
        if not self.path.exists():
            return None
        with self.connection() as connection:
            row = connection.execute("SELECT value FROM library_meta WHERE key = ?", (key,)).fetchone()
            return None if row is None else str(row["value"])

    def backup_to(self, destination: str | Path) -> Path:
        target = Path(destination)
        if not self.path.is_file():
            raise ValueError(f"library database does not exist: {self.path}")
        if target.resolve() == self.path.resolve():
            raise ValueError("backup destination must differ from the source database")
        if target.exists():
            raise FileExistsError(f"backup destination already exists: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        source = self._connect()
        backup = sqlite3.connect(target)
        try:
            source.backup(backup)
        except BaseException:
            backup.close()
            source.close()
            target.unlink(missing_ok=True)
            raise
        backup.close()
        source.close()
        return target


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
