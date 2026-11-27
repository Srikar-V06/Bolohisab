CREATE TABLE IF NOT EXISTS shops (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 120),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
) STRICT;

CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0 AND length(name) <= 120),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (shop_id, id)
) STRICT;

CREATE TABLE IF NOT EXISTS transaction_batches (
    shop_id INTEGER NOT NULL REFERENCES shops(id),
    id TEXT NOT NULL CHECK (length(id) BETWEEN 1 AND 128 AND id = trim(id)),
    original_transcript TEXT,
    detected_language TEXT CHECK (length(trim(detected_language)) BETWEEN 1 AND 64),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (shop_id, id)
) STRICT;

CREATE TABLE IF NOT EXISTS ledger_entries (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    shop_id INTEGER NOT NULL,
    batch_id TEXT NOT NULL,
    customer_id INTEGER NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('CREDIT', 'PAYMENT', 'ADJUSTMENT')),
    amount_paise INTEGER NOT NULL CHECK (
        amount_paise > -9223372036854775808
        AND amount_paise <> 0
        AND (type = 'ADJUSTMENT' OR amount_paise > 0)
    ),
    balance_effect_paise INTEGER GENERATED ALWAYS AS (
        CASE type WHEN 'PAYMENT' THEN -amount_paise ELSE amount_paise END
    ) STORED,
    corrects_entry_id INTEGER CHECK (
        corrects_entry_id IS NULL OR (type = 'ADJUSTMENT' AND corrects_entry_id < id)
    ),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (shop_id, customer_id, id),
    FOREIGN KEY (shop_id, batch_id) REFERENCES transaction_batches(shop_id, id),
    FOREIGN KEY (shop_id, customer_id) REFERENCES customers(shop_id, id),
    FOREIGN KEY (shop_id, customer_id, corrects_entry_id)
        REFERENCES ledger_entries(shop_id, customer_id, id)
) STRICT;

CREATE INDEX IF NOT EXISTS ledger_entries_batch ON ledger_entries(shop_id, batch_id, id);

CREATE TABLE IF NOT EXISTS correction_requests (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    shop_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    original_entry_id INTEGER NOT NULL,
    reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (shop_id, customer_id, original_entry_id)
        REFERENCES ledger_entries(shop_id, customer_id, id)
) STRICT;

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY CHECK (id > 0),
    shop_id INTEGER NOT NULL,
    customer_id INTEGER NOT NULL,
    ledger_entry_id INTEGER NOT NULL UNIQUE,
    issued_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (shop_id, customer_id, ledger_entry_id)
        REFERENCES ledger_entries(shop_id, customer_id, id)
) STRICT;

CREATE TRIGGER IF NOT EXISTS ledger_entries_no_update
BEFORE UPDATE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'Ledger entries are append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_entries_no_delete
BEFORE DELETE ON ledger_entries
BEGIN
    SELECT RAISE(ABORT, 'Ledger entries are append-only');
END;

CREATE TRIGGER IF NOT EXISTS ledger_entries_no_replace
BEFORE INSERT ON ledger_entries
WHEN EXISTS (SELECT 1 FROM ledger_entries WHERE id = NEW.id)
BEGIN
    SELECT RAISE(ABORT, 'Ledger entries are append-only');
END;

CREATE TRIGGER IF NOT EXISTS transaction_batches_no_update
BEFORE UPDATE ON transaction_batches
BEGIN
    SELECT RAISE(ABORT, 'Transaction batches are immutable');
END;

CREATE TRIGGER IF NOT EXISTS transaction_batches_no_delete
BEFORE DELETE ON transaction_batches
BEGIN
    SELECT RAISE(ABORT, 'Transaction batches are immutable');
END;

CREATE TRIGGER IF NOT EXISTS transaction_batches_no_replace
BEFORE INSERT ON transaction_batches
WHEN EXISTS (
    SELECT 1 FROM transaction_batches WHERE shop_id = NEW.shop_id AND id = NEW.id
)
BEGIN
    SELECT RAISE(ABORT, 'Transaction batches are immutable');
END;

INSERT INTO shops (id, name) VALUES (1, 'Kirana Shop') ON CONFLICT(id) DO NOTHING;
