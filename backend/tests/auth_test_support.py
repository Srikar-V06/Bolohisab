from pathlib import Path

from fastapi.testclient import TestClient

from app.auth_store import create_account, hash_password
from app.database import DEFAULT_SHOP_ID, database_transaction


TEST_REVIEWER = "Test shopkeeper"
TEST_PHONE = "+919000000090"
TEST_PASSWORD = " test passphrase for the existing shop "


def authenticate_existing_shop(client: TestClient, path: Path) -> None:
    with database_transaction(path, write=True) as db:
        if db.execute("SELECT 1 FROM users WHERE normalized_phone_number = ?", (TEST_PHONE,)).fetchone() is None:
            create_account(db, TEST_REVIEWER, TEST_PHONE, hash_password(TEST_PASSWORD), "SHOPKEEPER", DEFAULT_SHOP_ID)
    login = client.post("/api/auth/login", json={"phone_number": TEST_PHONE, "password": TEST_PASSWORD})
    assert login.status_code == 200, login.text
    client.headers["X-CSRF-Token"] = client.get("/api/auth/csrf").json()["csrf_token"]
