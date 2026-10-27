import csv,io,json,os,secrets,sqlite3,time,urllib.parse,hashlib
from http.cookies import SimpleCookie
from . import auth
from .calculations import brasilia
from collections import defaultdict,deque
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from .db import connect,search,serialize,now,ROOT
from .connectors import detail
from . import automatic,productivity,financial,presentation,economy,governments,rankings,analytics,source_monitor
import threading
SOURCES=[
("camara","Câmara dos Deputados","https://dadosabertos.camara.leg.br/swagger/api.html","Atualização automática: deputados, proposições, autoria, tramitação e votações. Consulte o progresso e a cobertura."),
("senado","Senado Federal","https://www12.senado.leg.br/dados-abertos","Atualização automática: senadores e processos do serviço atual; autoria e histórico com evidências. Votos do Senado ainda não integrados."),
("tse","TSE","https://dadosabertos.tse.jus.br/","Não integrado. Candidatura não equivale a exercício de mandato."),
("planalto","Planalto","https://www4.planalto.gov.br/legislacao/","Não integrado. Conversão de propostas em leis não verificada."),
("lexml","LexML","https://www.lexml.gov.br/","Não integrado."),
("estados","Assembleias / CLDF","https://www.interlegis.leg.br/","Dados legislativos estaduais não integrados. A cobertura financeira da ALESC é apresentada separadamente em Fiscalização Financeira."),
("municipios","Câmaras municipais / SAPL","https://www.interlegis.leg.br/","Nenhum município conectado; cadastro geográfico nacional pendente.")]
DATASETS={"camara_people","senado_people","camara_proposals","camara_votes"}
def coverage(db):
    output=[]
    for source,name,url,note in SOURCES:
        counts={r["kind"]:r["n"] for r in db.execute("SELECT kind,COUNT(*) n FROM records WHERE source=? GROUP BY kind",(source,))}
        interval=db.execute("SELECT MIN(collected_at),MAX(collected_at) FROM records WHERE source=?",(source,)).fetchone()
        years=[r[0] for r in db.execute("SELECT DISTINCT json_extract(data,'$.year') FROM records WHERE source=? AND kind IN ('proposal','vote')",(source,)) if r[0]]
        output.append(dict(id=source,name=name,url=url,note=note,counts=counts,status="partial" if counts else "not_synced" if source in {"camara","senado"} else "not_integrated",first_collected=interval[0],last_collected=interval[1],observed_years=sorted(years),historical_coverage="Não aferida; anos observados não comprovam cobertura completa."))
    return output
def safe_cell(value):
    value=str(value or "")
    return "'"+value if value.lstrip().startswith(("=","+","-","@","\t","\r")) else value
def report_csv(result,filters):
    buf=io.StringIO(newline=""); writer=csv.writer(buf)
    writer.writerow(["Emissão UTC",now(),"Filtros",json.dumps(filters,ensure_ascii=False),"Cobertura","Parcial; somente registros coletados"])
    writer.writerow(["ID","Nome / título","Fonte","URL oficial","Coleta UTC","Hash SHA256"])
    for r in result["items"]: writer.writerow([safe_cell(x) for x in [r["id"],r["data"].get("name"),r["source"],r["url"],r["collected_at"],r["hash"]]])
    return "\ufeff"+buf.getvalue()
class RestrictedAdministration(Exception):pass

class Handler(BaseHTTPRequestHandler):
    server_version="Observatorio/0.1"
    rates=defaultdict(deque)
    def log_message(self,format,*args): pass
    def current_user(self,db):
        cookie=SimpleCookie()
        try: cookie.load(self.headers.get("Cookie",""))
        except Exception: return None
        return auth.session(db,cookie["session"].value if "session" in cookie else None)
    def technical_view(self,db,params):
        if params.get('technical')!='1':return False
        user=self.current_user(db)
        if not user:raise PermissionError()
        if user['role']!='superadmin':raise RestrictedAdministration()
        return True
    def headers_common(self,ctype):
        self.send_header("Content-Type",ctype)
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header("Cache-Control","no-store")
        if getattr(self,"set_cookie",None): self.send_header("Set-Cookie",self.set_cookie)
    def respond(self,value,status=200,ctype="application/json; charset=utf-8"):
        body=(json.dumps(value,ensure_ascii=False) if ctype.startswith("application/json") else value).encode("utf8")
        self.send_response(status); self.headers_common(ctype); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
    def download(self,body,ctype,filename):
        if isinstance(body,str):body=body.encode('utf8')
        self.send_response(200);self.headers_common(ctype)
        self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def guard(self):
        host=self.headers.get("Host","")
        if host not in {f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}:
            self.respond({"error":"Instalação local: Host não permitido"},403); return False
        queue=self.rates[self.client_address[0]]; stamp=time.monotonic()
        while queue and queue[0]<stamp-60: queue.popleft()
        if len(queue)>=120: self.respond({"error":"Limite de consultas; aguarde um minuto"},429); return False
        queue.append(stamp); return True
    def do_GET(self):
        if not self.guard(): return
        try:
            u=urllib.parse.urlsplit(self.path); p={k:v[0] for k,v in urllib.parse.parse_qs(u.query).items()}
            if u.path in {"/","/app.js","/financial.js","/analytics.js","/style.css"}:
                name={"/":"index.html","/app.js":"app.js","/financial.js":"financial.js","/analytics.js":"analytics.js","/style.css":"style.css"}[u.path]
                return self.respond((ROOT/"web"/name).read_text(encoding="utf8"),ctype='text/javascript; charset=utf-8' if name.endswith('.js') else 'text/css; charset=utf-8' if name.endswith('.css') else 'text/html; charset=utf-8')
            with connect(migrate=False) as db:
                if u.path=="/api/health":
                    db.execute("SELECT 1").fetchone()
                    return self.respond({"status":"ok","database":"ok","database_check":"read_probe","integrity_check":"not_run","mode":"local_authenticated"})
                if u.path=="/api/session":
                    user=self.current_user(db)
                    return self.respond({"user":user,"plan":auth.plan(db,user) if user else None})
                if u.path=='/api/source-status':return self.respond(source_monitor.status(db,self.technical_view(db,p)))
                if u.path=='/api/economic-revisions':return self.respond(economy.revisions(db,p))
                if u.path=='/api/economy':return self.respond(economy.snapshot(db,p,self.technical_view(db,p)))
                if u.path=='/api/governments':return self.respond(governments.compare(db,p))
                if u.path=='/api/rankings':return self.respond(rankings.query(db,p))
                if u.path=='/api/assistant':return self.respond(analytics.answer(db,p))
                if u.path=='/api/analytics/export':
                    from .analytics_exports import export
                    title,rows,meta=analytics.dataset(db,p.get('module','economy'),p)
                    body,ctype=export(title,rows,meta,p.get('format','json'))
                    return self.download(body,ctype,'observatorio-relatorio.'+p.get('format','json'))
                if u.path=="/api/config": return self.respond({"name":os.environ.get("APP_NAME","Observatório Legislativo Brasil"),"mode":"Instalação local • organizações isoladas","billing":"Não ativado","ai":"Busca documental; IA generativa não configurada"} if self.technical_view(db,p) else {"name":os.environ.get("APP_NAME","Observatório Legislativo Brasil")})
                if u.path=="/api/automatic":
                    result=automatic.status(db);return self.respond(result if self.technical_view(db,p) else presentation.automatic(result))
                if u.path=="/api/financial/coverage":
                    result=financial.status(db);return self.respond(result if self.technical_view(db,p) else presentation.finance_coverage(result))
                if u.path=="/api/financial":
                    result=financial.query(db,p);return self.respond(result if self.technical_view(db,p) else presentation.financial(result))
                if u.path=='/api/financial/export':
                    from .financial_exports import xlsx_export,pdf_export
                    result=financial.query(db,p,export=True);form=p.get('format','csv');result['issued_at_brasilia']=brasilia()
                    if form=='json':return self.download(json.dumps(presentation.financial(result),ensure_ascii=False,indent=2),'application/json; charset=utf-8','fiscalizacao-financeira.json')
                    if form=='csv':return self.download(financial.csv_export(result),'text/csv; charset=utf-8','fiscalizacao-financeira.csv')
                    if form=='xlsx':return self.download(xlsx_export(result),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','fiscalizacao-financeira.xlsx')
                    if form=='pdf':return self.download(pdf_export(result),'application/pdf','fiscalizacao-financeira.pdf')
                    raise ValueError('Formato inválido')
                if u.path=="/api/politician":
                    return self.respond(presentation.politician(productivity.dashboard(db,p.get("id",""),p.get("start",""),p.get("end",""),int(p.get("page",1)),int(p.get("size",20)),p.get("category","all"))))
                if u.path=="/api/coverage":
                    result={"automatic":automatic.status(db),"sources":coverage(db),"runs":[dict(r) for r in db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 30")],"jobs":[dict(r) for r in db.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 30")]}
                    return self.respond(result if self.technical_view(db,p) else presentation.coverage(result))
                if u.path in {"/api/search","/api/export"}:
                    kind=p.get("kind","person")
                    if kind not in {"person","proposal","vote","document"}: raise ValueError("Tipo inválido")
                    page=int(p.get("page",1)); size=int(p.get("size",20))
                    if not 1<=page<=100000 or not 1<=size<=100: raise ValueError("Paginação inválida")
                    if len(p.get("q",""))>200: raise ValueError("Busca muito longa")
                    args={k:p.get(k,"") for k in ["q","source","uf","party","year"]}
                    result=search(db,kind=kind,page=page,size=size,**args)
                    if u.path=="/api/export":
                        # Export this page explicitly; never silently claim a full export.
                        return self.respond(report_csv(result,p),ctype="text/csv; charset=utf-8")
                    return self.respond(result)
                if u.path=="/api/record":
                    row=db.execute("SELECT * FROM records WHERE id=?",(p.get("id",""),)).fetchone()
                    if not row: return self.respond({"error":"Registro não encontrado"},404)
                    return self.respond({"record":serialize(row),"documents":[{"id":d["id"],"url":d["url"],"collected_at":d["collected_at"],"section":json.loads(d["data"]).get("section"),"payload":json.loads(d["raw"]),"note":"Documento preservado da fonte oficial. A cobertura é parcial."} for d in db.execute("SELECT * FROM records WHERE kind='document' AND json_extract(data,'$.parent')=? ORDER BY collected_at DESC",(row["id"],))],"versions":[dict(r) for r in db.execute("SELECT hash,collected_at FROM versions WHERE record_id=? ORDER BY id DESC LIMIT 50",(row["id"],))]})
                if u.path=="/api/watches":
                    user=self.current_user(db)
                    return self.respond({"watches":auth.watches(db,user),"events":auth.events(db,user)})
                return self.respond({"error":"Rota não encontrada"},404)
        except RestrictedAdministration: self.respond({"error":"Área reservada à administração"},403)
        except KeyError: self.respond({"error":"Parlamentar não encontrado"},404)
        except PermissionError: self.respond({"error":"Entre com sua conta para acessar esta área"},401)
        except (ValueError,TypeError): self.respond({"error":"Parâmetros inválidos"},400)
        except Exception: self.respond({"error":"Falha interna; consulte o estado da coleta"},500)
    def do_POST(self):
        if not self.guard(): return
        host=self.headers.get("Host","")
        if self.headers.get("Origin")!="http://"+host or self.headers.get("X-Local-Action")!="1":
            return self.respond({"error":"Origem inválida"},403)
        if self.headers.get("Content-Type","").split(";")[0]!="application/json":
            return self.respond({"error":"JSON obrigatório"},415)
        try:
            length=int(self.headers.get("Content-Length","0"))
            if not 0<length<=4096: raise ValueError()
            p=json.loads(self.rfile.read(length))
            if not isinstance(p,dict): raise ValueError()
            with connect(migrate=False) as db:
                path=urllib.parse.urlsplit(self.path).path
                if path=="/api/login":
                    email=p.get("email","");password=p.get("password","")
                    if not isinstance(email,str) or not isinstance(password,str): raise ValueError()
                    stamp=time.monotonic();attempts=self.rates["login:"+self.client_address[0]]
                    while attempts and attempts[0]<stamp-300: attempts.popleft()
                    if len(attempts)>=5: return self.respond({"error":"Muitas tentativas. Aguarde cinco minutos."},429)
                    attempts.append(stamp)
                    result=auth.login(db,email,password)
                    if not result: return self.respond({"error":"E-mail ou senha inválidos"},401)
                    self.set_cookie="session="+result[0]+"; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800"
                    return self.respond({"message":"Sessão iniciada","csrf":result[1]})
                user=self.current_user(db)
                auth.require(user,"reader")
                if not secrets.compare_digest(self.headers.get("X-CSRF-Token",""),user["csrf"]): raise PermissionError()
                if path=="/api/logout":
                    token=SimpleCookie(self.headers.get("Cookie",""))["session"].value
                    db.execute("DELETE FROM sessions WHERE id=?",(hashlib.sha256(token.encode()).hexdigest(),));db.commit()
                    self.set_cookie="session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0"
                    return self.respond({"message":"Sessão encerrada"})
                if path=="/api/economy/sync":
                    auth.require(user,"superadmin")
                    economy.seed(db)
                    db.execute("UPDATE economic_jobs SET next_due=0,state='pending' WHERE state<>'running'")
                    db.execute("INSERT INTO audit_log(tenant_id,user_id,action,created_at) VALUES(?,?,?,?)",(user['tenant_id'],user['id'],'economic_refresh_requested',now()));db.commit()
                    return self.respond({"message":"Consulta oficial solicitada. A publicação dos indicadores segue o calendário de cada órgão."},202)
                if path=="/api/automatic/retry":
                    auth.require(user,"superadmin")
                    db.execute("UPDATE sync_streams SET state='pending',failures=0,error=NULL,next_due=0 WHERE key=? AND state='dead'",(str(p.get("key","")),));db.commit()
                    return self.respond({"message":"Coleta reaberta para nova tentativa, preservando o cursor."})
                if path=='/api/financial/sync':
                    auth.require(user,'superadmin')
                    financial.seed(db)
                    key=financial.enqueue(db,str(p.get('source','')),int(p.get('year',0)),str(p.get('target','')))
                    db.execute("UPDATE financial_sync_jobs SET state='pending',attempts=0,error=NULL,next_due=0 WHERE key=? AND state<>'running'",(key,))
                    db.execute('INSERT INTO audit_log(tenant_id,user_id,action,created_at) VALUES(?,?,?,?)',(user['tenant_id'],user['id'],'financial_sync_requested:'+key,now()));db.commit()
                    return self.respond({'message':'Consulta financeira enfileirada; dados anteriores preservados.','key':key},202)
                if path=="/api/sync":
                    auth.require(user,"superadmin")
                    dataset=p.get("dataset")
                    if dataset not in DATASETS: raise ValueError()
                    db.execute("INSERT OR IGNORE INTO jobs(dataset) VALUES(?)",(dataset,)); db.commit()
                    return self.respond({"message":"Coleta enfileirada. Execute o worker para processar."},202)
                if path=="/api/detail":
                    auth.require(user,"analyst")
                    result=detail(db,str(p.get("id","")),str(p.get("section","detail")))
                    return self.respond(result)
                if path=="/api/watches":
                    auth.require(user,"analyst")
                    query=p.get("query","")
                    if not isinstance(query,str) or not 2<=len(query.strip())<=120: raise ValueError()
                    db.execute("BEGIN IMMEDIATE")
                    plan=auth.plan(db,user)
                    if plan["watch_limit"] is not None and plan["watch_count"]>=plan["watch_limit"]:
                        return self.respond({"error":"Limite de monitoramentos do plano atingido"},409)
                    db.execute("INSERT INTO watches(tenant_id,query,created_at) VALUES(?,?,?)",(user["tenant_id"],query.strip(),now())); db.execute("INSERT INTO audit_log(tenant_id,user_id,action,created_at) VALUES(?,?,?,?)",(user["tenant_id"],user["id"],"watch_created",now()));db.commit()
                    return self.respond({"message":"Monitoramento local salvo. Novas alterações coletadas gerarão eventos."},201)
                if path=="/api/watches/delete":
                    auth.require(user,"analyst")
                    db.execute("DELETE FROM watches WHERE id=? AND tenant_id=?",(int(p.get("id",0)),user["tenant_id"])); db.execute("INSERT INTO audit_log(tenant_id,user_id,action,created_at) VALUES(?,?,?,?)",(user["tenant_id"],user["id"],"watch_removed",now()));db.commit()
                    return self.respond({"message":"Monitoramento removido"})
                return self.respond({"error":"Rota não encontrada"},404)
        except PermissionError: self.respond({"error":"Entre com uma conta autorizada para esta ação"},403)
        except (ValueError,TypeError,sqlite3.IntegrityError): self.respond({"error":"Entrada inválida"},400)
        except RestrictedAdministration: self.respond({"error":"Área reservada à administração"},403)
        except KeyError: self.respond({"error":"Registro não encontrado"},404)
        except Exception: self.respond({"error":"Fonte indisponível ou contrato alterado. Nenhum resultado foi inventado."},502)
class LocalServer(ThreadingHTTPServer):
    # Windows otherwise permits two development instances to share one port.
    allow_reuse_address=False

def main():
    # Apply additive migrations before any collector thread or public request.
    with connect() as db:db.execute("SELECT 1").fetchone()
    port=int(os.environ.get("PORT","8080"))
    server=LocalServer((os.environ.get("BIND_HOST","127.0.0.1"),port),Handler)
    print(f"Observatório local: http://127.0.0.1:{port}",flush=True)
    stop=threading.Event()
    if os.environ.get("ECONOMIC_SYNC_ENABLED","1")!="0":
        threading.Thread(target=economy.run,args=(stop,),daemon=True).start()
        threading.Thread(target=source_monitor.run,args=(stop,),daemon=True).start()
    if os.environ.get("AUTO_SYNC_ENABLED","1")!="0":
        threading.Thread(target=automatic.run,args=(stop,),daemon=True).start()
    if os.environ.get('FINANCIAL_SYNC_ENABLED','1')!='0':
        threading.Thread(target=financial.run,args=(stop,),daemon=True).start()
    try:server.serve_forever()
    finally:
        stop.set();server.server_close()
if __name__=="__main__": main()
