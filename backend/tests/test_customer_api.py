import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from app.database import DEFAULT_SHOP_ID, database_transaction
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

    def test_cursor_pages_same_timestamp_entries_with_exact_running_balances(self) -> None:
        customer = self.client.post("/api/customers", json={"name": "Ramesh"}).json()
        customer_id = customer["id"]
        url = f"/api/customers/{customer_id}/ledger"
        timestamp = "2026-11-26T06:12:00.000Z"

        with database_transaction(self.path, write=True) as connection:
            connection.execute("INSERT INTO transaction_batches (shop_id, id) VALUES (1, 'pagination')")
            rows = [
                (customer_id, "CREDIT", 10_000, timestamp if index != 9 else "2026-11-25T06:12:00.000Z")
                for index in range(10)
            ] + [(customer_id, "PAYMENT", 7_500, timestamp), (customer_id, "ADJUSTMENT", -500, timestamp)]
            connection.executemany(
                """
                INSERT INTO ledger_entries (shop_id, batch_id, customer_id, type, amount_paise, created_at)
                VALUES (1, 'pagination', ?, ?, ?, ?)
                """,
                rows,
            )

        first = self.client.get(url, params={"limit": 5}).json()
        self.assertEqual([row["id"] for row in first["items"]], [12, 11, 9, 8, 7])
        self.assertEqual([row["balance_after_paise"] for row in first["items"]], [92_000, 92_500, 100_000, 90_000, 80_000])
        self.assertTrue(first["has_more"])

        # A backdated append must not change an already-open history snapshot.
        with database_transaction(self.path, write=True) as connection:
            connection.execute(
                """
                INSERT INTO ledger_entries (shop_id, batch_id, customer_id, type, amount_paise, created_at)
                VALUES (1, 'pagination', ?, 'CREDIT', 100, '2026-11-24T06:12:00.000Z')
                """,
                (customer_id,),
            )

        second = self.client.get(url, params={"limit": 5, "cursor": first["next_cursor"]}).json()
        self.assertEqual([row["id"] for row in second["items"]], [6, 5, 4, 3, 2])
        self.assertEqual(second["items"][0]["balance_after_paise"], 70_000)
        self.assertTrue(second["has_more"])

        final = self.client.get(url, params={"cursor": second["next_cursor"]}).json()
        self.assertEqual([row["id"] for row in final["items"]], [1, 10])
        self.assertEqual([row["balance_after_paise"] for row in final["items"]], [20_000, 10_000])
        self.assertEqual(final["has_more"], False)
        self.assertIsNone(final["next_cursor"])
        self.assertEqual(self.client.get(url, params={"limit": 1}).json()["items"][0]["balance_after_paise"], 92_100)

    def test_paged_history_empty_limits_and_cursor_customer_scope(self) -> None:
        first = self.client.post("/api/customers", json={"name": "Ramesh"}).json()["id"]
        second = self.client.post("/api/customers", json={"name": "Sita"}).json()["id"]
        self.assertEqual(
            self.client.get(f"/api/customers/{second}/ledger?limit=5").json(),
            {"items": [], "has_more": False, "next_cursor": None},
        )
        with ledger_session(self.path, write=True) as ledger:
            ledger.create_transaction_batch(DEFAULT_SHOP_ID, "scope", [
                LedgerEntryDraft(first, "CREDIT", 10_000), LedgerEntryDraft(first, "PAYMENT", 100),
            ])
            ledger.connection.execute("INSERT INTO shops (id, name) VALUES (2, 'Other shop')")
            other_shop = ledger.create_customer(2, "Mohan").id
        url = f"/api/customers/{first}/ledger"
        token = self.client.get(url, params={"limit": 1}).json()["next_cursor"]
        self.assertEqual(self.client.get(f"/api/customers/{second}/ledger", params={"cursor": token}).status_code, 422)
        self.assertEqual(self.client.get(f"/api/customers/{other_shop}/ledger?limit=1").status_code, 404)
        self.assertEqual(self.client.get(url, params={"cursor": "broken!"}).status_code, 422)
        self.assertEqual(self.client.get(url, params={"limit": 0}).status_code, 422)
        self.assertEqual(self.client.get(url, params={"limit": 51}).status_code, 422)
