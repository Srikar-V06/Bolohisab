from argparse import ArgumentParser
from pathlib import Path

from .database import DEFAULT_SHOP_ID, database_path, initialize_database
from .ledger import LedgerEntryDraft, ledger_session
from .localization import LanguageCode
from .receipt_store import generate_receipt, mark_receipt_sent

DEMO_BATCH_ID = "bolohisaab-demo-v1"
STITCH_BATCH_ID = "bolohisaab-stitch-demo-v1"


def seed_demo(path: Path) -> bool:
    initialize_database(path)
    with ledger_session(path, write=True) as ledger:
        if ledger.get_batch(DEFAULT_SHOP_ID, DEMO_BATCH_ID) is not None:
            return False

        ramesh = ledger.create_customer(DEFAULT_SHOP_ID, "Ramesh")
        suresh = ledger.create_customer(DEFAULT_SHOP_ID, "Suresh")
        sita = ledger.create_customer(DEFAULT_SHOP_ID, "Sita")
        ledger.create_transaction_batch(DEFAULT_SHOP_ID, DEMO_BATCH_ID, [
            LedgerEntryDraft(ramesh.id, "CREDIT", 100_000),
            LedgerEntryDraft(ramesh.id, "CREDIT", 45_000),
            LedgerEntryDraft(ramesh.id, "PAYMENT", 20_000),
            LedgerEntryDraft(suresh.id, "CREDIT", 64_000),
            LedgerEntryDraft(suresh.id, "PAYMENT", 25_000),
            LedgerEntryDraft(sita.id, "CREDIT", 37_500),
            LedgerEntryDraft(sita.id, "PAYMENT", 15_000),
        ])
    return True


def seed_stitch_preview(path: Path) -> bool:
    initialize_database(path)
    shop_id = DEFAULT_SHOP_ID
    with ledger_session(path, write=True) as ledger:
        if ledger.get_batch(shop_id, STITCH_BATCH_ID) is not None:
            return False

        ramesh, sunita, suresh, mohan = (
            ledger.create_customer(shop_id, name).id
            for name in ("Ramesh Kumar", "Sunita Devi", "Suresh", "Mohan")
        )
        earlier = ledger.create_transaction_batch(shop_id, f"{STITCH_BATCH_ID}-earlier", [
            LedgerEntryDraft(ramesh, "CREDIT", 100_000),
            LedgerEntryDraft(ramesh, "PAYMENT", 20_000, payment_method="CASH"),
            LedgerEntryDraft(sunita, "CREDIT", 260_000),
            LedgerEntryDraft(suresh, "CREDIT", 55_000),
            LedgerEntryDraft(mohan, "CREDIT", 50_000),
            LedgerEntryDraft(mohan, "PAYMENT", 50_000, payment_method="CASH"),
        ])
        for entry in earlier.entries:
            generate_receipt(ledger.connection, shop_id, entry.id, LanguageCode.HINDI)
            mark_receipt_sent(ledger.connection, shop_id, entry.id)
        ledger.create_transaction_batch(shop_id, STITCH_BATCH_ID, [
            LedgerEntryDraft(suresh, "CREDIT", 30_000),
            LedgerEntryDraft(sunita, "PAYMENT", 20_000, payment_method="CASH"),
            LedgerEntryDraft(ramesh, "CREDIT", 45_000),
        ])
    return True


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("--stitch-preview", action="store_true", help="Seed the Stitch screen reference data.")
    args = parser.parse_args()
    seeded = (seed_stitch_preview if args.stitch_preview else seed_demo)(database_path())
    print("Seeded the kirana shop demo." if seeded else "The kirana shop demo is already present.")
