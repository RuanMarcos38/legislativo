import json,time,urllib.request,urllib.parse
from datetime import date,timedelta
from .db import upsert,now
CAMARA="https://dadosabertos.camara.leg.br/api/v2/"
SENADO="https://legis.senado.leg.br/dadosabertos/"
class OfficialRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        validate_url(newurl)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
def validate_url(url):
    u=urllib.parse.urlsplit(url)
    if u.scheme!="https" or u.hostname not in {"dadosabertos.camara.leg.br","legis.senado.leg.br"} or u.port not in (None,443) or u.username or u.password:
        raise ValueError("URL fora das fontes autorizadas")
def fetch(url):
    validate_url(url)
    opener=urllib.request.build_opener(OfficialRedirect())
    req=urllib.request.Request(url,headers={"Accept":"application/json","User-Agent":"ObservatorioLegislativo/0.1 (consulta publica)"})
    for attempt in range(3):
        try:
            with opener.open(req,timeout=30) as response:
                body=response.read(16_000_001)
                if len(body)>16_000_000: raise ValueError("Resposta excede limite")
                return json.loads(body)
        except (urllib.error.URLError,TimeoutError):
            if attempt==2: raise
            time.sleep(2**attempt)
def array(value):
    return value if isinstance(value,list) else [value] if value else []
def person(source,row):
    if source=="camara":
        return str(row["id"]),dict(name=row["nome"],party=row.get("siglaPartido",""),uf=row.get("siglaUf",""),role="Deputado(a) federal",search=(row["nome"]+" "+row.get("siglaPartido","")).lower())
    p=row["IdentificacaoParlamentar"]
    return str(p["CodigoParlamentar"]),dict(name=p["NomeParlamentar"],party=p.get("SiglaPartidoParlamentar",""),uf=p.get("UfParlamentar",""),role="Senador(a)",search=(p["NomeParlamentar"]+" "+p.get("SiglaPartidoParlamentar","")).lower())
def sync(db,dataset,max_pages=5,year=None):
    if dataset not in {"camara_people","senado_people","camara_proposals","camara_votes"}: raise ValueError("Dataset não suportado")
    run=db.execute("INSERT INTO runs(dataset,started_at,status) VALUES(?,?,'running')",(dataset,now())).lastrowid
    db.commit(); count=0; complete=False
    try:
        if dataset=="senado_people":
            url=SENADO+"senador/lista/atual.json"; payload=fetch(url)
            rows=array(payload["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])
            for row in rows:
                eid,data=person("senado",row); upsert(db,"senado","person",eid,url,row,data); count+=1
            complete=True
        else:
            endpoint={"camara_people":"deputados","camara_proposals":"proposicoes","camara_votes":"votacoes"}[dataset]
            params={"itens":100,"pagina":1,"ordem":"ASC"}
            if endpoint=="proposicoes": params["ano"]=year or date.today().year
            if endpoint=="votacoes":
                end=date(year,1,31) if year else date.today()
                start=date(year,1,1) if year else end-timedelta(days=30)
                params["dataInicio"]=start.isoformat()
                params["dataFim"]=end.isoformat()
            url=CAMARA+endpoint+"?"+urllib.parse.urlencode(params)
            for page in range(max_pages):
                payload=fetch(url)
                if not isinstance(payload.get("dados"),list): raise ValueError("Contrato Câmara inválido")
                for row in payload["dados"]:
                    if endpoint=="deputados": eid,data=person("camara",row); kind="person"
                    else:
                        eid=str(row["id"]); kind="proposal" if endpoint=="proposicoes" else "vote"
                        name=(f'{row.get("siglaTipo","")} {row.get("numero","")}/{row.get("ano","")}' if kind=="proposal" else row.get("descricao","Votação"))
                        data=dict(name=name,description=row.get("ementa",row.get("descricao","")),year=str(row.get("ano",str(row.get("data",""))[:4])),date=row.get("data",""),type=row.get("siglaTipo",""),search=(name+" "+row.get("ementa",row.get("descricao",""))).lower())
                    upsert(db,"camara",kind,eid,CAMARA+endpoint+"/"+urllib.parse.quote(eid,safe=""),row,data); count+=1
                nxt=next((x["href"] for x in payload.get("links",[]) if x.get("rel")=="next"),None)
                db.execute("UPDATE runs SET count=?,checkpoint=? WHERE id=?",(count,nxt,run)); db.commit()
                if not nxt: complete=True; break
                validate_url(nxt); url=nxt; time.sleep(.3)
        # Complete refers only to this selected dataset/query; never to national coverage.
        status="complete_query" if complete else "partial"
        db.execute("UPDATE runs SET status=?,finished_at=?,count=? WHERE id=?",(status,now(),count,run)); db.commit()
        return dict(run=run,status=status,count=count)
    except Exception as exc:
        db.execute("UPDATE runs SET status='failed',finished_at=?,count=?,error=? WHERE id=?",(now(),count,type(exc).__name__+": "+str(exc)[:300],run)); db.commit(); raise
def detail(db,key,section="detail"):
    record=db.execute("SELECT * FROM records WHERE id=?",(key,)).fetchone()
    if not record: raise KeyError(key)
    source,kind,eid=record["source"],record["kind"],record["external_id"]
    if source=="senado":
        if section!="detail": raise ValueError("Seção não integrada para Senado")
        url=SENADO+"senador/"+urllib.parse.quote(eid,safe="")+".json"
    else:
        base={"person":"deputados","proposal":"proposicoes","vote":"votacoes"}.get(kind)
        if not base: raise ValueError("Tipo não suportado")
        allowed={"person":{"detail","historico","despesas"},"proposal":{"detail","autores","tramitacoes"},"vote":{"detail","votos"}}
        if section not in allowed[kind]: raise ValueError("Seção não suportada")
        url=CAMARA+base+"/"+urllib.parse.quote(eid,safe="")+("" if section=="detail" else "/"+section)
        if section=="despesas": url+="?itens=100&pagina=1"
    payload=fetch(url)
    data=dict(name=f"Documento oficial: {key} / {section}",search=key.lower(),parent=key,section=section)
    doc_key=upsert(db,source,"document",eid+":"+kind+":"+section,url,payload,data); db.commit()
    return dict(id=doc_key,url=url,collected_at=now(),payload=payload,note="Dados brutos da fonte. Coleções podem ter outras páginas; consulte links da resposta. Votação simbólica não identifica votos individuais.")
