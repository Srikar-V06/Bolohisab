CREATE INDEX IF NOT EXISTS ledger_entries_history
    ON ledger_entries(shop_id, customer_id, created_at DESC, id DESC);
