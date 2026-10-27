-- Additive only. Rollback: stop new collectors and restore previous code; keep these tables.
BEGIN IMMEDIATE;
CREATE TABLE IF NOT EXISTS economic_observations(
 indicator TEXT NOT NULL,period TEXT NOT NULL,value TEXT NOT NULL,unit TEXT NOT NULL,
 source_url TEXT NOT NULL,published_at TEXT,collected_at TEXT NOT NULL,hash TEXT NOT NULL,
 PRIMARY KEY(indicator,period));
CREATE TABLE IF NOT EXISTS economic_revisions(
 id INTEGER PRIMARY KEY,indicator TEXT NOT NULL,period TEXT NOT NULL,value TEXT NOT NULL,
 unit TEXT NOT NULL,source_url TEXT NOT NULL,published_at TEXT,collected_at TEXT NOT NULL,
 hash TEXT NOT NULL,UNIQUE(indicator,period,hash));
CREATE TABLE IF NOT EXISTS economic_jobs(
 indicator TEXT PRIMARY KEY,state TEXT NOT NULL DEFAULT 'pending',next_due REAL NOT NULL DEFAULT 0,
 lease_token TEXT,lease_until REAL,last_attempt TEXT,last_success TEXT,failures INTEGER NOT NULL DEFAULT 0,
 last_count INTEGER NOT NULL DEFAULT 0,error_code TEXT);
CREATE TABLE IF NOT EXISTS economic_runs(
 id INTEGER PRIMARY KEY,indicator TEXT NOT NULL,started_at TEXT NOT NULL,finished_at TEXT NOT NULL,
 status TEXT NOT NULL,received INTEGER NOT NULL,changed INTEGER NOT NULL,duration_ms INTEGER NOT NULL,error_code TEXT);
CREATE TABLE IF NOT EXISTS source_availability(
 source TEXT PRIMARY KEY,checked_at TEXT NOT NULL,status TEXT NOT NULL);
INSERT OR IGNORE INTO schema_versions VALUES(6);
COMMIT;
