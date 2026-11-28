import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import COOKIE
from app.auth_store import (
    ATTEMPT_WINDOW, SESSION_IDLE_TIMEOUT, SESSION_LIFETIME, digest, hash_password, verify_password,
)
from app.database import database_transaction
from app.ledger import LedgerEntryDraft, ledger_session
from app.main import create_app


PHONE = "+919876543210"
OTHER = "+919876543211"
BUYER = "+919876543212"
PASSWORD = "  a real passphrase " + "a" * 128 + "  "
ORIGIN = "http://localhost:3000"


class AuthenticationTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "auth.sqlite3"
        self.enterContext(patch.dict("os.environ", {"BOLO_ENV": "development", "BOLO_ALLOWED_ORIGINS": ORIGIN}))
        self.app = create_app(self.path)
        self.now = 18_000
        self.app.state.auth_clock = lambda: self.now
        self.client = self.enterContext(TestClient(self.app))

    def register(self, phone=PHONE, role="shopkeeper", **fields):
        body = {"full_name": "Test account", "phone_number": phone, "password": PASSWORD}
        if role == "shopkeeper":
            body.update(shop_name="Test shop", shop_address="Pune")
        return self.client.post(f"/api/auth/register/{role}", json={**body, **fields})

    def login(self, phone=PHONE, client=None, **fields):
        return (client or self.client).post("/api/auth/login", json={
            "phone_number": phone, "password": PASSWORD, **fields,
        })

    @staticmethod
    def headers(client):
        return {"X-CSRF-Token": client.get("/api/auth/csrf").json()["csrf_token"]}

    def test_role_specific_registrations_normalize_and_duplicates_are_atomic(self) -> None:
        seller = self.register("98765-43210")
        self.assertEqual(seller.status_code, 201, seller.text)
        record = seller.json()
        self.assertEqual(record["role"], "SHOPKEEPER")
        self.assertEqual(record["normalized_phone_number"], PHONE)
        self.assertTrue(record["is_active"])
        self.assertNotIn("password_hash", record)
        self.assertNotIn(COOKIE, seller.cookies)
        customer = self.register(BUYER, "customer")
        self.assertEqual(customer.status_code, 201, customer.text)
        self.assertEqual(customer.json()["role"], "CUSTOMER")
        self.assertIsNone(customer.json()["shop_id"])
        for role in ("shopkeeper", "customer"):
            duplicate = self.register("+91 98765 43210", role)
            self.assertEqual((duplicate.status_code, duplicate.json()), (409, {"detail": "REGISTRATION_FAILED"}))
        with database_transaction(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM shops").fetchone()[0], 2)
            shop = db.execute("SELECT name, address FROM shops WHERE id = ?", (record["shop_id"],)).fetchone()
            self.assertEqual(tuple(shop), ("Test shop", "Pune"))
            stored = db.execute("SELECT password_hash FROM users WHERE id = ?", (record["id"],)).fetchone()[0]
        self.assertTrue(stored.startswith("$argon2id$"))
        self.assertTrue(verify_password(stored, PASSWORD))
        self.assertFalse(verify_password(stored, PASSWORD.strip()))
        self.assertFalse(verify_password("broken-hash", PASSWORD))
        self.assertNotEqual(hash_password(PASSWORD), stored)

    def test_errors_are_generic_and_passwords_do_not_echo(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        for response in (
            self.login(password="not the password"), self.login(OTHER), self.login(role="CUSTOMER"),
        ):
            self.assertEqual((response.status_code, response.json()), (401, {"detail": "INVALID_CREDENTIALS"}))
        short = self.register(BUYER, "customer", password="veryshort")
        self.assertEqual((short.status_code, short.json()), (422, {"detail": "INVALID_AUTH_INPUT"}))
        extra = self.login(role="SHOPKEEPER", unexpected=PASSWORD)
        self.assertEqual(extra.json(), {"detail": "INVALID_AUTH_INPUT"})
        self.assertNotIn(PASSWORD, extra.text)

    def test_session_restoration_rotation_csrf_and_logout(self) -> None:
        account = self.register().json()
        login = self.login(role="SHOPKEEPER")
        self.assertEqual(login.status_code, 200, login.text)
        first = self.client.cookies[COOKIE]
        cookie = login.headers["Set-Cookie"]
        for attr in ("HttpOnly", "SameSite=lax", "Path=/", f"Max-Age={SESSION_LIFETIME}"):
            self.assertIn(attr, cookie)
        self.assertNotIn("Secure", cookie)
        self.assertNotIn("Domain=", cookie)
        self.assertNotIn(first, login.text)
        csrf = self.headers(self.client)
        with database_transaction(self.path) as db:
            stored = db.execute("SELECT token_hash, csrf_hash, last_activity_at FROM auth_sessions").fetchone()
            self.assertEqual(tuple(stored), (digest(first), digest(csrf["X-CSRF-Token"]), self.now))
        restored = TestClient(self.app, cookies={COOKIE: first})
        self.now += 30
        self.assertEqual(restored.get("/api/auth/me").json(), account)
        self.assertEqual(self.headers(restored), csrf)
        with database_transaction(self.path) as db:
            self.assertEqual(db.execute("SELECT last_activity_at FROM auth_sessions").fetchone()[0], self.now)
        self.assertEqual(self.client.post("/api/customers", json={"name": "Customer"}).json()["detail"], "CSRF_INVALID")
        self.assertEqual(self.client.post("/api/auth/logout", headers={"X-CSRF-Token": "0" * 64}).status_code, 403)
        self.assertEqual(self.login().status_code, 200)
        second = self.client.cookies[COOKIE]
        self.assertNotEqual(first, second)
        self.assertEqual(restored.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/logout", headers=csrf).status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout", headers=self.headers(self.client)).status_code, 204)
        self.assertNotIn(COOKIE, self.client.cookies)
        self.assertEqual(TestClient(self.app, cookies={COOKIE: second}).get("/api/auth/me").status_code, 401)
        with database_transaction(self.path) as db:
            count = db.execute("SELECT count(*) FROM auth_sessions WHERE revoked_at IS NOT NULL").fetchone()[0]
            self.assertEqual(count, 2)

    def test_idle_absolute_and_inactive_sessions(self) -> None:
        account = self.register().json()
        self.assertEqual(self.login().status_code, 200)
        self.now += SESSION_IDLE_TIMEOUT
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        for _ in range(13):
            self.now += SESSION_IDLE_TIMEOUT // 2
            self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self.now += SESSION_IDLE_TIMEOUT // 2
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login().status_code, 200)
        with database_transaction(self.path, write=True) as db:
            db.execute("UPDATE users SET is_active = 0 WHERE id = ?", (account["id"],))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.login().json(), {"detail": "INVALID_CREDENTIALS"})
        with database_transaction(self.path, write=True) as db:
            db.execute("UPDATE users SET is_active = 1 WHERE id = ?", (account["id"],))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_origin_cors_and_secure_production_cookie(self) -> None:
        wrong = "https://untrusted.example"
        self.assertEqual(self.register().status_code, 201)
        options = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "X-CSRF-Token"}
        allowed = self.client.options("/api/customers", headers={**options, "Origin": ORIGIN})
        self.assertEqual(allowed.headers["Access-Control-Allow-Origin"], ORIGIN)
        self.assertEqual(allowed.headers["Access-Control-Allow-Credentials"], "true")
        blocked = self.client.options("/api/customers", headers={**options, "Origin": wrong})
        self.assertEqual(blocked.status_code, 400)
        self.assertNotIn("Access-Control-Allow-Origin", blocked.headers)
        unauthorized = self.client.post("/api/auth/login", headers={"Origin": wrong},
                                        json={"phone_number": PHONE, "password": PASSWORD})
        self.assertEqual(unauthorized.json()["detail"], "ORIGIN_NOT_ALLOWED")
        self.assertEqual(self.login().status_code, 200)
        csrf = self.headers(self.client)
        for origin in (wrong, "null"):
            self.assertEqual(self.client.post("/api/customers", headers={**csrf, "Origin": origin},
                                              json={"name": "Customer"}).status_code, 403)
        self.assertEqual(self.client.post("/api/customers", headers={**csrf, "Origin": ORIGIN},
                                          json={"name": "Customer"}).status_code, 201)
        with patch.dict("os.environ", {"BOLO_ENV": "production", "BOLO_ALLOWED_ORIGINS": "https://shop.example"}):
            with TestClient(create_app(self.path), base_url="https://shop.example") as production:
                self.assertIn("Secure", self.login(client=production).headers["Set-Cookie"])
                self.assertEqual(production.get("/api/auth/me").status_code, 200)

    def test_login_limits_phone_and_ip_then_reset(self) -> None:
        for _ in range(8):
            self.assertEqual(self.login(password="wrong").status_code, 401)
        client = TestClient(self.app, client=("192.0.2.12", 1234))
        blocked_phone = self.login("98765-43210", client)
        self.assertEqual(blocked_phone.status_code, 429)
        self.assertEqual(blocked_phone.headers["Retry-After"], str(ATTEMPT_WINDOW))
        for index in range(22):
            self.assertEqual(self.login(f"+919800001{index:03d}").status_code, 401)
        self.assertEqual(self.login(OTHER).status_code, 429)
        self.now += ATTEMPT_WINDOW
        self.assertEqual(self.register().status_code, 201)
        self.assertEqual(self.login().status_code, 200)

    def test_registration_throttle(self) -> None:
        self.assertEqual(self.register().status_code, 201)
        for _ in range(3):
            self.assertEqual(self.register().status_code, 409)
        self.assertEqual(self.register().status_code, 429)
        self.now += ATTEMPT_WINDOW
        self.assertEqual(self.register().status_code, 409)

    def test_customer_links_and_shop_isolation_on_existing_routes(self) -> None:
        self.assertEqual(self.client.get("/api/receipts").status_code, 401)
        self.assertEqual(self.client.post("/api/voice/parse", json={"transcript": "credit 400"}).status_code, 401)
        first = self.register().json()
        second = self.register(OTHER).json()
        buyer = self.register(BUYER, "customer").json()
        with ledger_session(self.path, write=True) as ledger:
            a, b = first["shop_id"], second["shop_id"]
            one = ledger.create_customer(a, "First record")
            unrelated = ledger.create_customer(a, "Other record")
            two = ledger.create_customer(b, "Second record")
            ledger.create_transaction_batch(
                a, "first", [LedgerEntryDraft(one.id, "CREDIT", 1000), LedgerEntryDraft(unrelated.id, "CREDIT", 8400)],
                original_transcript="First record and Other record",
            )
            second_entry = ledger.create_ledger_entry(b, "second", LedgerEntryDraft(two.id, "CREDIT", 3000))
        self.assertEqual(self.login().status_code, 200)
        csrf = self.headers(self.client)
        self.assertEqual({x["id"] for x in self.client.get("/api/customers").json()}, {one.id, unrelated.id})
        for url in (f"/api/customers/{two.id}", f"/api/customers/{two.id}/ledger?limit=5"):
            self.assertEqual(self.client.get(url).status_code, 404)
        for suffix, payload in (("", {"language": "en-IN"}), ("/sent", {}),
                                ("/dispute/review", {"decision": "APPROVED"})):
            other_url = f"/api/receipts/{second_entry.id}{suffix}"
            self.assertEqual(self.client.post(other_url, json=payload, headers=csrf).status_code, 404)
        entry = self.client.get(f"/api/customers/{one.id}/ledger").json()[0]
        issued = self.client.post(f"/api/receipts/{entry['id']}", headers=csrf, json={"language": "en-IN"}).json()
        token = issued["share_token"]
        customer = TestClient(self.app)
        self.assertEqual(self.login(BUYER, customer).status_code, 200)
        self.assertEqual(customer.get("/api/customers").json(), [])
        self.assertEqual(customer.get(f"/api/customers/{one.id}").status_code, 404)
        with database_transaction(self.path, write=True) as db:
            db.executemany("INSERT INTO customer_account_links (customer_id, user_id) VALUES (?, ?)",
                           [(one.id, buyer["id"]), (two.id, buyer["id"])])
        self.assertEqual([row["balance_paise"] for row in customer.get("/api/customers").json()], [1000, 3000])
        history = customer.get(f"/api/customers/{one.id}/ledger?limit=5").json()["items"]
        self.assertIsNone(history[0]["original_transcript"])
        self.assertEqual(customer.get(f"/api/customers/{unrelated.id}/ledger").status_code, 404)
        receipts = customer.get("/api/receipts").json()
        self.assertEqual([receipt["receipt_id"] for receipt in receipts], [issued["receipt_id"]])
        self.assertIsNone(receipts[0]["share_token"])
        for url, payload in (
            ("/api/customers", {"name": "Blocked"}),
            ("/api/voice/parse", {"transcript": "credit 400"}),
            (f"/api/receipts/{entry['id']}/dispute/review", {"decision": "APPROVED"}),
        ):
            self.assertEqual(customer.post(url, json=payload, headers=self.headers(customer)).status_code, 403)
        self.assertEqual(TestClient(self.app).get(f"/api/receipts/share/{token}").status_code, 200)
