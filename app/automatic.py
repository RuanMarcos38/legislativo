"""Resumable, source-backed ingestion. One page per lease; no arbitrary page cap."""
import argparse,calendar,json,os,threading,time,urllib.parse,uuid
from datetime import date
from .db import connect,upsert,now
from .connectors import CAMARA,SENADO,fetch,person,array,validate_url

PROJECT_TYPES={"PL","PLP","PEC","PDL","PDC","PRC","PRS","PLS","PLC","PLV","PEC"}
# Explicit official Câmara event codes. Parecer, urgência and requerimento approvals excluded.
APPROVAL_CODES={"237","238","239","240","244","1235","1518","1519"}
SENATE_APPROVALS={"APROVADA_EM_COMISSAO_TERMINATIVA","APROVADA_NO_PLENARIO",
 "APROVADA_PARCIALMENTE","APROVADO_NA_INTEGRA","APROVADO_PLV"}
CAMARA_CODES_URL=CAMARA+"referencias/proposicoes/codTipoTramitacao"
def add_stream(db,key,source,mode,url,target=None,priority=50,scope="",refresh=21600):
    validate_url(url)
    db.execute("""INSERT OR IGNORE INTO sync_streams(key,source,mode,target,initial_url,next_url,priority,scope,refresh_seconds,next_due)
     VALUES(?,?,?,?,?,?,?,?,?,?)""",(key,source,mode,target,url,url,priority,scope,refresh,time.time()))
def author_stream(db,key,priority=30):
    source,kind,eid=key.split(":")
    if kind!="person" or source not in {"camara","senado"} or not eid.isdigit():raise ValueError("Identidade inválida")
    if source=="camara":
        url=CAMARA+"proposicoes?"+urllib.parse.urlencode({"idDeputadoAutor":eid,"itens":100,"pagina":1})
    else:url=SENADO+"processo?"+urllib.parse.urlencode({"codigoParlamentarAutor":eid})
    sid="author:"+key
    add_stream(db,sid,source,"proposals",url,target=key,priority=priority,scope="Autoria/coautoria disponível na fonte; todos os anos retornados")
    db.execute("UPDATE sync_streams SET priority=MIN(priority,?) WHERE key=?",(priority,sid))
    return sid
def seed(db,today=None):
    today=today or date.today()
    add_stream(db,"camara:people","camara","people",CAMARA+"deputados?itens=100&pagina=1",priority=10,scope="Lista atual da Câmara")
    add_stream(db,"senado:people","senado","people",SENADO+"senador/lista/atual.json",priority=10,scope="Senadores em exercício")
    # Recent cohorts first. The dates are configured scope, not claims of source completeness.
    starts={"camara":int(os.environ.get("AUTO_CAMARA_START_YEAR","1934")),"senado":int(os.environ.get("AUTO_SENADO_START_YEAR","1826"))}
    for source,start in starts.items():
        if not 1800<=start<=today.year:raise ValueError("Ano inicial automático inválido")
        for year in range(today.year,start-1,-1):
            url=(CAMARA+"proposicoes?"+urllib.parse.urlencode({"ano":year,"itens":100,"pagina":1}) if source=="camara" else SENADO+"processo?ano="+str(year))
            add_stream(db,f"{source}:proposals:{year}",source,"proposals",url,priority=40+min(today.year-year,100),scope=f"Ano de identificação {year}; histórico da fonte pode conter lacunas",refresh=21600 if year>=today.year-1 else 2592000)
    first=int(os.environ.get("AUTO_VOTES_START_YEAR","2023"))
    if not 1800<=first<=today.year:raise ValueError("Ano inicial de votações inválido")
    for year in range(today.year,first-1,-1):
        for month in range(12,0,-1):
            if (year,month)>(today.year,today.month):continue
            start=date(year,month,1);end=min(date(year,month,calendar.monthrange(year,month)[1]),today)
            url=CAMARA+"votacoes?"+urllib.parse.urlencode({"dataInicio":start.isoformat(),"dataFim":end.isoformat(),"itens":100,"pagina":1})
            add_stream(db,f"camara:votes:{year}-{month:02}","camara","votes",url,priority=35 if year==today.year else 90,scope=f"Votações Câmara {start} a {end}",refresh=21600 if end==today else 2592000)
            # The current month's end advances with the calendar, without discarding an active cursor.
            db.execute("UPDATE sync_streams SET initial_url=? WHERE key=?",(url,f"camara:votes:{year}-{month:02}"))
    # Backfill relations for already persisted people after an upgrade.
    for row in db.execute("SELECT id FROM records WHERE kind='person' AND source IN ('camara','senado')").fetchall():
        author_stream(db,row["id"])
    db.commit()
def schedule_documents(db,source,eid,priority=55):
    base=CAMARA+"proposicoes/"+str(eid) if source=="camara" else SENADO+"processo/"+str(eid)
    for section in (["detail","autores","tramitacoes"] if source=="camara" else ["detail"]):
        stream_key=f"{source}:proposal:{eid}:{section}"
        add_stream(db,stream_key,source,"document",base+("" if section=="detail" else "/"+section),target=f"{source}:proposal:{eid}",priority=priority,scope=section)
        db.execute("UPDATE sync_streams SET priority=MIN(priority,?) WHERE key=?",(priority,stream_key))
def save_proposal(db,source,row,url):
    eid=str(row["id"])
    name=(f'{row.get("siglaTipo","")} {row.get("numero","")}/{row.get("ano","")}' if source=="camara" else row["identificacao"])
    type_=row.get("siglaTipo","") if source=="camara" else name.split(" ",1)[0]
    data=dict(name=name,description=row.get("ementa",""),year=str(row.get("ano",name.rsplit("/",1)[-1])),type=type_,date=row.get("dataApresentacao",""),search=(name+" "+row.get("ementa","")).lower())
    canonical=CAMARA+"proposicoes/"+eid if source=="camara" else SENADO+"processo/"+eid
    key=upsert(db,source,"proposal",eid,canonical,row,data)
    # Date of presentation, not year of renumbering, controls the dashboard's period.
    db.execute("""INSERT INTO proposal_facts(proposal_id,source,type,presented_at) VALUES(?,?,?,?)
     ON CONFLICT(proposal_id) DO UPDATE SET type=excluded.type,
     presented_at=COALESCE(NULLIF(excluded.presented_at,''),proposal_facts.presented_at)""",(key,source,type_,data["date"]))
    if source=="senado":
        db.execute("UPDATE proposal_facts SET status=?,norm_reported=?,detail_checked_at=? WHERE proposal_id=?",(row.get("situacaoAtual",""),int(bool(row.get("normaGerada"))),now(),key))
        db.execute("DELETE FROM approval_evidence WHERE proposal_id=? AND event_key LIKE 'decision:%'",(key,))
        decision=row.get("siglaTipoDeliberacao")
        if decision in SENATE_APPROVALS:
            add_evidence(db,key,"decision:"+decision,decision,decision,row.get("dataDeliberacao"),row,url)
    schedule_documents(db,source,eid)
    return key
def add_evidence(db,key,event,code,description,stamp,row,url):
    db.execute("""INSERT INTO approval_evidence VALUES(?,?,?,?,?,?,?,?)
     ON CONFLICT(proposal_id,event_key) DO UPDATE SET code=excluded.code,description=excluded.description,
     event_date=excluded.event_date,body=excluded.body,source_url=excluded.source_url,collected_at=excluded.collected_at""",
     (key,event,str(code),description,stamp,json.dumps(row,ensure_ascii=False),url,now()))
def link_author(db,proposal,person_id,relation,url):
    db.execute("""INSERT INTO authorships VALUES(?,?,?,?,?) ON CONFLICT(proposal_id,person_id)
     DO UPDATE SET relation=CASE WHEN excluded.relation='author_unspecified' THEN authorships.relation ELSE excluded.relation END,
     source_url=excluded.source_url,collected_at=excluded.collected_at""",(proposal,person_id,relation,url,now()))
def save_document(db,stream,payload,url):
    target=stream["target"];source=stream["source"];section=stream["scope"]
    eid=target.split(":")[-1]
    upsert(db,source,"document",eid+":proposal:"+section,url,payload,dict(name="Documento oficial: "+target+" / "+section,search=target.lower(),parent=target,section=section))
    if source=="camara":
        if section=="detail":
            row=payload["dados"];status=row.get("statusProposicao") or {}
            db.execute("""UPDATE proposal_facts SET status=?,urn=?,norm_reported=?,detail_checked_at=?,
             presented_at=COALESCE(NULLIF(?,''),presented_at) WHERE proposal_id=?""",
             (status.get("descricaoSituacao",""),row.get("urnFinal"),int(str(status.get("codSituacao"))=="1140" or bool(row.get("urnFinal"))),now(),row.get("dataApresentacao",""),target))
        elif section=="autores":
            rows=payload["dados"]
            if not isinstance(rows,list):raise ValueError("Contrato de autoria inválido")
            db.execute("DELETE FROM authorships WHERE proposal_id=?",(target,))
            for row in rows:
                uri=row.get("uri") or "";prefix=CAMARA+"deputados/"
                if not uri.startswith(prefix) or not uri[len(prefix):].isdigit():continue
                pid=uri[len(prefix):];person_id="camara:person:"+pid
                if not db.execute("SELECT 1 FROM records WHERE id=?",(person_id,)).fetchone():
                    name=row.get("nome","Identidade institucional")
                    upsert(db,"camara","person",pid,uri,row,dict(name=name,role="Identificado na autoria; mandato não verificado",search=name.lower()))
                relation="first_signatory" if row.get("ordemAssinatura")==1 else "coauthor"
                link_author(db,target,person_id,relation,url)
            db.execute("UPDATE proposal_facts SET authors_checked_at=? WHERE proposal_id=?",(now(),target))
        elif section=="tramitacoes":
            rows=payload["dados"]
            if not isinstance(rows,list):raise ValueError("Contrato de tramitação inválido")
            db.execute("DELETE FROM approval_evidence WHERE proposal_id=?",(target,))
            for i,row in enumerate(rows):
                code=str(row.get("codTipoTramitacao",""))
                if code in APPROVAL_CODES:
                    add_evidence(db,target,str(row.get("sequencia",i)),code,row.get("descricaoTramitacao",""),row.get("dataHora"),row,url)
            db.execute("UPDATE proposal_facts SET history_checked_at=? WHERE proposal_id=?",(now(),target))
    else:
        if not isinstance(payload,dict) or str(payload.get("id"))!=eid:raise ValueError("Processo Senado inesperado")
        rows=payload.get("autoriaIniciativa",payload.get("documento",{}).get("autoria",[]))
        db.execute("DELETE FROM authorships WHERE proposal_id=?",(target,))
        for row in rows:
            pid=row.get("codigoParlamentar")
            if not pid:continue
            relation="first_signatory" if row.get("ordem")==1 else "coauthor"
            link_author(db,target,"senado:person:"+str(pid),relation,url)
        db.execute("""UPDATE proposal_facts SET status=?,detail_checked_at=?,authors_checked_at=?,history_checked_at=?,
         presented_at=COALESCE(NULLIF(?,''),presented_at) WHERE proposal_id=?""",
         (payload.get("situacaoAtual",""),now(),now(),now(),payload.get("documento",{}).get("dataApresentacao",""),target))
        db.execute("DELETE FROM approval_evidence WHERE proposal_id=? AND event_key NOT LIKE 'decision:%'",(target,))
        for aut in array(payload.get("autuacoes")):
            for row in array(aut.get("situacoes")):
                # A Senate state APRVD is approval in that institution, never enactment.
                if row.get("sigla")=="APRVD":
                    add_evidence(db,target,str(aut.get("numero"))+":"+str(row.get("inicio")),row["sigla"],row.get("descricao",""),row.get("inicio"),row,url)
def save_record_document(db,stream,payload,url):
    target=stream["target"];source=stream["source"];section=stream["scope"]
    _,kind,eid=target.split(":")
    upsert(db,source,"document",eid+":"+kind+":"+section,url,payload,dict(name="Documento oficial: "+target+" / "+section,search=target.lower(),parent=target,section=section))
    if kind=="vote" and section=="votos":
        rows=payload["dados"]
        if not isinstance(rows,list):raise ValueError("Contrato de votos inválido")
        db.execute("DELETE FROM nominal_votes WHERE vote_id=?",(target,))
        vote=db.execute("SELECT data FROM records WHERE id=?",(target,)).fetchone()
        vote_date=json.loads(vote["data"]).get("date")
        for row in rows:
            deputy=row.get("deputado_") or row.get("deputado") or {}
            if deputy.get("id") is None or not row.get("tipoVoto"):continue
            db.execute("INSERT OR REPLACE INTO nominal_votes VALUES(?,?,?,?,?,?)",
              (target,"camara:person:"+str(deputy["id"]),row["tipoVoto"],vote_date,url,now()))
    return 1,None

def ingest(db,stream,payload,url):
    source=stream["source"];mode=stream["mode"];count=0;nxt=None
    if mode=="record_document":
        return save_record_document(db,stream,payload,url)
    if mode=="document":
        save_document(db,stream,payload,url);return 1,None
    if mode=="people":
        rows=payload["dados"] if source=="camara" else array(payload["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])
        for row in rows:
            eid,data=person(source,row);key=upsert(db,source,"person",eid,(CAMARA+"deputados/"+eid if source=="camara" else SENADO+"senador/"+eid+".json"),row,data)
            author_stream(db,key)
            base=CAMARA+"deputados/"+eid if source=="camara" else SENADO+"senador/"+eid+".json"
            for section in (["detail","historico"] if source=="camara" else ["detail"]):
                add_stream(db,key+":"+section,source,"record_document",base+("" if section=="detail" else "/"+section),target=key,scope=section)
            count+=1
    elif mode=="proposals":
        rows=payload["dados"] if source=="camara" else payload
        if not isinstance(rows,list):raise ValueError("Contrato de proposições inválido")
        for row in rows:
            key=save_proposal(db,source,row,url)
            if stream["target"]:link_author(db,key,stream["target"],"author_unspecified",url)
            if stream["priority"]<=5:schedule_documents(db,source,row["id"],priority=6)
            count+=1
    elif mode=="votes":
        rows=payload["dados"]
        if not isinstance(rows,list):raise ValueError("Contrato de votações inválido")
        for row in rows:
            eid=str(row["id"]);name=row.get("descricao","Votação")
            upsert(db,source,"vote",eid,CAMARA+"votacoes/"+urllib.parse.quote(eid,safe=""),row,dict(name=name,description=name,date=row.get("data",""),year=str(row.get("data",""))[:4],search=name.lower()))
            add_stream(db,"votes:"+eid,source,"record_document",CAMARA+"votacoes/"+urllib.parse.quote(eid,safe="")+"/votos",target=source+":vote:"+eid,scope="votos")
            count+=1
    else:raise ValueError("Modo de coleta inválido")
    if source=="camara":
        nxt=next((r["href"] for r in payload.get("links",[]) if r.get("rel")=="next"),None)
    if nxt:validate_url(nxt)
    return count,nxt
def claim(db,stamp=None):
    stamp=time.time() if stamp is None else stamp
    db.execute("BEGIN IMMEDIATE")
    row=db.execute("""SELECT * FROM sync_streams WHERE
      ((state IN ('pending','idle','retry') AND next_due<=?) OR (state='running' AND lease_until<?))
      ORDER BY CASE WHEN priority<10 THEN priority ELSE MAX(10,priority-CAST((?-COALESCE(last_attempt,next_due))/60 AS INTEGER)) END,
      COALESCE(last_attempt,0),key LIMIT 1""",(stamp,stamp,stamp)).fetchone()
    if not row:db.commit();return None
    row=dict(row)
    if row["state"]=="idle":
        row.update(next_url=row["initial_url"],cycle=row["cycle"]+1,pages=0,items=0)
    token=uuid.uuid4().hex
    # A unique lease token prevents a late worker from committing after lease recovery.
    db.execute("""UPDATE sync_streams SET state='running',lease_until=?,last_attempt=?,next_url=?,
      cycle=?,pages=?,items=?,error=? WHERE key=?""",
      (stamp+180,stamp,row["next_url"],row["cycle"],row["pages"],row["items"],"lease:"+token,row["key"]))
    db.commit();row["lease_token"]="lease:"+token
    return row
def step(db,stamp=None):
    stream=claim(db,stamp)
    if not stream:return False
    url=stream["next_url"] or stream["initial_url"]
    try:
        payload=fetch(url)
        db.execute("BEGIN IMMEDIATE")
        lease=db.execute("SELECT error FROM sync_streams WHERE key=?",(stream["key"],)).fetchone()
        if lease["error"]!=stream["lease_token"]:db.rollback();return True
        count,nxt=ingest(db,stream,payload,url)
        if nxt and (nxt==url or db.execute("SELECT 1 FROM sync_pages WHERE stream_key=? AND cycle=? AND url=?",(stream["key"],stream["cycle"],nxt)).fetchone()):
            raise ValueError("Paginação circular detectada")
        db.execute("INSERT OR IGNORE INTO sync_pages VALUES(?,?,?,?)",(stream["key"],stream["cycle"],url,now()))
        db.execute("""UPDATE sync_streams SET next_url=?,state=?,lease_until=NULL,failures=0,error=NULL,
         pages=pages+1,items=items+?,last_success=?,completed_at=CASE WHEN ? IS NULL THEN ? ELSE completed_at END,
         next_due=? WHERE key=?""",(nxt,"pending" if nxt else "idle",count,now(),nxt,now(),time.time()+(.5 if nxt else stream["refresh_seconds"]),stream["key"]))
        db.commit()
    except Exception as exc:
        db.rollback()
        failures=stream["failures"]+1
        db.execute("""UPDATE sync_streams SET state=?,failures=?,lease_until=NULL,error=?,next_due=?
         WHERE key=? AND error=?""",("dead" if failures>=5 else "retry",failures,type(exc).__name__+": "+str(exc)[:350],time.time()+min(3600,30*2**failures),stream["key"],stream["lease_token"]))
        db.commit()
    return True
def status(db):
    beat=db.execute("SELECT MAX(seen_at) FROM sync_heartbeats").fetchone()[0]
    counts={r["state"]:r["n"] for r in db.execute("SELECT state,COUNT(*) n FROM sync_streams GROUP BY state")}
    rows=[dict(r) for r in db.execute("SELECT key,source,mode,target,state,pages,items,last_success,completed_at,next_due,scope,CASE WHEN state='running' THEN NULL ELSE error END error FROM sync_streams ORDER BY last_attempt DESC LIMIT 30")]
    return dict(enabled=os.environ.get("AUTO_SYNC_ENABLED","1")!="0",worker_online=bool(beat and time.time()-beat<180),last_heartbeat=beat,states=counts,streams=rows,interval_hours=6,note="Consulta concluída refere-se somente ao escopo da consulta. Não comprova cobertura nacional completa.")
def run(stop=None):
    stop=stop or threading.Event();worker="auto:"+str(os.getpid())+":"+uuid.uuid4().hex[:8];seeded=0
    while not stop.is_set():
        error=None
        try:
            with connect() as db:
                if time.time()-seeded>3600:seed(db);seeded=time.time()
                db.execute("INSERT OR REPLACE INTO sync_heartbeats VALUES(?,?,NULL)",(worker,time.time()));db.commit()
                busy=step(db)
        except Exception as exc:error=type(exc).__name__+": "+str(exc)[:250];busy=False
        if error:
            try:
                with connect() as db:db.execute("INSERT OR REPLACE INTO sync_heartbeats VALUES(?,?,?)",(worker,time.time(),error))
            except Exception:pass
        stop.wait(max(.2,float(os.environ.get("AUTO_REQUEST_INTERVAL","1"))) if busy else 5)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--steps",type=int);args=p.parse_args()
    if args.steps is None:run()
    else:
        with connect() as db:
            seed(db)
            for _ in range(args.steps):
                if not step(db):break
