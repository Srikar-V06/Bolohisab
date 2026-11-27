import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.database import DEFAULT_SHOP_ID
from app.ledger import LedgerEntryDraft, ledger_session
from app.main import create_app


class CustomerApiTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "customers.sqlite3"
        self.client = self.enterContext(TestClient(create_app(self.path)))

    def test_create_list_read_and_retrieve_ledger(self) -> None:
        self.assertEqual(self.client.get("/api/customers").json(), [])
        response = self.client.post("/api/customers", json={"name": "सीता"})
        self.assertEqual(response.status_code, 201)
        customer = response.json()
        customer_id = customer["id"]
        self.assertEqual(customer["name"], "सीता")
        self.assertEqual(customer["balance_paise"], 0)
        self.assertEqual(self.client.get(f"/api/customers/{customer_id}/ledger").json(), [])

        with ledger_session(self.path, write=True) as ledger:
            ledger.create_transaction_batch(DEFAULT_SHOP_ID, "api-sample-batch", [
                LedgerEntryDraft(customer_id, "CREDIT", 45_000),
                LedgerEntryDraft(customer_id, "PAYMENT", 20_000),
            ], original_transcript="सीता ने ₹200 दिए।", detected_language="hi-IN")

        customer["balance_paise"] = 25_000
        history = self.client.get(f"/api/customers/{customer_id}/ledger").json()
        customer["last_transaction_at"] = history[-1]["created_at"]
        self.assertEqual(self.client.get("/api/customers").json(), [customer])
        self.assertEqual(self.client.get(f"/api/customers/{customer_id}").json(), customer)
        response = self.client.get(f"/api/customers/{customer_id}/ledger")
        self.assertEqual(response.status_code, 200)
        entries = response.json()
        self.assertEqual([entry["type"] for entry in entries], ["CREDIT", "PAYMENT"])
        self.assertEqual([entry["balance_effect_paise"] for entry in entries], [45_000, -20_000])
        self.assertEqual(entries[1]["batch_id"], "api-sample-batch")
        self.assertEqual(entries[1]["original_transcript"], "सीता ने ₹200 दिए।")
        self.assertEqual(entries[1]["detected_language"], "hi-IN")

    def test_invalid_body_bad_path_and_missing_customer(self) -> None:
        for body in ({}, {"name": "   "}, {"name": 123}, {"name": "x" * 121}, {"name": "Ramesh", "shop_id": 2}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/api/customers", json=body).status_code, 422)
        for path in ("/api/customers/999", "/api/customers/999/ledger"):
            self.assertEqual(self.client.get(path).status_code, 404)
        for path in ("/api/customers/not-an-id", "/api/customers/0", "/api/customers/9223372036854775808/ledger"):
            self.assertEqual(self.client.get(path).status_code, 422)
