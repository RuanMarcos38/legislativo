"""Small official-series collector on the existing SQLite/worker architecture."""
import gzip,hashlib,json,time,uuid,urllib.request,urllib.parse,threading
from datetime import date,datetime,timedelta
from decimal import Decimal
from .db import connect,now
from .economic_catalog import CATALOG,BY_ID
from .calculations import number,text,change

INTERVAL=600
ALLOWED={'servicodados.ibge.gov.br','api.bcb.gov.br'}

def fetch(url):
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            validate_url(newurl)
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    validate_url(url)
    req=urllib.request.Request(url,headers={'Accept':'application/json','User-Agent':'ObservatorioLegislativo/1.0'})
    with urllib.request.build_opener(Redirect).open(req,timeout=30) as r:
        body=r.read(8_000_001)
        if len(body)>8_000_000:raise ValueError('Resposta excede limite')
    if body[:2]==b'\x1f\x8b':
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(body)) as z:body=z.read(8_000_001)
    if len(body)>8_000_000:raise ValueError('Resposta excede limite')
    return json.loads(body.decode('utf-8-sig'),parse_float=Decimal)

def validate_url(url):
    p=urllib.parse.urlsplit(url)
    if p.scheme!='https' or p.hostname not in ALLOWED or p.username or p.password or p.port not in (None,443):raise ValueError('Fonte não autorizada')

def source_url(item,today=None):
    today=today or date.today()
    if item['connector']=='bcb':
        start=date(today.year-1,1,1)
        return item['url']+'?'+urllib.parse.urlencode(dict(formato='json',dataInicial=start.strftime('%d/%m/%Y'),dataFinal=today.strftime('%d/%m/%Y')))
    return item['url']

def parse(item,payload):
    out={}
    if item['connector']=='bcb':
        if not isinstance(payload,list):raise ValueError('Contrato BCB alterado')
        for row in payload:
            day=datetime.strptime(row['data'],'%d/%m/%Y').date()
            period=day.isoformat() if item['frequency']=='daily' else day.strftime('%Y-%m')
            if day>date.today():raise ValueError('Data futura')
            value=str(number(row['valor']))
            if period in out and out[period]!=value:raise ValueError('Observação duplicada divergente')
            out[period]=value
    else:
        if not isinstance(payload,list) or len(payload)!=1:raise ValueError('Contrato IBGE alterado')
        doc=payload[0]
        expected=item['url'].split('/variaveis/')[1].split('?')[0]
        if str(doc['id'])!=expected:raise ValueError('Variável diferente')
        results=doc['resultados']
        if len(results)!=1 or len(results[0]['series'])!=1:raise ValueError('Agregação ambígua')
        series=results[0]['series'][0]
        if str(series['localidade']['id'])!='1':raise ValueError('Localidade diferente')
        for raw,v in series['serie'].items():
            if v in ('...','..','-','X','X ',''):continue
            if item['frequency']=='annual':
                if len(raw)!=4:raise ValueError('Período anual inválido')
                period=raw
            elif item['frequency']=='quarterly':
                year,q=int(raw[:4]),int(raw[4:])
                if len(raw)!=6 or not 1<=q<=4:raise ValueError('Trimestre inválido')
                period=f'{year}-Q{q}'
            else:
                if len(raw)!=6:raise ValueError('Período mensal inválido')
                date(int(raw[:4]),int(raw[4:]),1);period=raw[:4]+'-'+raw[4:]
            out[period]=str(number(v))
    if not out:raise ValueError('Resposta sem observações válidas')
    if len(out)>20000:raise ValueError('Série excessiva')
    return sorted(out.items())

def seed(db):
    for item in CATALOG:
        if item['connector']:db.execute('INSERT OR IGNORE INTO economic_jobs(indicator) VALUES(?)',(item['id'],))
    for item in CATALOG:
        if item['connector']=='bcb':
            for year in range(1995,date.today().year-1):
                db.execute('INSERT OR IGNORE INTO economic_backfill_jobs(indicator,year) VALUES(?,?)',(item['id'],year))
    db.commit()

def store_rows(db,item,rows,url,finished):
    changed=0
    for period,value in rows:
        digest=hashlib.sha256((value+'|'+item['unit']).encode()).hexdigest()
        old=db.execute('SELECT hash FROM economic_observations WHERE indicator=? AND period=?',(item['id'],period)).fetchone()
        changed+=int(not old or old[0]!=digest)
        vals=(item['id'],period,value,item['unit'],url,None,finished,digest)
        db.execute('INSERT INTO economic_observations VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(indicator,period) DO UPDATE SET value=excluded.value,unit=excluded.unit,source_url=excluded.source_url,collected_at=excluded.collected_at,hash=excluded.hash',vals)
        db.execute('INSERT OR IGNORE INTO economic_revisions(indicator,period,value,unit,source_url,published_at,collected_at,hash) VALUES(?,?,?,?,?,?,?,?)',vals)
    return changed

def step(db,fetcher=fetch,stamp=None):
    stamp=time.time() if stamp is None else stamp
    db.execute('BEGIN IMMEDIATE')
    r=db.execute("SELECT * FROM economic_jobs WHERE (state IN ('pending','idle','retry') AND next_due<=?) OR (state='running' AND lease_until<?) ORDER BY COALESCE(last_attempt,''),indicator LIMIT 1",(stamp,stamp)).fetchone()
    if not r:db.commit();return False
    job=dict(r);token=uuid.uuid4().hex;started=now();clock=time.monotonic()
    db.execute("UPDATE economic_jobs SET state='running',lease_token=?,lease_until=?,last_attempt=? WHERE indicator=?",(token,stamp+180,started,job['indicator']));db.commit()
    item=BY_ID[job['indicator']];url=source_url(item);changed=0
    try:
        rows=parse(item,fetcher(url));finished=now()
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT lease_token FROM economic_jobs WHERE indicator=?',(item['id'],)).fetchone()[0]!=token:db.rollback();return True
        changed=store_rows(db,item,rows,url,finished)
        db.execute("UPDATE economic_jobs SET state='idle',next_due=?,lease_token=NULL,lease_until=NULL,last_success=?,failures=0,last_count=?,error_code=NULL WHERE indicator=?",(time.time()+INTERVAL,finished,len(rows),item['id']))
        db.execute('INSERT INTO economic_runs(indicator,started_at,finished_at,status,received,changed,duration_ms) VALUES(?,?,?,?,?,?,?)',(item['id'],started,finished,'success',len(rows),changed,int((time.monotonic()-clock)*1000)));db.commit()
    except Exception as exc:
        db.rollback();code='source_unavailable' if isinstance(exc,(OSError,TimeoutError)) else 'invalid_response'
        failures=job['failures']+1
        db.execute("UPDATE economic_jobs SET state='retry',failures=?,next_due=?,error_code=?,lease_token=NULL,lease_until=NULL WHERE indicator=? AND lease_token=?",(failures,time.time()+min(INTERVAL,30*2**min(failures,5)),code,item['id'],token))
        db.execute('INSERT INTO economic_runs(indicator,started_at,finished_at,status,received,changed,duration_ms,error_code) VALUES(?,?,?,?,?,?,?,?)',(item['id'],started,now(),'failed',0,0,int((time.monotonic()-clock)*1000),code));db.commit()
    return True

def step_history(db,fetcher=fetch,stamp=None):
    stamp=time.time() if stamp is None else stamp
    db.execute('BEGIN IMMEDIATE')
    row=db.execute("SELECT * FROM economic_backfill_jobs WHERE (state IN ('pending','retry') AND next_due<=?) OR (state='running' AND lease_until<?) ORDER BY year DESC,next_due,indicator LIMIT 1",(stamp,stamp)).fetchone()
    if not row:db.commit();return False
    row=dict(row);token=uuid.uuid4().hex;item=BY_ID[row['indicator']]
    db.execute("UPDATE economic_backfill_jobs SET state='running',lease_token=?,lease_until=? WHERE indicator=? AND year=?",(token,stamp+120,row['indicator'],row['year']));db.commit()
    url=item['url']+'?'+urllib.parse.urlencode(dict(formato='json',dataInicial=f"01/01/{row['year']}",dataFinal=f"31/12/{row['year']}"))
    try:
        payload=fetcher(url);rows=parse(item,payload) if payload else []
        db.execute('BEGIN IMMEDIATE')
        current=db.execute('SELECT lease_token FROM economic_backfill_jobs WHERE indicator=? AND year=?',(row['indicator'],row['year'])).fetchone()
        if current[0]!=token:db.rollback();return True
        store_rows(db,item,rows,url,now())
        db.execute("UPDATE economic_backfill_jobs SET state='complete',lease_token=NULL,lease_until=NULL,last_success=?,error_code=NULL WHERE indicator=? AND year=?",(now(),row['indicator'],row['year']));db.commit()
    except Exception:
        db.rollback();db.execute("UPDATE economic_backfill_jobs SET state='retry',failures=failures+1,next_due=?,lease_token=NULL,lease_until=NULL,error_code='source_unavailable' WHERE indicator=? AND year=? AND lease_token=?",(stamp+min(86400,600*2**min(row['failures'],7)),row['indicator'],row['year'],token));db.commit()
    return True

def snapshot(db,params=None,technical=False):
    params=params or {};start=params.get('start','');end=params.get('end','');selected=params.get('indicator','')
    if selected and selected not in BY_ID:raise ValueError('Indicador inválido')
    for v in (start,end):
        if v:date.fromisoformat(v)
    if start and end and start>end:raise ValueError('Período inválido')
    items=[]
    for definition in CATALOG:
        if selected and definition['id']!=selected:continue
        item=dict(definition)
        rows=[dict(r) for r in db.execute('SELECT period,value,unit,source_url,published_at,collected_at,hash FROM economic_observations WHERE indicator=? ORDER BY period',(item['id'],))]
        rows=[r for r in rows if (not start or period_bounds(r['period'])[0]>=start) and (not end or period_bounds(r['period'])[1]<=end)]
        job=db.execute('SELECT * FROM economic_jobs WHERE indicator=?',(item['id'],)).fetchone()
        last=rows[-1] if rows else None;comparison=change(rows[-1]['value'],rows[-2]['value'],item['kind']=='rate') if len(rows)>1 else None
        checked=job['last_attempt'] if job else None
        fresh=bool(job and job['state']!='retry' and job['last_success'] and time.time()-datetime.fromisoformat(job['last_success']).timestamp()<INTERVAL*2)
        item.update(observations=rows,latest=last,previous=rows[-2] if len(rows)>1 else None,change=comparison,
          last_checked=checked,last_success=job['last_success'] if job else None,
          status='unavailable' if not last else 'available' if fresh else 'stale',
          source_status='unavailable' if not job else 'retry' if job['state']=='retry' else 'available' if fresh else 'not_confirmed',
          publication_note='Data de publicação não informada por esta resposta da API. Competência e consulta são campos distintos.')
        if technical:item['job']=dict(job) if job else None
        items.append(item)
    revision=db.execute('SELECT MAX(id) FROM economic_revisions').fetchone()[0]
    return dict(items=items,interval_seconds=INTERVAL,timezone='America/Sao_Paulo',revision=revision,
      generated_at=now(),methodology='Séries nacionais oficiais. Consultas a cada dez minutos não significam novas publicações. Sinal neutro: variação não é avaliação de governo. Histórico disponível pode ter lacunas.',
      history_states={r['state']:r['n'] for r in db.execute('SELECT state,COUNT(*) n FROM economic_backfill_jobs GROUP BY state')},
      runs=[dict(r) for r in db.execute('SELECT * FROM economic_runs ORDER BY id DESC LIMIT 50')] if technical else [])

def period_bounds(period):
    import calendar
    if '-Q' in period:
        year,q=map(int,period.split('-Q'));m=q*3
        return f'{year}-{m-2:02}-01',f'{year}-{m:02}-{calendar.monthrange(year,m)[1]}'
    if len(period)==4:return period+'-01-01',period+'-12-31'
    if len(period)==7:
        y,m=map(int,period.split('-'));return period+'-01',period+f'-{calendar.monthrange(y,m)[1]}'
    date.fromisoformat(period);return period,period

def revisions(db,params):
    key=params.get('indicator','');period=params.get('period','')
    if key not in BY_ID or len(period)>10:raise ValueError('Seleção inválida')
    first,last=period_bounds(period);date.fromisoformat(first);date.fromisoformat(last)
    rows=[dict(r) for r in db.execute('SELECT value,unit,source_url,published_at,collected_at,hash FROM economic_revisions WHERE indicator=? AND period=? ORDER BY id DESC LIMIT 1001',(key,period))]
    return dict(indicator=key,period=period,items=rows[:1000],truncated=len(rows)>1000,
      note='Versões detectadas pelas consultas desta ferramenta. Não representa todo o histórico de revisões anterior ao início da coleta. Data de consulta não é data de publicação oficial.')

def run(stop=None):
    stop=stop or threading.Event()
    while not stop.is_set():
        try:
            with connect() as db:
                seed(db);busy=step(db)
                if not busy:busy=step_history(db)
        except Exception:busy=False
        stop.wait(2 if busy else 15)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int);a=p.parse_args()
    if a.steps is None:run()
    else:
        with connect() as db:
            seed(db)
            for _ in range(a.steps):
                if not step(db):break
