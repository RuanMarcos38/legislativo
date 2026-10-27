BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS economic_backfill_jobs(
 indicator TEXT NOT NULL,year INTEGER NOT NULL,state TEXT NOT NULL DEFAULT 'pending',
 next_due REAL NOT NULL DEFAULT 0,lease_token TEXT,lease_until REAL,failures INTEGER NOT NULL DEFAULT 0,
 last_success TEXT,error_code TEXT,PRIMARY KEY(indicator,year));
INSERT OR IGNORE INTO schema_versions VALUES(8);
COMMIT;
