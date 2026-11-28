from argparse import ArgumentParser
from getpass import getpass
from os import environ
from pathlib import Path
from sqlite3 import IntegrityError

from .auth_store import create_account, hash_password, normalize_phone
from .database import database_path, database_transaction, initialize_database
from .ledger import Ledger, LedgerEntryDraft, validate_customer_name
from .localization import LanguageCode
from .receipt_store import generate_receipt


DEMO_ACCOUNTS = (
    ("Demo Shopkeeper", "+919000000001", "Demo shopkeeper passphrase"),
    ("Demo Customer One", "+919000000002", "Demo customer one passphrase"),
    ("Demo Customer Two", "+919000000003", "Demo customer two passphrase"),
)


def seed_demo_accounts(path: Path) -> bool:
    if environ.get("BOLO_ENV") != "development":
        raise ValueError("Set BOLO_ENV=development to seed an isolated development database")
    initialize_database(path)
    credentials = [(name, phone, hash_password(password)) for name, phone, password in DEMO_ACCOUNTS]
    with database_transaction(path, write=True) as db:
        existing = db.execute(
            """
            SELECT full_name, role FROM users WHERE normalized_phone_number = ?
            """,
            (credentials[0][1],),
        ).fetchone()
        if existing and tuple(existing) == (credentials[0][0], "SHOPKEEPER"):
            return False
        shop_id = db.execute("INSERT INTO shops (name) VALUES ('Demo Kirana Shop') RETURNING id").fetchone()[0]
        create_account(db, *credentials[0], "SHOPKEEPER", shop_id)
        ledger = Ledger(db)
        for index, credential in enumerate(credentials[1:], start=1):
            account = create_account(db, *credential, "CUSTOMER", None)
            customer = ledger.create_customer(shop_id, account.full_name)
            db.execute("INSERT INTO customer_account_links (customer_id, user_id) VALUES (?, ?)",
                       (customer.id, account.id))
            entry = ledger.create_ledger_entry(
                shop_id, f"account-demo-{index}", LedgerEntryDraft(customer.id, "CREDIT", index * 20_000),
            )
            generate_receipt(db, shop_id, entry.id, LanguageCode.HINDI)
    return True


def main() -> None:
    parser = ArgumentParser(description="Manage accounts with trusted local database access.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed-demo")
    claim = commands.add_parser("claim-shop", help="Provision the verified owner of an existing shop.")
    claim.add_argument("--shop-id", type=int, required=True)
    claim.add_argument("--phone", required=True)
    claim.add_argument("--name", required=True)
    link = commands.add_parser("link-customer", help="Link a verified customer account to an explicit ledger record.")
    link.add_argument("--customer-id", type=int, required=True)
    link.add_argument("--phone", required=True)
    args = parser.parse_args()
    path = database_path()
    try:
        if args.command == "seed-demo":
            print("Seeded demo accounts." if seed_demo_accounts(path) else "Demo accounts already present.")
            return
        phone = normalize_phone(args.phone)
        initialize_database(path)
        if args.command == "claim-shop":
            name = validate_customer_name(args.name.strip())
            password = getpass("New shopkeeper passphrase: ")
            if password != getpass("Repeat the passphrase: ") or not 10 <= len(password) <= 1024:
                raise ValueError("Passphrases must match and contain 10 to 1024 characters")
            encoded = hash_password(password)
            with database_transaction(path, write=True) as db:
                create_account(db, name, phone, encoded, "SHOPKEEPER", args.shop_id)
        else:
            with database_transaction(path, write=True) as db:
                account = db.execute(
                    "SELECT id FROM users WHERE normalized_phone_number = ? AND role = 'CUSTOMER' AND is_active = 1",
                    (phone,),
                ).fetchone()
                if account is None:
                    raise ValueError("An active customer account is required")
                existing = db.execute("SELECT user_id FROM customer_account_links WHERE customer_id = ?",
                                      (args.customer_id,)).fetchone()
                if existing is None:
                    db.execute("INSERT INTO customer_account_links (customer_id, user_id) VALUES (?, ?)",
                               (args.customer_id, account["id"]))
                elif existing["user_id"] != account["id"]:
                    raise ValueError("Ledger record is already linked to a different account")
        print("Account association saved.")
    except IntegrityError:
        parser.error("Account association failed. Check the verified account and record IDs.")
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
