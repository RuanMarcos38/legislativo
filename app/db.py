import sqlite3, json, hashlib, os
from pathlib import Path
from datetime import datetime, timezone
ROOT=Path(__file__).resolve().parent.parent
def now(): return datetime.now(timezone.utc).isoformat()
class Connection(sqlite3.Connection):
    def __exit__(self,kind,value,trace):
        try: return super().__exit__(kind,value,trace)
        finally: self.close()
def connect(path=None):
    path=Path(path or os.environ.get("DATABASE_PATH",ROOT/"data"/"observatorio.db"))
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30,factory=Connection)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    for migration in sorted((ROOT/"migrations").glob("*.sql")):
        db.executescript(migration.read_text(encoding="utf8"))
    return db
def upsert(db,source,kind,eid,url,raw,data):
    key=f"{source}:{kind}:{eid}"
    body=json.dumps(raw,sort_keys=True,ensure_ascii=False)
    digest=hashlib.sha256(body.encode()).hexdigest()
    old=db.execute("SELECT hash FROM records WHERE id=?",(key,)).fetchone()
    stamp=now()
    db.execute("""INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(id) DO UPDATE SET url=excluded.url,raw=excluded.raw,data=excluded.data,
    hash=excluded.hash,collected_at=excluded.collected_at,
    updated_at=CASE WHEN records.hash<>excluded.hash THEN excluded.updated_at ELSE records.updated_at END""",
    (key,source,kind,str(eid),url,body,json.dumps(data,ensure_ascii=False),digest,stamp,stamp))
    if not old or old["hash"]!=digest:
        db.execute("INSERT INTO versions(record_id,hash,raw,collected_at) VALUES(?,?,?,?)",(key,digest,body,stamp))
        for w in db.execute("SELECT * FROM watches").fetchall():
            if w["query"].casefold() in json.dumps(data,ensure_ascii=False).casefold():
                db.execute("INSERT OR IGNORE INTO events(watch_id,record_id,hash,created_at) VALUES(?,?,?,?)",(w["id"],key,digest,stamp))
    return key
def serialize(row):
    item=dict(row); item["data"]=json.loads(item["data"]); item.pop("raw",None); return item
def search(db,kind="person",q="",source="",uf="",party="",year="",page=1,size=20):
    clauses=["kind=?"]; args=[kind]
    for field,value in [("source",source),("uf",uf),("party",party),("year",year)]:
        if value:
            clauses.append(("source" if field=="source" else f"json_extract(data,'$.{field}')")+"=?"); args.append(value)
    if q:
        clauses.append("instr(lower(json_extract(data,'$.search')),?)>0"); args.append(q.lower())
    where=" AND ".join(clauses)
    total=db.execute("SELECT COUNT(*) FROM records WHERE "+where,args).fetchone()[0]
    rows=db.execute("SELECT * FROM records WHERE "+where+" ORDER BY updated_at DESC,id LIMIT ? OFFSET ?",args+[size,(page-1)*size]).fetchall()
    return dict(total=total,page=page,size=size,items=[serialize(r) for r in rows])
