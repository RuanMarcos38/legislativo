-- Additive migration: existing records, users, tenants and monitors are preserved.
CREATE TABLE IF NOT EXISTS sync_streams(
 key TEXT PRIMARY KEY, source TEXT NOT NULL, mode TEXT NOT NULL, target TEXT,
 initial_url TEXT NOT NULL, next_url TEXT, state TEXT NOT NULL DEFAULT 'pending',
 priority INTEGER NOT NULL DEFAULT 50, refresh_seconds INTEGER NOT NULL DEFAULT 21600,
 next_due REAL NOT NULL DEFAULT 0, lease_until REAL, last_attempt REAL,
 cycle INTEGER NOT NULL DEFAULT 1,pages INTEGER NOT NULL DEFAULT 0,items INTEGER NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0,last_success TEXT,completed_at TEXT,error TEXT,
 scope TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS sync_stream_due ON sync_streams(state,next_due,priority);
CREATE TABLE IF NOT EXISTS sync_pages(stream_key TEXT REFERENCES sync_streams(key),cycle INTEGER,url TEXT,
 collected_at TEXT,PRIMARY KEY(stream_key,cycle,url));
CREATE TABLE IF NOT EXISTS authorships(
 proposal_id TEXT NOT NULL REFERENCES records(id),person_id TEXT NOT NULL,
 relation TEXT NOT NULL,source_url TEXT NOT NULL,collected_at TEXT NOT NULL,
 PRIMARY KEY(proposal_id,person_id));
CREATE INDEX IF NOT EXISTS authorship_person ON authorships(person_id,proposal_id);
CREATE TABLE IF NOT EXISTS proposal_facts(
 proposal_id TEXT PRIMARY KEY REFERENCES records(id),source TEXT NOT NULL,type TEXT,
 presented_at TEXT,status TEXT,urn TEXT,norm_reported INTEGER NOT NULL DEFAULT 0,
 detail_checked_at TEXT,history_checked_at TEXT,authors_checked_at TEXT);
CREATE TABLE IF NOT EXISTS approval_evidence(
 proposal_id TEXT NOT NULL REFERENCES records(id),event_key TEXT NOT NULL,code TEXT NOT NULL,
 description TEXT NOT NULL,event_date TEXT,body TEXT NOT NULL,source_url TEXT NOT NULL,
 collected_at TEXT NOT NULL,PRIMARY KEY(proposal_id,event_key));
CREATE TABLE IF NOT EXISTS sync_heartbeats(worker TEXT PRIMARY KEY,seen_at REAL NOT NULL,error TEXT);
CREATE TABLE IF NOT EXISTS nominal_votes(
 vote_id TEXT NOT NULL REFERENCES records(id),person_id TEXT NOT NULL,choice TEXT NOT NULL,
 vote_date TEXT,source_url TEXT NOT NULL,collected_at TEXT NOT NULL,PRIMARY KEY(vote_id,person_id));
CREATE INDEX IF NOT EXISTS nominal_vote_person ON nominal_votes(person_id,vote_date);
INSERT OR IGNORE INTO schema_versions VALUES(3);
