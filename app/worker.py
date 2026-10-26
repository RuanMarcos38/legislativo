import time
from .db import connect
from .connectors import sync
def claim(db,stamp=None):
    stamp=stamp or time.time()
    db.execute("BEGIN IMMEDIATE")
    row=db.execute("SELECT * FROM jobs WHERE (status='pending' AND available_at<=?) OR (status='running' AND lease_until<?) ORDER BY id LIMIT 1",(stamp,stamp)).fetchone()
    if row:
        db.execute("UPDATE jobs SET status='running',attempts=attempts+1,lease_until=? WHERE id=?",(stamp+1800,row["id"]))
    db.commit()
    return dict(row) if row else None
def tick(db):
    job=claim(db)
    if not job: return False
    try:
        sync(db,job["dataset"])
        db.execute("UPDATE jobs SET status='done',lease_until=NULL WHERE id=?",(job["id"],))
    except Exception as e:
        attempts=job["attempts"]+1
        db.execute("UPDATE jobs SET status=?,available_at=?,lease_until=NULL,error=? WHERE id=?",("dead" if attempts>=5 else "pending",time.time()+min(3600,2**attempts*30),str(e)[:300],job["id"]))
    db.commit(); return True
def main():
    import threading
    from .automatic import run
    threading.Thread(target=run,daemon=True).start()
    db=connect()
    try:
        while True:
            if not tick(db): time.sleep(3)
    finally:db.close()

if __name__=="__main__":main()
