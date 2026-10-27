-- Covering dictionaries resolve Unicode text once, before querying the ledger.
CREATE INDEX IF NOT EXISTS financial_name_lookup ON parliamentary_expenses(person_name,person_id);
CREATE INDEX IF NOT EXISTS financial_supplier_lookup ON parliamentary_expenses(supplier,year,month);
INSERT OR IGNORE INTO schema_versions VALUES(5);
