"""Optional live verification. Writes only a report and source-backed documents."""
import json,sqlite3,tempfile
from pathlib import Path
from .db import connect,ROOT,now
from .connectors import detail
from .server import coverage
def verify():
    report={"verified_at":now(),"integrity":None,"sources":[],"documents":[],"backup":None}
    with connect() as db:
        report["integrity"]=db.execute("PRAGMA integrity_check").fetchone()[0]
        for source,kind,section in [("camara","person","detail"),("senado","person","detail"),("camara","proposal","tramitacoes"),("camara","vote","votos")]:
            row=db.execute("SELECT id FROM records WHERE source=? AND kind=? ORDER BY id LIMIT 1",(source,kind)).fetchone()
            if not row:
                report["documents"].append({"source":source,"kind":kind,"status":"no_records"});continue
            try:
                doc=detail(db,row["id"],section)
                report["documents"].append({"id":row["id"],"url":doc["url"],"section":section,"status":"received","keys":list(doc["payload"])})
            except Exception as exc:report["documents"].append({"id":row["id"],"status":"failed","error":type(exc).__name__+": "+str(exc)[:250]})
        report["sources"]=coverage(db)
        with tempfile.TemporaryDirectory() as directory:
            dest=sqlite3.connect(str(Path(directory)/"backup.db"));db.backup(dest)
            report["backup"]=dest.execute("PRAGMA integrity_check").fetchone()[0];dest.close()
    path=ROOT/"docs"/"live-verification.json"
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(report,ensure_ascii=True,indent=2))
    return report
if __name__=="__main__":
    r=verify()
    if r["integrity"]!="ok" or any(d["status"]!="received" for d in r["documents"]):raise SystemExit(1)
