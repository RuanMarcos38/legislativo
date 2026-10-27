"""Ten-minute availability checks. Bulk history remains in resumable collectors."""
import time,uuid,threading,urllib.request,urllib.error
from datetime import date
from .db import connect,now
from . import automatic,financial

def sources():
    year=date.today().year
    return {'camara':automatic.CAMARA+'deputados?itens=1','senado':automatic.SENADO+'senador/lista/atual.json',
      'camara_ceap':f'https://www.camara.leg.br/cotas/Ano-{year}.csv.zip',
      'senado_ceaps':financial.SENADO+str(year),
      'alesc_office':f'https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/csv/{year}',
      'alesc_travel':f'https://transparencia.alesc.sc.gov.br/diarias/csv/{year}'}

def check(url,headers=None):
    # URL comes only from sources(), never from the client. Fixed-host redirect policy.
    allowed={'dadosabertos.camara.leg.br','legis.senado.leg.br','www.camara.leg.br','adm.senado.gov.br','transparencia.alesc.sc.gov.br'}
    from urllib.parse import urlsplit
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,response,newurl):
            p=urlsplit(newurl)
            if p.scheme!='https' or p.hostname not in allowed or p.username or p.password:raise ValueError('Redirecionamento não autorizado')
            return super().redirect_request(req,fp,code,msg,response,newurl)
    request_headers={'User-Agent':'ObservatorioLegislativo/1.0',**(headers or {})}
    opener=urllib.request.build_opener(Redirect)
    try:
        with opener.open(urllib.request.Request(url,headers=request_headers,method='HEAD'),timeout=20) as r:return dict(etag=r.headers.get('ETag'),modified=r.headers.get('Last-Modified'),status=r.status)
    except urllib.error.HTTPError as ex:
        if ex.code==304:return dict(status=304)
        if ex.code!=405:raise
    with opener.open(urllib.request.Request(url,headers=request_headers),timeout=20) as r:
        r.read(1024);return dict(etag=r.headers.get('ETag'),modified=r.headers.get('Last-Modified'),status=r.status)

def seed(db):
    for row in financial.SOURCES:db.execute("INSERT OR IGNORE INTO financial_sources VALUES(?,?,?,?,?,?,?)",row)
    for key,url in sources().items():db.execute('INSERT INTO scheduled_source_checks(source,url) VALUES(?,?) ON CONFLICT(source) DO UPDATE SET url=excluded.url',(key,url))
    db.commit()

def step(db,fetcher=check,stamp=None):
    stamp=time.time() if stamp is None else stamp;db.execute('BEGIN IMMEDIATE')
    row=db.execute('SELECT * FROM scheduled_source_checks WHERE next_due<=? AND (lease_until IS NULL OR lease_until<?) ORDER BY next_due,source LIMIT 1',(stamp,stamp)).fetchone()
    if not row:db.commit();return False
    row=dict(row);token=uuid.uuid4().hex
    db.execute('UPDATE scheduled_source_checks SET lease_token=?,lease_until=? WHERE source=?',(token,stamp+120,row['source']));db.commit()
    try:
        h={}
        if row['etag']:h['If-None-Match']=row['etag']
        if row['modified']:h['If-Modified-Since']=row['modified']
        result=fetcher(row['url'],h)
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT lease_token FROM scheduled_source_checks WHERE source=?',(row['source'],)).fetchone()[0]!=token:db.rollback();return True
        unchanged=result['status']==304 or bool(row['etag'] and row['etag']==result.get('etag')) or bool(not row['etag'] and row['modified'] and row['modified']==result.get('modified'))
        if not unchanged and row['source'] not in {'camara','senado'}:
            # Reuse the existing source/year job. No duplicate imports or data deletion.
            key=financial.enqueue(db,row['source'],date.today().year)
            db.execute("UPDATE financial_sync_jobs SET next_due=0,state='pending' WHERE key=? AND state IN ('complete','failed')",(key,))
        db.execute("UPDATE scheduled_source_checks SET checked_at=?,last_success=?,status='available',next_due=?,lease_token=NULL,lease_until=NULL,etag=COALESCE(?,etag),modified=COALESCE(?,modified),failures=0 WHERE source=?",(now(),now(),stamp+600,result.get('etag'),result.get('modified'),row['source']));db.commit()
    except Exception:
        db.rollback();db.execute("UPDATE scheduled_source_checks SET checked_at=?,status='unavailable',next_due=?,lease_token=NULL,lease_until=NULL,failures=failures+1 WHERE source=? AND lease_token=?",(now(),stamp+min(600,30*2**min(row['failures']+1,5)),row['source'],token));db.commit()
    return True

def status(db,technical=False):
    columns='*' if technical else 'source,checked_at,last_success,status'
    return dict(interval_seconds=600,sources=[dict(r) for r in db.execute('SELECT '+columns+' FROM scheduled_source_checks ORDER BY source')],
      note='A verificação de disponibilidade não comprova que todos os registros da fonte já foram importados. O histórico é percorrido por etapas.')

def run(stop=None):
    stop=stop or threading.Event()
    while not stop.is_set():
        try:
            with connect() as db:seed(db);busy=step(db)
        except Exception:busy=False
        stop.wait(2 if busy else 15)
