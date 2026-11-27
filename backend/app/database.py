import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from os import environ
from pathlib import Path


DEFAULT_SHOP_ID = 1
SCHEMA_VERSION = 2


def database_path() -> Path:
    return Path(environ.get("DATABASE_PATH", "data/bolohisaab.sqlite3"))


def connect_database(path: Path, *, create: bool = False) -> sqlite3.Connection:
    mode = "rwc" if create else "rw"
    uri = f"{path.resolve().as_uri()}?mode={mode}"
    connection = sqlite3.connect(uri, uri=True, autocommit=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def database_transaction(path: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    with closing(connect_database(path)) as connection:
        if not write:
            connection.execute("PRAGMA query_only = ON")
        connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        try:
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect_database(path, create=True)) as connection:
        connection.execute("PRAGMA journal_mode = WAL").fetchone()
    with database_transaction(path, write=True) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1, SCHEMA_VERSION):
            raise RuntimeError(f"Unsupported ledger schema version: {version}")
        if version == 0:
            connection.executescript(Path(__file__).with_name("schema.sql").read_text(encoding="utf-8"))
        if version < 2:
            connection.executescript(Path(__file__).with_name("receipts_migration.sql").read_text(encoding="utf-8"))
            connection.execute("PRAGMA user_version = 2")


def check_database(path: Path) -> None:
    # Read the schema without silently creating a replacement database.
    with closing(connect_database(path)) as connection:
        connection.execute("PRAGMA schema_version").fetchone()
