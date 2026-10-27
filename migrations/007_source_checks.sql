BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS scheduled_source_checks(
 source TEXT PRIMARY KEY,url TEXT NOT NULL,next_due REAL NOT NULL DEFAULT 0,
 lease_token TEXT,lease_until REAL,checked_at TEXT,last_success TEXT,status TEXT NOT NULL DEFAULT 'pending',
 etag TEXT,modified TEXT,failures INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO schema_versions VALUES(7);
COMMIT;
