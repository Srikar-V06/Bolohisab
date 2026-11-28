import unittest
from concurrent.futures import ThreadPoolExecutor
from os import environ
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from auth_test_support import TEST_REVIEWER, authenticate_existing_shop

from app.database import DEFAULT_SHOP_ID, connect_database, database_transaction
from app.ledger import MAX_SQLITE_INTEGER, LedgerEntryDraft, ledger_session
from app.main import create_app
from app.seed_demo import seed_stitch_preview


class ConfirmationReceiptTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = self.enterContext(TemporaryDirectory())
        self.path = Path(folder) / "receipts.sqlite3"
        self.client = self.enterContext(TestClient(create_app(self.path)))
        authenticate_existing_shop(self.client, self.path)
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
        self.assertEqual(self.client.get("/api/receipts").json()[0]["status"], "AWAITING")
        self.assertEqual(self.client.post("/api/receipts/99999", json={"language": "hi-IN"}).status_code, 404)
        self.assertEqual(self.client.post(endpoint + "/sent").status_code, 404)
        issued = self.client.post(endpoint, json={"language": "hi-IN"})
        self.assertEqual(issued.status_code, 200, issued.text)
        info = issued.json()
        self.assertIsNone(info["sent_at"])
        self.assertEqual(info["status"], "GENERATED")
        self.assertIsNotNone(info["receipt_id"])
        self.assertEqual(info["balance_after_paise"], 100_000)
        self.assertEqual(self.client.post(endpoint, json={"language": "en-IN"}).json(), info)
        url = "/api/receipts/share/" + info["share_token"]
        hindi = self.client.get(url)
        self.assertEqual(hindi.status_code, 200)
        self.assertIn("रसीद", hindi.text)
        self.assertIn("Ramesh", hindi.text)
        self.assertIn("₹1000", hindi.text)
        self.assertEqual(hindi.headers["cache-control"], "no-store")
        self.assertEqual(hindi.headers["referrer-policy"], "no-referrer")
        self.assertIn("frame-ancestors 'none'", hindi.headers["content-security-policy"])
        self.assertIn("Balance after transaction", self.client.get(url, params={"language": "en-IN"}).text)
        self.assertEqual(self.client.get("/api/receipts/share/" + "x" * 43).status_code, 404)
        sent = self.client.post(endpoint + "/sent").json()
        self.assertIsNotNone(sent["sent_at"])
        self.assertEqual(sent["status"], "SENT")
        self.assertEqual(sent, self.client.post(endpoint + "/sent").json())

    def test_public_token_is_scoped_and_confirmation_is_idempotent(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            other = ledger.create_customer(DEFAULT_SHOP_ID, "Other <script>alert(1)</script>")
            other_entry = ledger.create_ledger_entry(
                DEFAULT_SHOP_ID, "other", LedgerEntryDraft(other.id, "CREDIT", 2_031),
            )
        with patch.dict(environ, {"PUBLIC_RECEIPT_ORIGIN": "https://receipts.example.com"}):
            with TestClient(create_app(self.path)) as public_client:
                authenticate_existing_shop(public_client, self.path)
                info = public_client.post(f"/api/receipts/{self.initial.id}", json={"language": "en-IN"}).json()
                self.assertRegex(info["share_token"], r"^[A-Za-z0-9_-]{43}$")
                self.assertEqual(info["share_url"], "https://receipts.example.com/api/receipts/share/" + info["share_token"])
        other_info = self.client.post(f"/api/receipts/{other_entry.id}", json={"language": "hi-IN"}).json()
        self.assertNotEqual(info["share_token"], other_info["share_token"])
        url = "/api/receipts/share/" + info["share_token"]
        english = self.client.get(url)
        self.assertIn('lang="en-IN"', english.text)
        self.assertIn("Listen to receipt", english.text)
        self.assertNotIn("Other", english.text)
        other_page = self.client.get("/api/receipts/share/" + other_info["share_token"])
        self.assertIn("Other &lt;script&gt;alert(1)&lt;/script&gt;", other_page.text)
        self.assertNotIn("Ramesh", other_page.text)
        for bad_token in ("invalid", "x" * 43):
            bad_url = f"/api/receipts/share/{bad_token}"
            response = self.client.get(bad_url, params={"language": "en-IN"})
            self.assertEqual(response.status_code, 404)
            self.assertIn("This receipt could not be found.", response.text)
            self.assertEqual(self.client.post(bad_url + "/confirm").status_code, 404)
            self.assertEqual(self.client.post(bad_url + "/dispute", json={
                "claimed_amount_paise": 300, "reason": "Wrong amount",
            }).status_code, 404)
        self.assertEqual(self.client.post(url + "/confirm").status_code, 204)
        confirmed = self.client.get("/api/receipts").json()[1]
        self.assertEqual(confirmed["status"], "CONFIRMED")
        self.assertIsNotNone(confirmed["confirmed_at"])
        self.assertEqual(self.client.post(url + "/confirm").status_code, 204)
        self.assertEqual(self.client.get("/api/receipts").json()[1], confirmed)
        self.assertEqual(self.client.post(url + "/dispute", json={
            "claimed_amount_paise": 300, "reason": "Wrong amount",
        }).json()["detail"], "RECEIPT_ALREADY_CONFIRMED")
        self.assertIn("You confirmed this transaction.", self.client.get(url).text)

    def test_payment_dispute_creates_one_adjustment_and_preserves_history(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            original = ledger.create_ledger_entry(
                DEFAULT_SHOP_ID, "original-payment", LedgerEntryDraft(self.customer.id, "PAYMENT", 20_000),
            )
        endpoint = f"/api/receipts/{original.id}"
        issued = self.client.post(endpoint, json={"language": "hi-IN"}).json()
        public_url = "/api/receipts/share/" + issued["share_token"]
        claim = {"claimed_amount_paise": "30000", "reason": "  I paid ₹300 in cash.  "}
        for amount in (-200, 20_000, "9223372036854775808", True, 30000.5):
            response = self.client.post(public_url + "/dispute", json={**claim, "claimed_amount_paise": amount})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.client.post(public_url + "/dispute", json={**claim, "reason": " "}).status_code, 422)
        self.assertEqual(self.client.post(public_url + "/dispute", json=claim).status_code, 204)
        self.assertEqual(self.client.post(public_url + "/dispute", json=claim).status_code, 204)
        self.assertEqual(self.client.post(public_url + "/dispute", json={**claim, "reason": "Different"}).status_code, 409)
        self.assertEqual(self.client.post(public_url + "/confirm").json()["detail"], "RECEIPT_ALREADY_DISPUTED")
        pending = self.client.get("/api/receipts").json()[0]
        self.assertEqual(pending["status"], "DISPUTED")
        self.assertEqual(pending["dispute"]["status"], "PENDING")
        self.assertEqual(pending["dispute"]["adjustment_paise"], -10_000)
        self.assertEqual(pending["dispute"]["reason"], "I paid ₹300 in cash.")

        decision = {"decision": "APPROVED", "reviewer": "Kirana owner"}
        review = endpoint + "/dispute/review"
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _: self.client.post(review, json=decision), range(2)))
        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(responses[0].json(), responses[1].json())
        resolved = responses[0].json()
        self.assertEqual(resolved["balance_after_paise"], 80_000)
        self.assertEqual(resolved["dispute"]["reviewed_by"], TEST_REVIEWER)
        self.assertEqual(resolved["dispute"]["reviewed_by_user_id"], self.client.get("/api/auth/me").json()["id"])
        self.assertEqual(resolved["dispute"]["status"], "APPROVED")
        self.assertIsNotNone(resolved["dispute"]["reviewed_at"])
        self.assertEqual(self.client.post(review, json={**decision, "decision": "REJECTED"}).status_code, 409)
        self.assertIn("accepted your correction", self.client.get(public_url, params={"language": "en-IN"}).text)
        self.assertNotIn("Kirana owner", self.client.get(public_url).text)
        self.assertEqual(self.client.get(f"/api/customers/{self.customer.id}").json()["balance_paise"], 70_000)
        url = f"/api/customers/{self.customer.id}/ledger"
        first = self.client.get(url, params={"limit": 1}).json()
        adjustment, = first["items"]
        self.assertEqual(
            [adjustment[field] for field in ("type", "amount_paise", "balance_after_paise", "corrects_entry_id")],
            ["ADJUSTMENT", -10_000, 70_000, original.id],
        )
        self.assertEqual(adjustment["id"], resolved["dispute"]["adjustment_entry_id"])
        older = self.client.get(url, params={"limit": 5, "cursor": first["next_cursor"]}).json()
        self.assertEqual([(item["id"], item["amount_paise"]) for item in older["items"]],
                         [(original.id, 20_000), (self.initial.id, 100_000)])
        self.assertFalse(older["has_more"])

    def test_rejection_leaves_ledger_unchanged_and_audits_reviewer(self) -> None:
        endpoint = f"/api/receipts/{self.initial.id}"
        info = self.client.post(endpoint, json={"language": "en-IN"}).json()
        url = "/api/receipts/share/" + info["share_token"]
        self.assertEqual(self.client.post(url + "/dispute", json={
            "claimed_amount_paise": 0, "reason": "No credit was taken",
        }).status_code, 204)
        reply = self.client.post(endpoint + "/dispute/review", json={"decision": "REJECTED", "reviewer": "Shop owner"})
        self.assertEqual(reply.status_code, 200, reply.text)
        dispute = reply.json()["dispute"]
        self.assertEqual(dispute["status"], "REJECTED")
        self.assertEqual(dispute["reviewed_by"], TEST_REVIEWER)
        self.assertIsNotNone(dispute["reviewed_at"])
        self.assertIsNone(dispute["adjustment_entry_id"])
        self.assertIn("rejected your correction", self.client.get(url).text)
        self.assertEqual(self.client.get(f"/api/customers/{self.customer.id}").json()["balance_paise"], 100_000)
        self.assertEqual(len(self.client.get(f"/api/customers/{self.customer.id}/ledger").json()), 1)

    def test_large_receipt_amounts_preserve_every_paise(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            entry = ledger.create_ledger_entry(
                DEFAULT_SHOP_ID, "large-credit", LedgerEntryDraft(self.customer.id, "CREDIT", MAX_SQLITE_INTEGER),
            )
        reply = self.client.post(f"/api/receipts/{entry.id}", json={"language": "en-IN"})
        self.assertEqual(reply.status_code, 200, reply.text)
        item = reply.json()
        self.assertEqual(item["amount_paise"], str(MAX_SQLITE_INTEGER))
        self.assertEqual(item["balance_after_paise"], str(MAX_SQLITE_INTEGER + 100_000))
        shared = self.client.get("/api/receipts/share/" + item["share_token"])
        self.assertIn("₹92233720368547758.07", shared.text)

    def test_stitch_seed_uses_real_balances_and_three_awaiting_receipts(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "demo.sqlite3"
            self.assertTrue(seed_stitch_preview(path))
            self.assertFalse(seed_stitch_preview(path))
            with TestClient(create_app(path)) as client:
                authenticate_existing_shop(client, path)
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
                authenticate_existing_shop(client, path)
                issued_before, = client.get("/api/receipts").json()
                self.assertIsNotNone(issued_before["issued_at"])
                self.assertIsNone(issued_before["share_token"])
                issued_after = client.post("/api/receipts/1", json={"language": "en-IN"}).json()
                self.assertEqual(issued_after["issued_at"], issued_before["issued_at"])
                self.assertEqual(issued_after["language"], "en-IN")
                self.assertTrue(issued_after["share_token"])
            with database_transaction(path) as conn:
                self.assertEqual(conn.execute("SELECT count(*) FROM receipts").fetchone()[0], 1)
