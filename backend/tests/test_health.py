import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.main import create_app


class HealthTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database_path = Path(directory.name) / "data" / "bolohisaab.sqlite3"

    def test_health_creates_and_checks_database(self) -> None:
        with TestClient(create_app(self.database_path)) as client:
            response = client.get("/api/health")

        self.assertTrue(self.database_path.is_file())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": "connected"})

    def test_health_returns_unavailable_if_database_disappears(self) -> None:
        with TestClient(create_app(self.database_path)) as client:
            self.database_path.unlink()
            response = client.get("/api/health")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(self.database_path.exists())

    def test_startup_preserves_existing_data(self) -> None:
        with TestClient(create_app(self.database_path)):
            with closing(sqlite3.connect(self.database_path)) as connection:
                with connection:
                    connection.execute("CREATE TABLE test_entries (amount INTEGER)")
                    connection.execute("INSERT INTO test_entries VALUES (350)")

        with TestClient(create_app(self.database_path)):
            with closing(sqlite3.connect(self.database_path)) as connection:
                row = connection.execute("SELECT amount FROM test_entries").fetchone()

        self.assertEqual(row, (350,))
