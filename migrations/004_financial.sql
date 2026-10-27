-- Additive only. Exact money is stored as INTEGER centavos, never SQLite REAL.
CREATE TABLE IF NOT EXISTS financial_sources(
 id TEXT PRIMARY KEY,name TEXT NOT NULL,institution TEXT NOT NULL,url TEXT NOT NULL,
 status TEXT NOT NULL,note TEXT NOT NULL,periodicity TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS financial_sync_jobs(
 key TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES financial_sources(id),year INTEGER NOT NULL,
 target TEXT NOT NULL DEFAULT '',state TEXT NOT NULL DEFAULT 'pending',cursor TEXT,
 attempts INTEGER NOT NULL DEFAULT 0,next_due REAL NOT NULL DEFAULT 0,lease_until REAL,
 lease_token TEXT,last_success TEXT,error TEXT,imported INTEGER NOT NULL DEFAULT 0,
 refresh_seconds INTEGER NOT NULL DEFAULT 86400,UNIQUE(source_id,year,target));
CREATE TABLE IF NOT EXISTS financial_import_batches(
 id INTEGER PRIMARY KEY,job_key TEXT NOT NULL REFERENCES financial_sync_jobs(key),
 source_url TEXT NOT NULL,response_sha256 TEXT NOT NULL,source_updated_at TEXT,
 collected_at TEXT NOT NULL,row_count INTEGER NOT NULL,state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parliamentary_expenses(
 id TEXT PRIMARY KEY,source_id TEXT NOT NULL REFERENCES financial_sources(id),official_id TEXT NOT NULL,
 person_id TEXT REFERENCES records(id),person_name TEXT NOT NULL,institution TEXT NOT NULL,
 mandate TEXT,year INTEGER NOT NULL,month INTEGER NOT NULL CHECK(month BETWEEN 1 AND 12),
 document_date TEXT,expense_date TEXT,payment_date TEXT,description TEXT NOT NULL,
 category TEXT NOT NULL,component TEXT NOT NULL,nature TEXT NOT NULL,
 amount_cents INTEGER CHECK(amount_cents IS NULL OR typeof(amount_cents)='integer'),
 original_amount TEXT,gross_cents INTEGER CHECK(gross_cents IS NULL OR typeof(gross_cents)='integer'),
 disallowed_cents INTEGER CHECK(disallowed_cents IS NULL OR typeof(disallowed_cents)='integer'),
 currency TEXT NOT NULL DEFAULT 'BRL',supplier TEXT,document_number TEXT,
 source_url TEXT NOT NULL,receipt_url TEXT,verification TEXT NOT NULL,verification_note TEXT,
 raw TEXT NOT NULL,hash TEXT NOT NULL,collected_at TEXT NOT NULL,source_updated_at TEXT,
 batch_id INTEGER REFERENCES financial_import_batches(id),UNIQUE(source_id,official_id));
CREATE INDEX IF NOT EXISTS financial_person_period ON parliamentary_expenses(person_id,year,month);
CREATE INDEX IF NOT EXISTS financial_source_period ON parliamentary_expenses(source_id,year,component,nature);
CREATE INDEX IF NOT EXISTS financial_period ON parliamentary_expenses(year,month,verification);
CREATE INDEX IF NOT EXISTS financial_categories ON parliamentary_expenses(category);
CREATE TABLE IF NOT EXISTS financial_audit_logs(
 id INTEGER PRIMARY KEY,expense_id TEXT NOT NULL REFERENCES parliamentary_expenses(id),
 hash TEXT NOT NULL,raw TEXT NOT NULL,amount_cents INTEGER,verification TEXT NOT NULL,
 collected_at TEXT NOT NULL,batch_id INTEGER REFERENCES financial_import_batches(id));
CREATE INDEX IF NOT EXISTS financial_audit_entry ON financial_audit_logs(expense_id,hash);
CREATE TABLE IF NOT EXISTS financial_source_coverage(
 job_key TEXT PRIMARY KEY REFERENCES financial_sync_jobs(key),source_id TEXT NOT NULL,
 year INTEGER NOT NULL,target TEXT NOT NULL DEFAULT '',last_complete TEXT,
 observed_count INTEGER NOT NULL DEFAULT 0,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS financial_reconciliations(
 id INTEGER PRIMARY KEY,batch_id INTEGER REFERENCES financial_import_batches(id),
 expected_rows INTEGER NOT NULL,persisted_rows INTEGER NOT NULL,confirmed_rows INTEGER NOT NULL,
 pending_rows INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS parliamentary_amendments(
 id TEXT PRIMARY KEY,source_url TEXT NOT NULL,person_id TEXT REFERENCES records(id),
 author_code TEXT,author_name TEXT,year INTEGER,verification TEXT NOT NULL,raw TEXT NOT NULL,
 collected_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS amendment_financial_events(
 id TEXT PRIMARY KEY,amendment_id TEXT NOT NULL REFERENCES parliamentary_amendments(id),
 nature TEXT NOT NULL,amount_cents INTEGER CHECK(amount_cents IS NULL OR typeof(amount_cents)='integer'),
 original_amount TEXT,source_url TEXT NOT NULL,collected_at TEXT NOT NULL);
INSERT OR IGNORE INTO schema_versions VALUES(4);
