"""Auditable public finance. Monetary arithmetic uses Decimal and integer centavos.

Public facts are shared, as existing records are. Sync mutation requires the existing
superadmin/CSRF gate. Never accept a URL, SQL expression or monetary value from HTTP.
"""
import csv,hashlib,io,json,os,re,threading,time,urllib.parse,urllib.request,uuid,zipfile,tempfile,sqlite3
from pathlib import Path
from collections import Counter
from datetime import date
from decimal import Decimal,InvalidOperation
from .db import connect,now,upsert

CAMARA='https://dadosabertos.camara.leg.br/api/v2/'
SENADO='https://adm.senado.gov.br/adm-dadosabertos/api/v1/senadores/despesas_ceaps/'
SOURCES=[
 ('camara_ceap','Cota parlamentar — Câmara','Câmara dos Deputados','https://www.camara.leg.br/cotas/','connected','Arquivo anual oficial e API individual. Valor líquido é débito na cota; não é limite disponível nem prova da data de pagamento.','Diária'),
 ('senado_ceaps','CEAPS — Senado','Senado Federal',SENADO,'connected','Web Service anual com identificador oficial do senador. Não informa mandato, data de pagamento ou comprovante digital em todos os registros.','Diária'),
 ('alesc_office','Gabinetes — ALESC','Assembleia Legislativa de Santa Catarina','https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/dados-abertos','partial','CSV sem identificador único de deputado/lançamento: registros institucionais pendentes, fora dos totais individuais. Série publicada desde 2011.','Diária'),
 ('alesc_travel','Diárias — ALESC','Assembleia Legislativa de Santa Catarina','https://transparencia.alesc.sc.gov.br/diarias/dados-abertos','partial','Diárias concedidas. Somente vínculo explícito Deputado; não comprova pagamento. Série publicada desde novembro de 2011.','Diária'),
 ('cgu_amendments','Emendas — CGU','Controladoria-Geral da União','https://api.portaldatransparencia.gov.br/','credentials_required','API exige chave-api-dados. Sem chave configurada e vínculo oficial entre códigos, valores não apurados. Emendas nunca compõem despesas pessoais.','Conforme fonte'),
 ('dou','Atos — Diário Oficial','Imprensa Nacional','https://inlabs.in.gov.br/acessar.php','credentials_required','Consulta assistida por link oficial. Ingestão INLABS depende de acesso e validação contextual. Ato não comprova pagamento.','Diária'),
 ('states','Demais Assembleias / CLDF','Casas estaduais','https://www.interlegis.leg.br/','not_integrated','26 outras instituições sem conector financeiro validado. Nenhuma cobertura nacional presumida.','Não aferida'),
 ('municipal','Câmaras municipais','Casas municipais','https://www.interlegis.leg.br/','not_integrated','Nenhum município integrado. Cadastro geográfico, portal, contrato e vínculo documental devem ser validados por instituição.','Não aferida')]
HOST_PATHS={
 'dadosabertos.camara.leg.br':('/api/v2/deputados/',),
 'www.camara.leg.br':('/cotas/',),
 'adm.senado.gov.br':('/adm-dadosabertos/api/v1/senadores/despesas_ceaps/',),
 'transparencia.alesc.sc.gov.br':('/gabinetes-parlamentares/csv/','/diarias/csv/'),
 'api.portaldatransparencia.gov.br':('/api-de-dados/emendas',)}
MISSING='VALOR NÃO DISPONIBILIZADO PELA FONTE OFICIAL'
PENDING='DADO PENDENTE DE VERIFICAÇÃO'

def dump(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,default=str,separators=(',',':'))

def cents(value,localized=False):
    if value is None or str(value).strip()=='':return None
    if isinstance(value,(float,bool)):raise ValueError('Use Decimal ou texto, nunca FLOAT')
    text=str(value).strip()
    if localized and ',' in text:text=text.replace('.','').replace(',','.')
    if not re.fullmatch(r'-?\d+(\.\d{1,2})?',text):raise ValueError('Formato monetário inválido')
    try:d=Decimal(text)*100
    except InvalidOperation:raise ValueError('Valor inválido')
    if not d.is_finite() or abs(d)>9_000_000_000_000_000:raise ValueError('Valor fora do limite')
    return int(d)

def money(value):
    if value is None:return None
    return ('-' if value<0 else '')+str(abs(value)//100)+'.'+str(abs(value)%100).zfill(2)

def validate_url(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme!='https' or u.hostname not in HOST_PATHS or u.username or u.password or u.port not in (None,443) or not u.path.startswith(HOST_PATHS.get(u.hostname,())):
        raise ValueError('URL fora do contrato financeiro autorizado')
    return url

def receipt_url(url):
    if not url:return None
    u=urllib.parse.urlsplit(str(url))
    if u.scheme!='https' or u.username or u.password or u.port not in (None,443):return None
    if u.hostname not in {'www.camara.leg.br','www.senado.leg.br','adm.senado.gov.br','transparencia.alesc.sc.gov.br','diarias.alesc.sc.gov.br'}:return None
    return str(url)

class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        # Credentials may never follow a cross-host redirect.
        if urllib.parse.urlsplit(newurl).hostname!=urllib.parse.urlsplit(req.full_url).hostname:raise ValueError('Redirecionamento entre fontes bloqueado')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def download(url):
    validate_url(url)
    headers={'User-Agent':'ObservatorioLegislativo/financeiro (dados publicos)'}
    if urllib.parse.urlsplit(url).hostname=='api.portaldatransparencia.gov.br':
        key=os.environ.get('CGU_API_KEY')
        if not key:raise PermissionError('Chave CGU não configurada')
        headers['chave-api-dados']=key
    with urllib.request.build_opener(Redirect()).open(urllib.request.Request(url,headers=headers),timeout=60) as r:
        body=r.read(96_000_001)
        if len(body)>96_000_000:raise ValueError('Resposta excede limite de segurança')
        return body,r.headers.get('Last-Modified')

def seed(db,today=None):
    today=today or date.today()
    for row in SOURCES:db.execute('INSERT OR IGNORE INTO financial_sources VALUES(?,?,?,?,?,?,?)',row)
    start=int(os.environ.get('FINANCIAL_START_YEAR','2008'))
    if not 2008<=start<=today.year:raise ValueError('Ano inicial financeiro inválido')
    for year in range(today.year,start-1,-1):
        for source in ('camara_ceap','senado_ceaps')+ (('alesc_office','alesc_travel') if year>=2011 else ()):
            enqueue(db,source,year)
    db.commit()

def enqueue(db,source,year,target=''):
    year=int(year)
    if not 2008<=year<=date.today().year:raise ValueError('Ano fora do escopo')
    if source not in {'camara_ceap','senado_ceaps','camara_api','alesc_office','alesc_travel'}:raise ValueError('Conector não validado')
    if source=='camara_api':
        if not re.fullmatch(r'camara:person:\d+',target):raise ValueError('Identidade inválida')
        if not db.execute("SELECT 1 FROM records WHERE id=? AND kind='person'",(target,)).fetchone():raise ValueError('Parlamentar não cadastrado')
        source_id='camara_ceap'
    else:source_id=source
    key=f'{source}:{year}:{target}'
    db.execute('INSERT OR IGNORE INTO financial_sync_jobs(key,source_id,year,target) VALUES(?,?,?,?)',(key,source_id,year,target))
    return key

def ensure_person(db,source,eid,name,raw,url,uf='',party=''):
    if not str(eid).isdigit():return None
    key=f'{source}:person:{eid}'
    if not db.execute('SELECT 1 FROM records WHERE id=?',(key,)).fetchone():
        upsert(db,source,'person',eid,url,{'id':str(eid),'name':name},dict(name=name,uf=uf,party=party,role='Identificado em registro financeiro; mandato não verificado',search=name.lower()))
    return key

def minimize(raw):
    # Financial source identifiers suffice; CPF and passenger names are unnecessary.
    return {k:v for k,v in raw.items() if k.lower() not in {'cpf','txtcnpjcpf','cpfcnpj','cnpjcpffornecedor','txtpassageiro'}}

def normalized(db,source,row,url):
    r=minimize(row); stamp=now()
    if source=='camara_ceap':
        bulk='ideDocumento' in row
        get=lambda a,b:row.get(a if bulk else b)
        eid=get('ideCadastro','_person_id');name=get('txNomeParlamentar','_person_name') or 'Identidade não informada'
        doc=get('ideDocumento','codDocumento')
        missing_doc=doc is None or str(doc)==''
        if missing_doc:doc='sem-documento:'+hashlib.sha256(dump(r).encode()).hexdigest()
        # A document has multiple accounting entries: document ID alone is NOT unique.
        parts=[eid or row.get('nuDeputadoId') or name,doc,get('numLote','codLote'),get('numRessarcimento','numRessarcimento'),get('numParcela','parcela'),get('numAno','ano'),get('numMes','mes'),row.get('datPagamentoRestituicao')]
        official=hashlib.sha256(dump([str(x) if x is not None else '' for x in parts]).encode()).hexdigest()
        person=ensure_person(db,'camara',eid,name,r,CAMARA+'deputados/'+str(eid),row.get('sgUF',''),row.get('sgPartido','')) if eid else None
        amount=get('vlrLiquido','valorLiquido');gross=get('vlrDocumento','valorDocumento');glosa=get('vlrGlosa','valorGlosa')
        ac,gc,dc=cents(amount),cents(gross),cents(glosa)
        category=get('txtDescricao','tipoDespesa') or 'Categoria não informada'
        rest=cents(row.get('vlrRestituicao'))
        status='confirmed';note='Valor líquido debitado na cota; data de pagamento não informada pela API.'
        if rest not in (None,0):status='pending';note='Restituição informada; vínculo com os demais lançamentos precisa de conciliação. Excluído dos totais.'
        if gc is not None and dc is not None and ac is not None and gc-dc!=ac:status='pending';note='Valor líquido diverge de documento menos glosa. Excluído dos totais.'
        if not person:status='pending';note='Despesa institucional sem atribuição individual. Excluída dos totais individuais.'
        if missing_doc:status='pending';note='Identificador do documento não disponibilizado. Lançamento preservado, fora dos totais até conciliação.'
        mandate=str(row['codLegislatura']) if bulk and row.get('codLegislatura') else None
        data=dict(official_id=official,person_id=person,person_name=name,institution='Câmara dos Deputados',mandate=mandate,year=int(get('numAno','ano')),month=int(get('numMes','mes')),document_date=get('datEmissao','dataDocumento'),expense_date=None,payment_date=None,description=category+((' · '+row['txtDescricaoEspecificacao']) if row.get('txtDescricaoEspecificacao') else ''),category=category,component='cota' if person else 'institucional',nature='ESTORNADO' if ac is not None and ac<0 else 'DEBITADO_COTA',amount_cents=ac,original_amount=None if amount is None else str(amount),gross_cents=gc,disallowed_cents=dc,supplier=get('txtFornecedor','nomeFornecedor'),document_number=get('txtNumero','numDocumento'),receipt_url=receipt_url(row.get('urlDocumento')),verification=status,verification_note=note)
    elif source=='senado_ceaps':
        if not str(row.get('id','')).isdigit() or not str(row.get('codSenador','')).isdigit():raise ValueError('Identificador Senado ausente')
        eid=str(row['codSenador']);name=row['nomeSenador'];ac=cents(row.get('valorReembolsado'))
        person=ensure_person(db,'senado',eid,name,r,'https://legis.senado.leg.br/dadosabertos/senador/'+eid+'.json')
        data=dict(official_id=str(row['id']),person_id=person,person_name=name,institution='Senado Federal',mandate=None,year=int(row['ano']),month=int(row['mes']),document_date=row.get('data'),expense_date=None,payment_date=None,description=row.get('detalhamento') or row.get('tipoDespesa') or 'Descrição não informada',category=row.get('tipoDespesa') or 'Categoria não informada',component='cota',nature='ESTORNADO' if ac is not None and ac<0 else 'REEMBOLSADO',amount_cents=ac,original_amount=None if row.get('valorReembolsado') is None else str(row['valorReembolsado']),gross_cents=None,disallowed_cents=None,supplier=row.get('fornecedor'),document_number=row.get('documento'),receipt_url=None,verification='confirmed',verification_note='Reembolso publicado no serviço CEAPS. Mandato e data do pagamento não informados neste conjunto.')
    elif source in {'alesc_travel','alesc_office'}:
        travel=source=='alesc_travel'
        source_date=row.get('Data' if travel else 'Data de Referência','')
        from datetime import datetime
        day=datetime.strptime(source_date,'%d/%m/%Y').date()
        name=row.get('Nome' if travel else 'Conta') or 'Institucional sem identificação'
        account=str(row.get('Conta',''))
        receipt=receipt_url(row.get('Relatório')) if travel else None
        if travel:
            if not receipt or not re.fullmatch(r'https://diarias\.alesc\.sc\.gov\.br/prestacao-contas/\d+',receipt):raise ValueError('Relatório ALESC sem identificador oficial')
            official=receipt.rsplit('/',1)[-1]
        else:official=hashlib.sha256(dump(row).encode()).hexdigest()
        individual=travel and row.get('Vínculo','').casefold()=='deputado' and account.isdigit()
        person=ensure_person(db,'alesc',account,name,r,url,uf='SC') if individual else None
        ac=cents(row.get('Valor'),localized=True)
        data=dict(official_id=official,person_id=person,person_name=name,institution='Assembleia Legislativa de Santa Catarina',mandate=None,year=day.year,month=day.month,document_date=None,expense_date=day.isoformat(),payment_date=None,description=('Diária concedida · vínculo '+row.get('Vínculo','não informado')) if travel else row.get('Descrição','Descrição não informada'),category='Diárias' if travel else row.get('Verba','Categoria não informada'),component='diarias' if individual else 'institucional',nature='AUTORIZADO' if travel else 'NAO_DETERMINADO',amount_cents=ac,original_amount=str(row.get('Valor','')),gross_cents=None,disallowed_cents=None,supplier=None if travel else row.get('Favorecido'),document_number=official if travel else None,receipt_url=receipt,verification='confirmed' if individual else 'pending',verification_note='Diária concedida publicada com vínculo Deputado e conta oficial; não comprova pagamento.' if individual else 'Sem vínculo individual inequívoco ou identificador estável de lançamento. Fora dos totais individuais.')
    else:raise ValueError('Conector não validado')
    if not 1<=data['month']<=12 or not 2008<=data['year']<=date.today().year:raise ValueError('Competência inválida')
    if data['amount_cents'] is None:data.update(verification='unavailable',verification_note=MISSING)
    if not data['category'] or data['category']=='Categoria não informada':data.update(verification='pending',verification_note=PENDING)
    data.update(id=source+':'+data['official_id'],source_id=source,currency='BRL',source_url=url,raw=dump(r),hash=hashlib.sha256(dump(r).encode()).hexdigest(),collected_at=stamp)
    return data

def save(db,data,batch,source_updated=None):
    old=db.execute('SELECT hash,verification FROM parliamentary_expenses WHERE id=?',(data['id'],)).fetchone()
    data=dict(data,batch_id=batch,source_updated_at=source_updated)
    cols=list(data)
    db.execute('INSERT INTO parliamentary_expenses('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+') ON CONFLICT(id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in cols if k!='id'),[data[k] for k in cols])
    if not old or old['hash']!=data['hash'] or old['verification']!=data['verification']:
        db.execute('INSERT INTO financial_audit_logs(expense_id,hash,raw,amount_cents,verification,collected_at,batch_id) VALUES(?,?,?,?,?,?,?)',tuple(data[k] for k in ('id','hash','raw','amount_cents','verification','collected_at','batch_id')))

def decode_rows(job,body):
    source=job['source_id']
    if job['target']:
        d=json.loads(body,parse_float=Decimal);rows=d['dados']
        if not isinstance(rows,list):raise ValueError('Contrato Câmara inválido')
        pid=job['target'].split(':')[-1]
        return [dict(r,_person_id=pid,_person_name=job.get('person_name','Identidade institucional')) for r in rows],next((x['href'] for x in d.get('links',[]) if x.get('rel')=='next'),None)
    if source in {'alesc_office','alesc_travel'}:
        rows=list(csv.DictReader(io.StringIO(body.decode('utf-8-sig')),delimiter=';'))
        required={'Nome','Conta','Vínculo','Data','Valor','Relatório'} if source=='alesc_travel' else {'Conta','Verba','Descrição','Data de Referência','Valor'}
        if rows and not required<=set(rows[0]):raise ValueError('Colunas ALESC alteradas')
        return rows,None
    if source=='camara_ceap':
        z=zipfile.ZipFile(io.BytesIO(body)); files=[f for f in z.infolist() if f.filename==f"Ano-{job['year']}.csv"]
        if len(files)!=1 or files[0].file_size>256_000_000:raise ValueError('Arquivo anual fora do contrato')
        rows=csv.DictReader(io.TextIOWrapper(z.open(files[0]),encoding='utf-8-sig'),delimiter=';')
        if not {'ideDocumento','ideCadastro','vlrLiquido','numAno','numMes'}<=set(rows.fieldnames or []):raise ValueError('Colunas Câmara alteradas')
        return rows,None
    rows=json.loads(body.decode('utf-8-sig'),parse_float=Decimal)
    if not isinstance(rows,list):raise ValueError('Contrato Senado inválido')
    return rows,None

def job_url(job):
    if job['cursor']:return validate_url(job['cursor'])
    if job['target']:return CAMARA+'deputados/'+job['target'].split(':')[-1]+'/despesas?'+urllib.parse.urlencode({'ano':job['year'],'itens':100,'pagina':1})
    if job['source_id']=='camara_ceap':return f"https://www.camara.leg.br/cotas/Ano-{job['year']}.csv.zip"
    if job['source_id']=='senado_ceaps':return SENADO+str(job['year'])
    path='diarias' if job['source_id']=='alesc_travel' else 'gabinetes-parlamentares'
    return f"https://transparencia.alesc.sc.gov.br/{path}/csv/{job['year']}"

def claim(db,stamp=None):
    stamp=time.time() if stamp is None else stamp
    db.execute('BEGIN IMMEDIATE')
    row=db.execute("SELECT * FROM financial_sync_jobs WHERE ((state IN ('pending','retry','complete') AND next_due<=?) OR (state='running' AND lease_until<?)) ORDER BY year DESC,COALESCE(last_success,''),key LIMIT 1",(stamp,stamp)).fetchone()
    if not row:db.commit();return None
    job=dict(row);token=uuid.uuid4().hex
    if job['state']=='complete':job['cursor']=None
    db.execute("UPDATE financial_sync_jobs SET state='running',lease_token=?,lease_until=?,cursor=? WHERE key=?",(token,stamp+600,job['cursor'],job['key']));db.commit();job['lease_token']=token
    if job['target']:
        person=db.execute('SELECT data FROM records WHERE id=?',(job['target'],)).fetchone()
        if not person:raise ValueError('Parlamentar não cadastrado')
        job['person_name']=json.loads(person['data'])['name']
    return job

def step(db,stamp=None,fetcher=None):
    job=claim(db,stamp)
    if not job:return False
    url=job_url(job)
    try:
        body,updated=(fetcher or download)(url);rows,nxt=decode_rows(job,body)
        if nxt:
            validate_url(nxt)
            a,b=urllib.parse.urlsplit(url),urllib.parse.urlsplit(nxt)
            before,after=urllib.parse.parse_qs(a.query),urllib.parse.parse_qs(b.query)
            if a.hostname!=b.hostname or a.path!=b.path or before.get('ano')!=after.get('ano') or int(after.get('pagina',['0'])[0])<=int(before.get('pagina',['1'])[0]):raise ValueError('Paginação financeira inválida')
        import_snapshot(db,job,rows,body,url,updated,nxt)
    except Exception as exc:
        db.rollback();attempts=job['attempts']+1
        # Do not include request headers, keys or supplier payload in public errors.
        db.execute("UPDATE financial_sync_jobs SET state=?,attempts=?,lease_until=NULL,lease_token=NULL,error=?,next_due=? WHERE key=? AND lease_token=?",('failed' if attempts>=5 else 'retry',attempts,type(exc).__name__+': fonte indisponível ou contrato não conciliado',time.time()+min(21600,60*2**attempts),job['key'],job['lease_token']));db.commit()
    return True

def import_snapshot(db,job,rows,body,url,updated,nxt):
    # Normalize large archives in a separate on-disk staging database. The live DB
    # remains readable; only the final atomic set-based merge takes its write lock.
    with tempfile.TemporaryDirectory(prefix='olb-financial-') as tmp:
        path=Path(tmp)/'stage.db';stage=connect(path);count=0;restitutions=set()
        try:
            stage.executemany('INSERT OR IGNORE INTO financial_sources VALUES(?,?,?,?,?,?,?)',SOURCES)
            for row in rows:
                r=normalized(stage,job['source_id'],row,url)
                if r['year']!=job['year']:raise ValueError('Competência fora da consulta')
                if stage.execute('SELECT 1 FROM parliamentary_expenses WHERE id=?',(r['id'],)).fetchone():
                    r.update(verification='pending',verification_note='Chave oficial ambígua nesta resposta; excluído dos totais até conciliação.')
                save(stage,r,None,updated);count+=1
                if count%1000==0:
                    db.execute('PRAGMA busy_timeout=250')
                    try:
                        db.execute('UPDATE financial_sync_jobs SET lease_until=? WHERE key=? AND lease_token=?',(time.time()+600,job['key'],job['lease_token']));db.commit()
                    except sqlite3.OperationalError:
                        db.rollback()  # A busy legislative writer must not discard staged public evidence.
                    finally:db.execute('PRAGMA busy_timeout=30000')
                if cents(row.get('vlrRestituicao')) not in (None,0):restitutions.add((str(row.get('ideCadastro','')),str(row.get('ideDocumento',''))))
            for person,doc in restitutions:
                stage.execute("UPDATE parliamentary_expenses SET verification='pending',verification_note='Documento com restituição associada; todas as parcelas fora dos totais até conciliação.' WHERE json_extract(raw,'$.ideCadastro')=? AND json_extract(raw,'$.ideDocumento')=?",(person,doc))
            stage.commit()
            unique=stage.execute('SELECT count(*) FROM parliamentary_expenses').fetchone()[0]
            confirmed=stage.execute("SELECT count(*) FROM parliamentary_expenses WHERE verification='confirmed'").fetchone()[0]
        finally:stage.close()
        db.execute('ATTACH DATABASE ? AS financial_stage',(str(path),))
        try:
            db.execute('BEGIN IMMEDIATE')
            lease=db.execute('SELECT lease_token FROM financial_sync_jobs WHERE key=?',(job['key'],)).fetchone()
            if not lease or lease[0]!=job['lease_token']:db.rollback();return
            batch=db.execute("INSERT INTO financial_import_batches(job_key,source_url,response_sha256,source_updated_at,collected_at,row_count,state) VALUES(?,?,?,?,?,?,'imported')",(job['key'],url,hashlib.sha256(body).hexdigest(),updated,now(),count)).lastrowid
            # Reuse existing identities without replacing their verified profile.
            db.execute('INSERT INTO records SELECT * FROM financial_stage.records WHERE true ON CONFLICT(id) DO NOTHING')
            db.execute('INSERT INTO versions(record_id,hash,raw,collected_at) SELECT s.id,s.hash,s.raw,s.collected_at FROM financial_stage.records s WHERE NOT EXISTS(SELECT 1 FROM versions v WHERE v.record_id=s.id AND v.hash=s.hash)')
            if job['target']:
                db.execute("DELETE FROM financial_stage.parliamentary_expenses WHERE id IN (SELECT id FROM main.parliamentary_expenses WHERE source_url LIKE 'https://www.camara.leg.br/cotas/%')")
            db.execute('INSERT INTO financial_stage.financial_sync_jobs(key,source_id,year,target) VALUES(?,?,?,?)',(job['key'],job['source_id'],job['year'],job['target']))
            db.execute('INSERT INTO financial_stage.financial_import_batches SELECT * FROM main.financial_import_batches WHERE id=?',(batch,))
            db.execute('UPDATE financial_stage.parliamentary_expenses SET batch_id=?',(batch,))
            db.execute('DROP TABLE IF EXISTS temp.financial_changes')
            db.execute('CREATE TEMP TABLE financial_changes AS SELECT s.* FROM financial_stage.parliamentary_expenses s LEFT JOIN main.parliamentary_expenses m ON m.id=s.id WHERE m.id IS NULL OR m.hash<>s.hash OR m.verification<>s.verification')
            cols=[r[1] for r in db.execute('PRAGMA table_info(parliamentary_expenses)')]
            db.execute('INSERT INTO main.parliamentary_expenses SELECT * FROM financial_stage.parliamentary_expenses WHERE true ON CONFLICT(id) DO UPDATE SET '+','.join(k+'=excluded.'+k for k in cols if k!='id'))
            db.execute('INSERT INTO financial_audit_logs(expense_id,hash,raw,amount_cents,verification,collected_at,batch_id) SELECT id,hash,raw,amount_cents,verification,collected_at,batch_id FROM financial_changes')
            # Keep alternate raw entries for ambiguous source identifiers too.
            db.execute('INSERT INTO financial_audit_logs(expense_id,hash,raw,amount_cents,verification,collected_at,batch_id) SELECT a.expense_id,a.hash,a.raw,a.amount_cents,s.verification,a.collected_at,? FROM financial_stage.financial_audit_logs a JOIN main.parliamentary_expenses s ON s.id=a.expense_id WHERE NOT EXISTS(SELECT 1 FROM main.financial_audit_logs m WHERE m.expense_id=a.expense_id AND m.hash=a.hash)',(batch,))
            db.execute('INSERT INTO financial_reconciliations(batch_id,expected_rows,persisted_rows,confirmed_rows,pending_rows,created_at) VALUES(?,?,?,?,?,?)',(batch,count,unique,confirmed,unique-confirmed,now()))
            if not nxt and not job['target']:
                db.execute("INSERT INTO financial_audit_logs(expense_id,hash,raw,amount_cents,verification,collected_at,batch_id) SELECT id,hash,raw,amount_cents,'pending',?,? FROM parliamentary_expenses WHERE source_id=? AND year=? AND COALESCE(batch_id,-1)<>? AND verification<>'pending'",(now(),batch,job['source_id'],job['year'],batch))
                db.execute("UPDATE parliamentary_expenses SET verification='pending',verification_note='Registro não retornou no último arquivo anual; revisão necessária.' WHERE source_id=? AND year=? AND COALESCE(batch_id,-1)<>? AND verification<>'pending'",(job['source_id'],job['year'],batch))
            imported=count+(job['imported'] if job['cursor'] else 0)
            interval=job['refresh_seconds'] if job['year']>=date.today().year-1 else 2592000
            db.execute("UPDATE financial_sync_jobs SET state=?,cursor=?,lease_until=NULL,lease_token=NULL,attempts=0,error=NULL,last_success=?,imported=?,next_due=? WHERE key=?",('pending' if nxt else 'complete',nxt,now(),imported,time.time()+(2 if nxt else interval),job['key']))
            if not nxt:db.execute('INSERT INTO financial_source_coverage VALUES(?,?,?,?,?,?,?) ON CONFLICT(job_key) DO UPDATE SET last_complete=excluded.last_complete,observed_count=excluded.observed_count,note=excluded.note',(job['key'],job['source_id'],job['year'],job['target'],now(),imported,'Consulta concluída na fonte; não comprova cobertura integral da atuação.'))
            db.commit()
        except Exception:db.rollback();raise
        finally:db.execute('DETACH DATABASE financial_stage')

def status(db):
    return dict(sources=[dict(r) for r in db.execute('SELECT * FROM financial_sources')],jobs=[dict(r) for r in db.execute('SELECT key,source_id,year,target,state,attempts,last_success,error,imported,next_due FROM financial_sync_jobs ORDER BY year DESC,key')],coverage=[dict(r) for r in db.execute('SELECT * FROM financial_source_coverage')],note='Somente fontes e competências listadas. Consulta vazia não comprova ausência de despesa. Último dado confirmado é mantido em falhas.')

def where(params):
    clauses=['1=1'];args=[]
    for param,column in [('person','person_id'),('source','source_id'),('year','year'),('month','month'),('category','category'),('nature','nature'),('verification','verification'),('mandate','mandate'),('component','component')]:
        value=params.get(param,'')
        if value:
            if param in {'year','month'}:
                value=int(value)
                if not (2008<=value<=date.today().year if param=='year' else 1<=value<=12):raise ValueError('Competência inválida')
            clauses.append('f.'+column+'=?');args.append(value)
    for param,column in [('q','person_name'),('supplier','supplier')]:
        if params.get(param):
            if len(params[param])>200:raise ValueError('Busca longa')
            clauses.append('instr(lower(f.'+column+'),lower(?))>0');args.append(params[param])
    if params.get('uf'):
        clauses.append("json_extract(p.data,'$.uf')=?");args.append(params['uf'].upper())
    return ' AND '.join(clauses),args

def public_row(row):
    r=dict(row)
    for key in ('raw','hash'):r.pop(key,None)
    for key in ('amount','gross','disallowed'):r[key]=money(r.pop(key+'_cents'))
    r['amount_label']=MISSING if r['amount'] is None else PENDING if r['verification']=='pending' else None
    return r

def query(db,params,export=False):
    condition,args=where(params);page=int(params.get('page',1));size=int(params.get('size',20))
    if not 1<=page<=100000 or not 1<=size<=100:raise ValueError('Paginação inválida')
    base=' FROM parliamentary_expenses f LEFT JOIN records p ON p.id=f.person_id WHERE '+condition
    total=db.execute('SELECT count(*)'+base,args).fetchone()[0]
    if export and total>10000:raise ValueError('Refine os filtros para exportar até 10000 registros')
    limit,offset=(10000,0) if export else (size,(page-1)*size)
    rows=db.execute('SELECT f.*'+base+' ORDER BY f.year DESC,f.month DESC,f.id LIMIT ? OFFSET ?',args+[limit,offset]).fetchall()
    # CHECK constraints guarantee INTEGER storage; SQLite SUM stays integer.
    # An overflow raises an error rather than converting to floating point.
    confirmed=" AND f.verification='confirmed' AND f.amount_cents IS NOT NULL AND f.person_id IS NOT NULL"
    grouped=db.execute('SELECT f.component,f.nature,SUM(f.amount_cents) amount,COUNT(*) n'+base+confirmed+' GROUP BY f.component,f.nature',args).fetchall()
    history=db.execute('SELECT f.year,f.month,f.component,f.nature,SUM(f.amount_cents) amount'+base+confirmed+' GROUP BY f.year,f.month,f.component,f.nature ORDER BY f.year,f.month,f.component,f.nature',args).fetchall()
    pending=total-sum(r['n'] for r in grouped)
    person=None
    if params.get('person'):
        p=db.execute("SELECT id,data,url FROM records WHERE id=? AND kind='person'",(params['person'],)).fetchone()
        if p:person=dict(id=p['id'],data=json.loads(p['data']),url=p['url'])
    return dict(total=total,page=page,size=limit,items=[public_row(r) for r in rows],person=person,
      totals=[dict(component=r['component'],nature=r['nature'],amount=money(r['amount']),records=r['n']) for r in grouped],
      timeline=[dict(year=r['year'],month=r['month'],component=r['component'],nature=r['nature'],amount=money(r['amount'])) for r in history],
      pending=pending,filters=params,categories=[r[0] for r in db.execute('SELECT DISTINCT category FROM parliamentary_expenses ORDER BY category')],
      methodology='Totais apenas de registros confirmados, separados por componente e natureza. Ajustes negativos permanecem separados. Não há custo total, soma de bruto e líquido ou soma de fases. Mandato desconhecido permanece desconhecido. Emendas ficam separadas.',
      amendments=dict(status='credentials_required',items=[],note='Não apurado. API CGU exige chave e conciliação de identificadores; nome isolado não vincula emenda ao parlamentar.'),coverage=status(db))

def csv_export(result):
    b=io.StringIO(newline='');w=csv.writer(b,delimiter=';')
    w.writerow(['Fiscalização Financeira','Emissão UTC',now(),'Escopo',dump(result['filters']),'Cobertura parcial','Registros',result['total']])
    columns=['id','person_id','person_name','institution','mandate','year','month','document_date','expense_date','payment_date','category','description','supplier','amount','gross','disallowed','currency','nature','verification','verification_note','document_number','source_url','receipt_url','collected_at','source_updated_at']
    w.writerow(columns)
    for row in result['items']:
        vals=[]
        for key in columns:
            value=row.get(key)
            if key in {'amount','gross','disallowed'} and value is None:value=MISSING
            if value is None:value='Não informado'
            value=str(value)
            if value.lstrip().startswith(('=','+','-','@','\t','\r')):value="'"+value
            vals.append(value)
        w.writerow(vals)
    return '\ufeff'+b.getvalue()

def run(stop=None):
    stop=stop or threading.Event();last_seed=0
    while not stop.is_set():
        busy=False
        try:
            with connect() as db:
                if time.time()-last_seed>3600:seed(db);last_seed=time.time()
                busy=step(db)
        except Exception:pass  # Job failures are persisted; process remains available.
        stop.wait(3 if busy else 15)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--steps',type=int);a=p.parse_args()
    if a.steps is None:run()
    else:
        with connect() as db:
            seed(db)
            for _ in range(a.steps):
                if not step(db):break
