import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from app import database
from app.database import connect_database, database_transaction, initialize_database


class PortalMigrationTest(unittest.TestCase):
    def test_existing_v5_accounts_ledgers_and_receipts_survive_upgrade_and_restart(self):
        path = Path(self.enterContext(TemporaryDirectory())) / "existing.sqlite3"
        schema_dir = Path(database.__file__).parent
        with closing(connect_database(path, create=True)) as db:
            for migration in ("schema.sql", "receipts_migration.sql", "ledger_pagination_migration.sql",
                              "receipt_lifecycle_migration.sql", "auth_migration.sql"):
                db.executescript((schema_dir / migration).read_text(encoding="utf-8"))
            db.executescript("""
                PRAGMA user_version=5;
                INSERT INTO users(full_name,normalized_phone_number,password_hash,role)
                  VALUES('Buyer','+919987654321','existing hash','CUSTOMER');
                INSERT INTO customers(id,shop_id,name) VALUES(7,1,'Buyer'),(8,1,'Old second record');
                INSERT INTO customer_account_links(customer_id,user_id) VALUES(7,1),(8,1);
                INSERT INTO transaction_batches(shop_id,id) VALUES(1,'original');
                INSERT INTO ledger_entries(id,shop_id,batch_id,customer_id,type,amount_paise)
                  VALUES(5,1,'original',7,'CREDIT',12345);
                INSERT INTO receipts(id,shop_id,customer_id,ledger_entry_id) VALUES(4,1,7,5);
            """)
        initialize_database(path)
        initialize_database(path)
        with database_transaction(path) as db:
            self.assertEqual(db.execute("PRAGMA user_version").fetchone()[0], database.SCHEMA_VERSION)
            self.assertEqual([tuple(r) for r in db.execute("SELECT customer_id,user_id FROM customer_account_links "
                                                           "ORDER BY customer_id")], [(7,1),(8,1)])
            self.assertEqual(db.execute("SELECT password_hash FROM users").fetchone()[0], "existing hash")
            self.assertEqual(db.execute("SELECT amount_paise FROM ledger_entries WHERE id=5").fetchone()[0], 12345)
            self.assertEqual(db.execute("SELECT ledger_entry_id FROM receipts WHERE id=4").fetchone()[0], 5)
            self.assertEqual(db.execute("SELECT count(*) FROM notifications").fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
