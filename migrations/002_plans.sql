CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,name TEXT NOT NULL,watch_limit INTEGER CHECK(watch_limit>=0));
INSERT OR IGNORE INTO plans VALUES('free','Gratuito',5),('professional','Profissional',50),('team','Equipes',250),('enterprise','Corporativo',NULL);
CREATE TABLE IF NOT EXISTS tenant_plans(tenant_id TEXT PRIMARY KEY REFERENCES tenants(id),plan_id TEXT NOT NULL REFERENCES plans(id),updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscriptions(id TEXT PRIMARY KEY,tenant_id TEXT NOT NULL REFERENCES tenants(id),provider TEXT NOT NULL,external_id TEXT, status TEXT NOT NULL CHECK(status IN ('pending','active','canceled','past_due')),updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit_log(id INTEGER PRIMARY KEY,tenant_id TEXT REFERENCES tenants(id),user_id TEXT REFERENCES users(id),action TEXT NOT NULL,created_at TEXT NOT NULL);
INSERT OR IGNORE INTO schema_versions VALUES(2);
