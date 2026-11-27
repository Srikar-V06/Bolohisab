ALTER TABLE ledger_entries ADD COLUMN payment_method TEXT
    CHECK (payment_method IS NULL OR (type = 'PAYMENT' AND payment_method IN ('CASH', 'UPI')));

ALTER TABLE receipts ADD COLUMN language TEXT NOT NULL DEFAULT 'hi-IN'
    CHECK (language IN ('hi-IN', 'en-IN'));
ALTER TABLE receipts ADD COLUMN share_token TEXT;
ALTER TABLE receipts ADD COLUMN sent_at TEXT;
CREATE UNIQUE INDEX receipts_share_token ON receipts(share_token);
