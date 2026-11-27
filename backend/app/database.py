import sqlite3
from contextlib import closing
from pathlib import Path


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL").fetchone()


def check_database(path: Path) -> None:
    # Read the schema without silently creating a replacement database.
    uri = f"{path.resolve().as_uri()}?mode=rw"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        connection.execute("PRAGMA schema_version").fetchone()
