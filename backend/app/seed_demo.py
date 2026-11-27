from pathlib import Path

from .database import DEFAULT_SHOP_ID, database_path, initialize_database
from .ledger import LedgerEntryDraft, ledger_session

DEMO_BATCH_ID = "bolohisaab-demo-v1"


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


if __name__ == "__main__":
    seeded = seed_demo(database_path())
    print("Seeded the kirana shop demo." if seeded else "The kirana shop demo is already present.")
