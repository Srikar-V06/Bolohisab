import sqlite3
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier

from app.database import DEFAULT_SHOP_ID, SCHEMA_VERSION, connect_database, database_transaction, initialize_database
from app.ledger import (
    MAX_SQLITE_INTEGER,
    BatchConflict,
    CustomerNotFound,
    LedgerEntryDraft,
    ledger_session,
)
from app.seed_demo import seed_demo

SHOP = DEFAULT_SHOP_ID


class LedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "ledger.sqlite3"
        initialize_database(self.path)
        with ledger_session(self.path, write=True) as ledger:
            self.customer = ledger.create_customer(SHOP, "Ramesh")

    def test_customer_creation_preserves_name_and_starts_at_zero(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            customer = ledger.create_customer(SHOP, "  सीता Devi  ")
            self.assertEqual(customer.name, "  सीता Devi  ")
            self.assertEqual(ledger.calculate_balance(SHOP, customer.id), 0)
            self.assertEqual(ledger.get_transaction_history(SHOP, customer.id), [])
            self.assertEqual(ledger.list_customers(SHOP), [self.customer, customer])
            with self.assertRaises(ValueError):
                ledger.create_customer(SHOP, " \t\n ")
            with self.assertRaises(ValueError):
                ledger.create_customer(999, "Suresh")

    def test_credit_and_payment_produce_opposite_effects(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            customer_id = self.customer.id
            credit = ledger.create_ledger_entry(SHOP, "credit", LedgerEntryDraft(customer_id, "CREDIT", 45_000))
            self.assertEqual(credit.balance_effect_paise, 45_000)
            self.assertEqual(ledger.calculate_balance(SHOP, customer_id), 45_000)
            payment = ledger.create_ledger_entry(SHOP, "payment", LedgerEntryDraft(customer_id, "PAYMENT", 60_000))
            self.assertEqual(payment.amount_paise, 60_000)
            self.assertEqual(payment.balance_effect_paise, -60_000)
            self.assertEqual(ledger.calculate_balance(SHOP, customer_id), -15_000)

    def test_adjustments_append_linked_corrections(self) -> None:
        with ledger_session(self.path, write=True) as ledger:
            customer_id = self.customer.id
            original = ledger.create_ledger_entry(
                SHOP, "original", LedgerEntryDraft(customer_id, "CREDIT", 10_000),
            )
            plus = ledger.create_ledger_entry(SHOP, "plus", LedgerEntryDraft(customer_id, "ADJUSTMENT", 2_500))
            minus = ledger.create_ledger_entry(
                SHOP, "minus", LedgerEntryDraft(customer_id, "ADJUSTMENT", -900, original.id),
            )
            self.assertEqual(minus.corrects_entry_id, original.id)
            self.assertEqual(ledger.calculate_balance(SHOP, customer_id), 11_600)
            self.assertEqual(ledger.get_transaction_history(SHOP, customer_id), [original, plus, minus])
            sita = ledger.create_customer(SHOP, "Sita")
            with self.assertRaisesRegex(ValueError, "same customer"):
                ledger.create_ledger_entry(SHOP, "wrong-reference", LedgerEntryDraft(sita.id, "ADJUSTMENT", -1, original.id))
            self.assertIsNone(ledger.get_batch(SHOP, "wrong-reference"))

    def test_combined_batch_gives_1250_rupees_and_preserves_metadata(self) -> None:
        transcript = "  Ramesh ने ₹450 का उधार लिया।\n₹200 नकद दिए।  "
        with ledger_session(self.path, write=True) as ledger:
            customer_id = self.customer.id
            ledger.create_ledger_entry(SHOP, "opening", LedgerEntryDraft(customer_id, "CREDIT", 100_000))
            batch = ledger.create_transaction_batch(SHOP, "purchase-and-payment", [
                LedgerEntryDraft(customer_id, "CREDIT", 45_000),
                LedgerEntryDraft(customer_id, "PAYMENT", 20_000),
            ], original_transcript=transcript, detected_language="hi-IN")
        with ledger_session(self.path) as ledger:
            history = ledger.get_transaction_history(SHOP, customer_id)
            self.assertEqual([entry.type for entry in history], ["CREDIT", "CREDIT", "PAYMENT"])
            self.assertEqual([entry.batch_id for entry in history], ["opening", batch.id, batch.id])
            self.assertEqual(history[-1].original_transcript, transcript)
            self.assertEqual(history[-1].detected_language, "hi-IN")
            self.assertEqual(ledger.calculate_balance(SHOP, customer_id), 125_000)

    def test_rejects_invalid_amounts_types_and_ids(self) -> None:
        for amount in (0, 1.25, 100.0, True, "100", MAX_SQLITE_INTEGER + 1, -MAX_SQLITE_INTEGER - 1):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                LedgerEntryDraft(self.customer.id, "ADJUSTMENT", amount)
        for entry_type in ("CREDIT", "PAYMENT"):
            with self.subTest(entry_type=entry_type), self.assertRaises(ValueError):
                LedgerEntryDraft(self.customer.id, entry_type, -10)
        with self.assertRaises(ValueError):
            LedgerEntryDraft(True, "PAYMENT", 10)
        with self.assertRaises(ValueError):
            LedgerEntryDraft(self.customer.id, "भुगतान", 10)
        with self.assertRaises(ValueError):
            LedgerEntryDraft(self.customer.id, "CREDIT", 10, 1)
        with ledger_session(self.path, write=True) as ledger:
            with self.assertRaises(ValueError):
                ledger.create_transaction_batch(SHOP, "empty", [])

    def test_balance_sum_remains_an_exact_integer_beyond_sqlite_sum_range(self) -> None:
        draft = LedgerEntryDraft(self.customer.id, "CREDIT", MAX_SQLITE_INTEGER)
        with ledger_session(self.path, write=True) as ledger:
            ledger.create_transaction_batch(SHOP, "large", [draft, draft])
            self.assertEqual(ledger.calculate_balance(SHOP, self.customer.id), 2 * MAX_SQLITE_INTEGER)

    def test_failed_batch_rolls_back_even_if_caller_continues(self) -> None:
        valid = LedgerEntryDraft(self.customer.id, "CREDIT", 100)
        missing_customer = LedgerEntryDraft(999, "PAYMENT", 30)
        with ledger_session(self.path, write=True) as ledger:
            with self.assertRaises(CustomerNotFound):
                ledger.create_transaction_batch(SHOP, "rollback-and-retry", [valid, missing_customer])
            self.assertIsNone(ledger.get_batch(SHOP, "rollback-and-retry"))
            self.assertEqual(ledger.calculate_balance(SHOP, self.customer.id), 0)
            ledger.create_ledger_entry(SHOP, "rollback-and-retry", valid)
        with ledger_session(self.path) as ledger:
            self.assertEqual(ledger.calculate_balance(SHOP, self.customer.id), 100)

    def test_outer_transaction_rolls_back_customers_and_batches(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Abort"):
            with ledger_session(self.path, write=True) as ledger:
                customer = ledger.create_customer(SHOP, "Sita")
                entry = LedgerEntryDraft(customer.id, "CREDIT", 100)
                ledger.create_ledger_entry(SHOP, "outer-rollback", entry)
                raise RuntimeError("Abort")
        with ledger_session(self.path) as ledger:
            self.assertEqual(ledger.list_customers(SHOP), [self.customer])
            self.assertIsNone(ledger.get_batch(SHOP, "outer-rollback"))

    def test_retry_reuses_batch_and_rejects_changed_entries_or_metadata(self) -> None:
        credit = LedgerEntryDraft(self.customer.id, "CREDIT", 100)
        payment = LedgerEntryDraft(self.customer.id, "PAYMENT", 40)
        with ledger_session(self.path, write=True) as ledger:
            original = ledger.create_transaction_batch(SHOP, "retry", [credit, payment], detected_language="en-IN")
        with ledger_session(self.path, write=True) as ledger:
            retry = ledger.create_transaction_batch(SHOP, "retry", [credit, payment], detected_language="en-IN")
            self.assertEqual(retry, original)
            with self.assertRaises(BatchConflict):
                ledger.create_transaction_batch(SHOP, "retry", [payment, credit], detected_language="en-IN")
            with self.assertRaises(BatchConflict):
                ledger.create_transaction_batch(SHOP, "retry", [credit, payment], detected_language="ta-IN")
            self.assertEqual(ledger.calculate_balance(SHOP, self.customer.id), 60)

    def test_concurrent_duplicate_requests_record_only_one_entry(self) -> None:
        ready = Barrier(2)
        draft = LedgerEntryDraft(self.customer.id, "CREDIT", 10)

        def submit():
            ready.wait(timeout=5)
            with ledger_session(self.path, write=True) as ledger:
                return ledger.create_ledger_entry(SHOP, "concurrent", draft)

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(submit)
            second = executor.submit(submit)
            self.assertEqual(first.result(timeout=10), second.result(timeout=10))
        with ledger_session(self.path) as ledger:
            self.assertEqual(ledger.calculate_balance(SHOP, self.customer.id), 10)
            self.assertEqual(len(ledger.get_transaction_history(SHOP, self.customer.id)), 1)

    def test_shop_scoping_and_database_constraints(self) -> None:
        with database_transaction(self.path, write=True) as connection:
            connection.execute("INSERT INTO shops (id, name) VALUES (2, 'Another Shop')")
        with ledger_session(self.path, write=True) as ledger:
            other = ledger.create_customer(2, "Suresh")
            original = ledger.create_ledger_entry(SHOP, "shared", LedgerEntryDraft(self.customer.id, "CREDIT", 100))
            ledger.create_ledger_entry(2, "shared", LedgerEntryDraft(other.id, "PAYMENT", 50))
            with self.assertRaises(CustomerNotFound):
                ledger.create_ledger_entry(SHOP, "wrong-shop", LedgerEntryDraft(other.id, "CREDIT", 1))
            self.assertEqual(ledger.calculate_balance(2, other.id), -50)
        with database_transaction(self.path, write=True) as connection:
            for query, params in [
                ("UPDATE ledger_entries SET amount_paise = 1 WHERE id = ?", (original.id,)),
                ("DELETE FROM ledger_entries WHERE id = ?", (original.id,)),
                (
                    "INSERT OR REPLACE INTO ledger_entries (id, shop_id, customer_id, batch_id, type, amount_paise) "
                    "VALUES (?, ?, ?, 'shared', 'CREDIT', 1)",
                    (original.id, SHOP, self.customer.id),
                ),
                (
                    "INSERT INTO ledger_entries (shop_id, customer_id, batch_id, type, amount_paise) "
                    "VALUES (?, ?, 'shared', 'CREDIT', 1)",
                    (SHOP, other.id),
                ),
                (
                    "INSERT INTO ledger_entries (shop_id, customer_id, batch_id, type, amount_paise) "
                    "VALUES (?, ?, 'shared', 'PAYMENT', -1)",
                    (SHOP, self.customer.id),
                ),
                ("UPDATE transaction_batches SET detected_language = 'en-IN' WHERE shop_id = ? AND id = 'shared'", (SHOP,)),
            ]:
                with self.subTest(query=query), self.assertRaises(sqlite3.IntegrityError):
                    connection.execute(query, params)
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])


class MigrationAndSeedTest(unittest.TestCase):
    def test_migration_upgrades_existing_database_and_seed_is_idempotent(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "existing.sqlite3"
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute("CREATE TABLE earlier_data (name TEXT)")
                connection.execute("INSERT INTO earlier_data VALUES ('preserved')")
            self.assertTrue(seed_demo(path))
            self.assertFalse(seed_demo(path))
            with ledger_session(path) as ledger:
                customers = ledger.list_customers(SHOP)
                self.assertEqual(
                    [(c.name, c.balance_paise) for c in customers],
                    [("Ramesh", 125_000), ("Suresh", 39_000), ("Sita", 22_500)],
                )
                self.assertEqual(sum(len(ledger.get_transaction_history(SHOP, c.id)) for c in customers), 7)
            with closing(connect_database(path)) as connection:
                self.assertEqual(connection.execute("SELECT name FROM earlier_data").fetchone()[0], "preserved")
                self.assertEqual(connection.execute("SELECT count(*) FROM shops").fetchone()[0], 1)
                self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], SCHEMA_VERSION)
