-- Additive covering indexes for aggregate and paginated financial reads.
BEGIN IMMEDIATE;
CREATE INDEX IF NOT EXISTS financial_public_totals ON parliamentary_expenses(year,verification,component,nature,month,person_id,amount_cents);
CREATE INDEX IF NOT EXISTS financial_public_categories ON parliamentary_expenses(year,category);
CREATE INDEX IF NOT EXISTS financial_public_order ON parliamentary_expenses(year DESC,month DESC,id);
INSERT OR IGNORE INTO schema_versions VALUES(9);
COMMIT;
