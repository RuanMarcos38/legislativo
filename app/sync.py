import argparse
from .db import connect
from .connectors import sync
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--dataset",choices=["camara_people","senado_people","camara_proposals","camara_votes","all"],default="all"); p.add_argument("--max-pages",type=int,default=5); p.add_argument("--year",type=int)
    a=p.parse_args()
    if not 1<=a.max_pages<=100: p.error("--max-pages deve estar entre 1 e 100")
    datasets=["camara_people","senado_people","camara_proposals","camara_votes"] if a.dataset=="all" else [a.dataset]
    failed=False
    with connect() as db:
        for dataset in datasets:
            try: print(dataset,sync(db,dataset,a.max_pages,a.year))
            except Exception as e:
                failed=True
                print(dataset,"FALHOU",type(e).__name__,str(e)[:300])
    if failed: raise SystemExit(1)
