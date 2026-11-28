import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from fastapi.testclient import TestClient

from app.auth_store import create_account, digest, hash_password
from app.database import database_transaction, initialize_database
from app.ledger import Ledger, LedgerEntryDraft
from app.main import create_app


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.path = Path(self.enterContext(TemporaryDirectory())) / "portal.db"
        self.app = create_app(self.path)
        initialize_database(self.path)
        self.now = int(datetime.now(UTC).timestamp())
        self.app.state.auth_clock = lambda: self.now
        self.password = "portal test passphrase"
        encoded = hash_password(self.password)
        with database_transaction(self.path, write=True) as db:
            db.execute("INSERT INTO shops(id,name) VALUES(2,'Second shop')")
            for i, shop in enumerate((1, 2, None, None), 1):
                create_account(db, f"User {i}", f"+91987654321{i}", encoded,
                               "SHOPKEEPER" if shop else "CUSTOMER", shop)
        self.seller, self.other_shop, self.buyer, self.other_buyer = [self.login(i) for i in range(1, 5)]
        self.customer = self.record(self.seller, "Ramesh", phone_number="98765-43213")

    def login(self, i):
        client = self.enterContext(TestClient(self.app, base_url=self.app.state.auth_config.origins[0]))
        response = client.post("/api/auth/login", json={"phone_number": f"987654321{i}", "password": self.password})
        self.assertEqual(response.status_code, 200, response.text)
        client.headers["X-CSRF-Token"] = client.get("/api/auth/csrf").json()["csrf_token"]
        return client

    def record(self, seller, name, **extra):
        response = seller.post("/api/customers", json={"name": name, **extra})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    def route(self, customer=None):
        return f"/api/shopkeeper/customers/{customer or self.customer}"

    def invite(self, seller=None, customer=None):
        response = (seller or self.seller).post(self.route(customer) + "/invite")
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["invitation_url"]

    def link(self, seller=None, customer=None):
        response = self.buyer.post(self.invite(seller, customer) + "/claim")
        self.assertEqual(response.status_code, 200, response.text)

    def entry(self, shop, customer, amount, kind="CREDIT"):
        with database_transaction(self.path, write=True) as db:
            batch = str(db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0])
            return Ledger(db).create_ledger_entry(shop, batch, LedgerEntryDraft(customer, kind, amount)).id

    def issue(self, seller, entry):
        response = seller.post(f"/api/receipts/{entry}", json={"language": "en-IN"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["receipt_id"]

    def test_invite_scope_token_expiry_and_revocation(self):
        url = self.invite()
        self.assertEqual(self.buyer.get(url).json()["customer_name"], "Ramesh")
        self.assertEqual(self.other_buyer.get(url).status_code, 403)
        self.assertEqual(self.other_buyer.post(url + "/claim").status_code, 403)
        self.assertEqual(self.seller.post(url + "/claim").status_code, 403)
        self.assertEqual(self.buyer.get(url + "x").status_code, 404)
        self.assertEqual(self.seller.post(self.route() + "/invite").status_code, 409)
        for suffix, method in (("/link-status", "get"), ("/invite", "post"), ("/invite", "delete"), ("/link", "delete")):
            self.assertEqual(getattr(self.other_shop, method)(self.route() + suffix).status_code, 404)
        with database_transaction(self.path) as db:
            invitation = db.execute("SELECT * FROM customer_invitations").fetchone()
            self.assertEqual(invitation["expires_at"], self.now + 7*86400)
            self.assertEqual(invitation["token_hash"], digest(url.split("/")[-1]))
        self.assertEqual(self.seller.delete(self.route() + "/invite").json()["invitation_status"], "REVOKED")
        self.assertEqual(self.buyer.post(url + "/claim").status_code, 410)
        url = self.invite()
        with database_transaction(self.path, write=True) as db:
            db.execute("UPDATE customer_invitations SET expires_at=? WHERE status='PENDING'", (self.now,))
        self.assertEqual(self.buyer.post(url + "/claim").status_code, 410)
        self.assertEqual(self.seller.get(self.route() + "/link-status").json()["invitation_status"], "EXPIRED")
        self.link()

    def test_atomic_claim_and_duplicate_store(self):
        url = self.invite() + "/claim"
        another_session = self.login(3)
        barrier = Barrier(2)

        def claim(client):
            barrier.wait(timeout=10)
            return client.post(url).status_code

        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(claim, (another_session, self.buyer))), [200, 409])
        self.assertEqual(self.buyer.post(url).status_code, 409)
        self.assertEqual(self.seller.post(self.route() + "/invite").status_code, 409)
        duplicate = self.invite(customer=self.record(self.seller, "Another customer"))
        self.assertEqual(self.buyer.post(duplicate + "/claim").status_code, 409)
        self.assertTrue(self.seller.get(self.route() + "/link-status").json()["linked"])

    def test_role_session_and_csrf_guards(self):
        guest = self.enterContext(TestClient(self.app))
        for path in ("/api/customer/stores", "/api/customer/stores/1", "/api/customer/stores/1/ledger",
                     "/api/customer/stores/1/receipts", "/api/customer/notifications",
                     "/api/customer/notifications/unread-count"):
            self.assertEqual(guest.get(path).status_code, 401)
            self.assertEqual(self.seller.get(path).status_code, 403)
        body = {"transcript":"Who owes me the most?", "language":"en-IN", "store_id":1}
        self.assertEqual(self.buyer.post("/api/voice/query", json=body).status_code, 403)
        self.assertEqual(guest.post("/api/voice/query", json=body).status_code, 401)
        url = self.invite()
        self.assertEqual(self.buyer.post(url + "/claim", headers={"X-CSRF-Token":"bad"}).status_code, 403)
        self.assertFalse(self.seller.get(self.route() + "/link-status").json()["linked"])

    def test_independent_stores_pagination_and_receipts(self):
        self.link()
        second = self.record(self.other_shop, "Ramesh")
        self.link(self.other_shop, second)
        hidden = self.record(self.seller, "Private")
        self.issue(self.seller, self.entry(1, hidden, 500))
        ids = [self.entry(1, self.customer, 25) for _ in range(7)]
        expected = self.issue(self.seller, ids[0])
        self.entry(2, second, 80)
        stores = self.buyer.get("/api/customer/stores").json()
        self.assertEqual([s["outstanding_balance_paise"] for s in stores], [175, 80])
        base = "/api/customer/stores/1"
        self.assertEqual(self.buyer.get(base).json(), stores[0])
        self.assertEqual([r["receipt_id"] for r in self.buyer.get(base+"/receipts").json()], [expected])
        page = self.buyer.get(base+"/ledger").json()
        self.assertEqual([i["id"] for i in page["items"]], ids[::-1][:5])
        self.entry(1, self.customer, 17)
        last = self.buyer.get(base+"/ledger", params={"cursor": page["next_cursor"]}).json()
        self.assertEqual([i["id"] for i in last["items"]], ids[::-1][5:])
        self.assertFalse(last["has_more"])
        self.assertEqual(self.buyer.get("/api/customer/stores/2/ledger", params={"cursor":page["next_cursor"]}).status_code, 422)
        self.assertFalse(self.seller.delete(self.route()+"/link").json()["linked"])
        for client in (self.other_buyer, self.buyer):
            for suffix in ("", "/ledger", "/receipts"):
                self.assertEqual(client.get(base+suffix).status_code, 404)
        self.assertEqual(self.buyer.get(f"/api/customers/{self.customer}/ledger").status_code, 404)

    def test_receipt_notifications_visibility_pagination_and_failure(self):
        feed = "/api/customer/notifications"
        self.issue(self.seller, self.entry(1, self.customer, 50))
        self.link()
        entry = self.entry(1, self.customer, 300)
        receipt = self.issue(self.seller, entry)
        self.issue(self.seller, entry)
        self.assertEqual(self.seller.post(f"/api/receipts/{entry}/sent").status_code, 200)
        second = self.issue(self.seller, self.entry(1, self.customer, 100))
        self.assertEqual(self.buyer.get(feed+"/unread-count").json()["unread_count"], 2)
        page = self.buyer.get(feed, params={"limit":1}).json()
        self.assertEqual(page["items"][0]["receipt_id"], second)
        older = self.buyer.get(feed, params={"cursor":page["next_cursor"]}).json()["items"][0]
        self.assertEqual((older["receipt_id"],older["amount_paise"],older["store_id"]), (receipt,300,1))
        read = feed + f"/{older['id']}/read"
        self.assertEqual(self.other_buyer.post(read).status_code, 404)
        self.assertEqual(self.other_buyer.post(feed+"/read-all").json()["updated_count"], 0)
        stamp = self.buyer.post(read).json()["read_at"]
        self.assertEqual(self.buyer.post(read).json()["read_at"], stamp)
        self.assertEqual(self.buyer.get("/api/customer/stores/1").json()["unread_notification_count"], 1)
        self.assertEqual(self.buyer.post(feed+"/read-all").json()["updated_count"], 1)
        self.assertEqual(self.buyer.get(feed+"/unread-count").json()["unread_count"], 0)
        with database_transaction(self.path, write=True) as db:
            db.execute("CREATE TRIGGER fail_notice BEFORE INSERT ON notifications BEGIN SELECT RAISE(ABORT,'test'); END")
        with self.assertLogs("app.receipt_store", level="ERROR"):
            self.issue(self.seller, self.entry(1, self.customer, 4))
        self.seller.delete(self.route()+"/link")
        self.assertEqual(self.buyer.get(feed).json()["items"], [])
        self.assertEqual(self.buyer.post(read).status_code, 404)

    def test_report_languages_boundaries_and_read_only(self):
        self.now = int(datetime(2026, 1, 1, 18, 30, tzinfo=UTC).timestamp())
        # Log in again using the report clock to avoid a session expiry.
        client = self.login(1)
        def report(text, lang="en-IN", shop=1):
            return client.post("/api/voice/query", json={"transcript":text,"language":lang,"store_id":shop})

        self.assertEqual(report("Who owes me the most?").json()["result"]["customers"], [])
        with database_transaction(self.path, write=True) as db:
            db.execute("INSERT INTO transaction_batches(shop_id,id) VALUES(1,'boundary')")
            for stamp, kind, amount in (
                ("2026-01-01T18:29:59.999Z","CREDIT",300),
                ("2026-01-01T18:30:00.000Z","CREDIT",100),
                ("2026-01-02T18:29:59.999Z","PAYMENT",50),
                ("2026-01-02T18:30:00.000Z","CREDIT",200),
            ):
                db.execute("INSERT INTO ledger_entries(shop_id,batch_id,customer_id,type,amount_paise,created_at) "
                           "VALUES(1,'boundary',?,?,?,?)", (self.customer,kind,amount,stamp))

        cases = [
            ("COLLECTIONS_QUERY","amount_paise",50,"How much money came in today?","Aaj kitne paise aaye?","आज कितने पैसे आए?"),
            ("CREDIT_QUERY","amount_paise",100,"How much credit did I give today?","Aaj kitna udhar diya?","आज कितना उधार दिया?"),
            ("CUSTOMER_BALANCE_QUERY","balance_paise",550,"How much does Ramesh owe?","Ramesh ka kitna udhar baaki hai?","रमेश का कितना उधार बाकी है?"),
            ("TOP_OUTSTANDING_QUERY","balance_paise",550,"Who owes me the most?","Sabse zyada udhar kiske paas hai?","सबसे ज्यादा उधार किसके पास है?"),
            ("TRANSACTION_COUNT_QUERY","count",2,"How many transactions happened today?","Aaj kitne transactions hue?","आज कितने लेनदेन हुए?"),
        ]
        for intent, field, expected, *examples in cases:
            for lang, example in zip(("en-IN","hi-Latn-IN","hi-IN"), examples):
                with self.subTest(example=example):
                    response = report(example, lang)
                    self.assertEqual(response.status_code, 200, response.text)
                    data = response.json()
                    self.assertEqual((data["detected_language"],data["intent"],data["result"][field]), (lang,intent,expected))
                    self.assertEqual(data["localized_text"],data["speech_text"])
        self.assertEqual(report("How much does Nobody owe?").json()["detail"]["code"], "CUSTOMER_NOT_FOUND")
        self.record(client, "Ramesh Sharma")
        self.assertEqual(len(report("How much does Ramesh owe?").json()["detail"]["candidates"]), 2)
        self.assertEqual(report("Who owes me the most?", shop=2).status_code, 404)
        self.assertEqual(report("record credit 100 for Ramesh").status_code, 422)
        with database_transaction(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM ledger_entries").fetchone()[0], 4)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
