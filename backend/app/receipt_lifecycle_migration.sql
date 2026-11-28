ALTER TABLE receipts ADD COLUMN confirmed_at TEXT;

ALTER TABLE correction_requests ADD COLUMN claimed_amount_paise INTEGER;
ALTER TABLE correction_requests ADD COLUMN reviewed_by TEXT
    CHECK (reviewed_by IS NULL OR length(trim(reviewed_by)) BETWEEN 1 AND 120);
ALTER TABLE correction_requests ADD COLUMN reviewed_at TEXT;
ALTER TABLE correction_requests ADD COLUMN adjustment_entry_id INTEGER
    REFERENCES ledger_entries(id);

-- Legacy requests had no claimed amount. Keep their history without inventing an amount.
CREATE UNIQUE INDEX receipt_dispute_entry ON correction_requests(original_entry_id)
    WHERE claimed_amount_paise IS NOT NULL;
CREATE UNIQUE INDEX receipt_dispute_adjustment ON correction_requests(adjustment_entry_id)
    WHERE adjustment_entry_id IS NOT NULL;

CREATE TRIGGER receipt_dispute_review_integrity
BEFORE UPDATE ON correction_requests
WHEN NEW.claimed_amount_paise IS NOT NULL AND (
    OLD.status <> 'PENDING'
    OR NEW.status NOT IN ('APPROVED', 'REJECTED')
    OR NEW.reviewed_by IS NULL OR NEW.reviewed_at IS NULL
    OR (NEW.status = 'REJECTED' AND NEW.adjustment_entry_id IS NOT NULL)
    OR (NEW.status = 'APPROVED' AND NOT EXISTS (
        SELECT 1 FROM ledger_entries AS adjustment
        WHERE adjustment.id = NEW.adjustment_entry_id AND adjustment.shop_id = NEW.shop_id
          AND adjustment.customer_id = NEW.customer_id AND adjustment.corrects_entry_id = NEW.original_entry_id
    ))
)
BEGIN
    SELECT RAISE(ABORT, 'Invalid receipt dispute review');
END;
