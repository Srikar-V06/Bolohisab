import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from fastapi.testclient import TestClient

from app.database import DEFAULT_SHOP_ID, connect_database, database_transaction
from app.ledger import LedgerEntryDraft, ledger_session
from app.main import create_app
from app.seed_demo import seed_stitch_preview


class ConfirmationReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "receipts.sqlite3"
        self.client = self.enterContext(TestClient(create_app(self.path)))
        with ledger_session(self.path, write=True) as ledger:
            self.customer = ledger.create_customer(DEFAULT_SHOP_ID, "Ramesh")
            self.initial = ledger.create_ledger_entry(
                DEFAULT_SHOP_ID, "opening", LedgerEntryDraft(self.customer.id, "CREDIT", 100_000),
            )

    def reviewed_payload(self) -> dict:
        transcript = " Ramesh ke khate mein saadhe chaar sau likh do aur usne do sau cash diya hai. "
        preview = self.client.post("/api/voice/parse", json={"original_transcript": transcript}).json()
        self.assertEqual(preview["original_transcript"], transcript)
        balance, = preview["balances"]
        self.assertEqual(
            [balance[key] for key in ("credit_paise", "payment_paise", "previous_balance_paise", "updated_balance_paise")],
            [45_000, 20_000, 100_000, 125_000],
        )
        return {
            "batch_id": str(uuid4()),
            "original_transcript": transcript,
            "actions": [
                {**{key: action[key] for key in ("intent", "amount_paise", "payment_method")},
                 "customer_id": action["customer"]["id"]}
                for action in preview["actions"]
            ],
            "previous_balances": {str(self.customer.id): balance["previous_balance_paise"]},
        }

    def test_parse_is_read_only_then_confirm_saves_once(self) -> None:
        payload = self.reviewed_payload()
        self.assertEqual(len(self.client.get("/api/receipts").json()), 1)
        saved = self.client.post("/api/voice/confirm", json=payload)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["original_transcript"], payload["original_transcript"])
        self.assertEqual(saved.json()["entries"][1]["payment_method"], "CASH")
        self.assertEqual(self.client.post("/api/voice/confirm", json=payload).json(), saved.json())
        self.assertEqual(self.client.get(f"/api/customers/{self.customer.id}").json()["balance_paise"], 125_000)
        items = self.client.get("/api/receipts").json()
        self.assertEqual([item["balance_after_paise"] for item in items], [125_000, 145_000, 100_000])
        payload["actions"][0]["amount_paise"] = 45_001
        self.assertEqual(self.client.post("/api/voice/confirm", json=payload).json()["detail"], "BATCH_CONFLICT")

    def test_changed_input_or_balance_requires_new_review(self) -> None:
        payload = self.reviewed_payload()
        changed = {**payload, "actions": [{**payload["actions"][0], "amount_paise": 1}, payload["actions"][1]]}
        self.assertEqual(self.client.post("/api/voice/confirm", json=changed).json()["detail"], "STALE_REVIEW")
        with ledger_session(self.path, write=True) as ledger:
            ledger.create_ledger_entry(DEFAULT_SHOP_ID, "new", LedgerEntryDraft(self.customer.id, "CREDIT", 100))
        self.assertEqual(self.client.post("/api/voice/confirm", json=payload).json()["detail"], "STALE_REVIEW")
        changed = {**payload, "actions": [dict(payload["actions"][0], amount_paise=1.5)]}
        self.assertEqual(self.client.post("/api/voice/confirm", json=changed).status_code, 422)
        self.assertEqual(len(self.client.get("/api/receipts").json()), 2)

    def test_receipt_generation_share_link_and_sent_status(self) -> None:
        endpoint = f"/api/receipts/{self.initial.id}"
        self.assertEqual(self.client.post("/api/receipts/99999", json={"language": "hi-IN"}).status_code, 404)
        self.assertEqual(self.client.post(endpoint + "/sent").status_code, 404)
        issued = self.client.post(endpoint, json={"language": "hi-IN"})
        self.assertEqual(issued.status_code, 200, issued.text)
        info = issued.json()
        self.assertIsNone(info["sent_at"])
        self.assertEqual(info["balance_after_paise"], 100_000)
        self.assertEqual(self.client.post(endpoint, json={"language": "en-IN"}).json(), info)
        url = "/api/receipts/share/" + info["share_token"]
        hindi = self.client.get(url)
        self.assertEqual(hindi.status_code, 200)
        self.assertIn("रसीद", hindi.text)
        self.assertIn("Ramesh", hindi.text)
        self.assertIn("₹1000", hindi.text)
        self.assertEqual(hindi.headers["cache-control"], "no-store")
        self.assertIn("Balance after transaction", self.client.get(url, params={"language": "en-IN"}).text)
        self.assertEqual(self.client.get("/api/receipts/share/" + "x" * 43).status_code, 404)
        sent = self.client.post(endpoint + "/sent").json()
        self.assertIsNotNone(sent["sent_at"])
        self.assertEqual(sent, self.client.post(endpoint + "/sent").json())

    def test_stitch_seed_uses_real_balances_and_three_awaiting_receipts(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "demo.sqlite3"
            self.assertTrue(seed_stitch_preview(path))
            self.assertFalse(seed_stitch_preview(path))
            with TestClient(create_app(path)) as client:
                customers = client.get("/api/customers").json()
                self.assertEqual({row["name"]: row["balance_paise"] for row in customers},
                                 {"Ramesh Kumar": 125_000, "Sunita Devi": 240_000, "Suresh": 85_000, "Mohan": 0})
                awaiting = [row["customer_name"] for row in client.get("/api/receipts").json() if not row["sent_at"]]
                self.assertEqual(awaiting, ["Ramesh Kumar", "Sunita Devi", "Suresh"])

    def test_v1_receipt_survives_migration(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "v1.sqlite3"
            connection = connect_database(path, create=True)
            try:
                schema = Path(__file__).resolve().parents[1] / "app" / "schema.sql"
                connection.executescript(schema.read_text(encoding="utf-8"))
                connection.execute("PRAGMA user_version = 1")
                connection.execute("INSERT INTO customers (id, shop_id, name) VALUES (1, 1, 'Sita')")
                connection.execute("INSERT INTO transaction_batches (shop_id, id) VALUES (1, 'prior')")
                connection.execute(
                    "INSERT INTO ledger_entries (id, shop_id, batch_id, customer_id, type, amount_paise) "
                    "VALUES (1, 1, 'prior', 1, 'CREDIT', 100)",
                )
                connection.execute("INSERT INTO receipts (shop_id, customer_id, ledger_entry_id) VALUES (1, 1, 1)")
            finally:
                connection.close()
            with TestClient(create_app(path)) as client:
                issued_before, = client.get("/api/receipts").json()
                self.assertIsNotNone(issued_before["issued_at"])
                self.assertIsNone(issued_before["share_token"])
                issued_after = client.post("/api/receipts/1", json={"language": "en-IN"}).json()
                self.assertEqual(issued_after["issued_at"], issued_before["issued_at"])
                self.assertEqual(issued_after["language"], "en-IN")
                self.assertTrue(issued_after["share_token"])
            with database_transaction(path) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
