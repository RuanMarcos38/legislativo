import csv,io,json,tempfile,time,unittest,urllib.request,urllib.error,threading,os
from pathlib import Path
from unittest.mock import patch
from app.db import connect,upsert,search,now
from app import auth
from app.connectors import validate_url,sync,person,detail
from app.worker import claim,tick
from app.server import Handler,LocalServer as ThreadingHTTPServer,report_csv
class Core(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=connect(Path(self.tmp.name)/"test.db")
        self.tenant,self.uid=auth.create_user(self.db,"Teste A","a@example.test","teste-longo-123")
        self.other,_=auth.create_user(self.db,"Teste B","b@example.test","teste-longo-456")
        self.user=dict(id=self.uid,tenant_id=self.tenant,role="admin")
    def tearDown(self): self.db.close();self.tmp.cleanup()
    def put(self,eid="1",name="Ana",source="camara",raw=None):
        return upsert(self.db,source,"person",eid,"https://dadosabertos.camara.leg.br/api/v2/deputados/"+eid,raw or {"nome":name},dict(name=name,uf="SP",party="P",search=name.lower()))
    def test_idempotence_and_change_history(self):
        key=self.put();self.put();self.assertEqual(self.db.execute("SELECT count(*) FROM versions").fetchone()[0],1)
        self.put(name="Ana Maria");self.assertEqual(self.db.execute("SELECT count(*) FROM versions").fetchone()[0],2)
        self.assertEqual(self.db.execute("SELECT count(*) FROM records").fetchone()[0],1)
    def test_homonyms_never_merge(self):
        self.put("1");self.put("2");self.put("1",source="senado")
        self.assertEqual(search(self.db)["total"],3)
    def test_filters_pagination_and_sql_input(self):
        self.put("1","Ana");self.put("2","Bia")
        self.assertEqual(search(self.db,q="ana",uf="SP")["total"],1)
        self.assertEqual(len(search(self.db,page=2,size=1)["items"]),1)
        self.assertEqual(search(self.db,q="' OR 1=1 --")["total"],0)
        self.assertEqual(search(self.db,q="%")["total"],0)
    def test_affiliation_change_preserves_version(self):
        self.put()
        upsert(self.db,"camara","person","1","https://dadosabertos.camara.leg.br/api/v2/deputados/1",{"nome":"Ana","partido":"Q"},dict(name="Ana",party="Q",uf="SP",search="ana"))
        self.assertEqual(search(self.db,party="Q")["total"],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM versions").fetchone()[0],2)
    def test_tenant_isolation_and_watch_delivery(self):
        self.db.execute("INSERT INTO watches(tenant_id,query,created_at) VALUES(?,?,?)",(self.tenant,"Ana",now()))
        self.put();self.put()
        self.assertEqual(len(auth.watches(self.db,self.user)),1)
        other=dict(tenant_id=self.other,role="reader")
        self.assertEqual(auth.watches(self.db,other),[])
        self.assertEqual(auth.events(self.db,other),[])
        self.assertEqual(len(auth.events(self.db,self.user)),1)
        with self.assertRaises(PermissionError): auth.require(other,"analyst")
        with self.assertRaises(PermissionError): auth.watches(self.db,None)
    def test_multiple_users_can_share_tenant_with_distinct_roles(self):
        tenant,uid=auth.create_user(self.db,"ignored","reader@example.test","reader-password-123","reader",self.tenant)
        token,_=auth.login(self.db,"reader@example.test","reader-password-123")
        user=auth.session(self.db,token)
        self.assertEqual(user["tenant_id"],self.tenant)
        self.assertEqual(user["role"],"reader")
        self.assertEqual(auth.plan(self.db,user)["watch_limit"],5)
    def test_login_and_session_expiry(self):
        self.assertIsNone(auth.login(self.db,"a@example.test","senha-invalida-123"))
        token,csrf=auth.login(self.db,"a@example.test","teste-longo-123")
        self.assertEqual(auth.session(self.db,token)["tenant_id"],self.tenant)
        self.assertNotIn(token,str(self.db.execute("SELECT * FROM sessions").fetchone()[:]))
        self.db.execute("UPDATE sessions SET expires_at=0")
        self.assertIsNone(auth.session(self.db,token))
    def test_source_allowlist(self):
        for url in ["http://dadosabertos.camara.leg.br/","https://localhost/","https://dadosabertos.camara.leg.br.evil.test/","https://dadosabertos.camara.leg.br:444/","https://user:pass@dadosabertos.camara.leg.br/"]:
            with self.assertRaises(ValueError): validate_url(url)
    def test_new_financial_identity_is_not_routed_to_another_house(self):
        key=self.put('15739','Identidade estadual',source='alesc')
        with patch('app.connectors.fetch') as fetcher:
            with self.assertRaises(ValueError):detail(self.db,key,'detail')
            fetcher.assert_not_called()
    def test_real_contract_shapes_using_test_only_fixture(self):
        eid,data=person("senado",{"IdentificacaoParlamentar":{"CodigoParlamentar":"123","NomeParlamentar":"Teste","UfParlamentar":"DF"}})
        self.assertEqual(eid,"123");self.assertEqual(data["uf"],"DF")
    @patch("app.connectors.fetch")
    def test_partial_pagination_is_not_complete(self,fetch):
        fetch.return_value={"dados":[{"id":1,"nome":"Teste","siglaUf":"SP"}],"links":[{"rel":"next","href":"https://dadosabertos.camara.leg.br/api/v2/deputados?pagina=2"}]}
        r=sync(self.db,"camara_people",max_pages=1)
        self.assertEqual(r["status"],"partial");self.assertEqual(r["count"],1)
    @patch("app.connectors.fetch",side_effect=TimeoutError("teste de indisponibilidade"))
    def test_source_failure_is_audited(self,fetch):
        with self.assertRaises(TimeoutError): sync(self.db,"senado_people")
        self.assertEqual(self.db.execute("SELECT status FROM runs").fetchone()[0],"failed")
    @patch("app.connectors.fetch",return_value={"dados":[],"links":[]})
    def test_detail_contract_does_not_send_unsupported_pagination(self,fetch):
        key=upsert(self.db,"camara","proposal","42","https://dadosabertos.camara.leg.br/api/v2/proposicoes/42",{},dict(name="Teste",search="teste"))
        detail(self.db,key,"tramitacoes")
        fetch.assert_called_once_with("https://dadosabertos.camara.leg.br/api/v2/proposicoes/42/tramitacoes")
    def test_worker_recovers_expired_lease(self):
        self.db.execute("INSERT INTO jobs(dataset,status,lease_until) VALUES('camara_people','running',0)");self.db.commit()
        job=claim(self.db);self.assertIsNotNone(job)
        self.assertIsNone(claim(self.db))
    @patch("app.worker.sync",side_effect=TimeoutError("teste"))
    def test_worker_dead_letter(self,sync_mock):
        self.db.execute("INSERT INTO jobs(dataset,attempts) VALUES('camara_people',4)");self.db.commit()
        tick(self.db)
        self.assertEqual(self.db.execute("SELECT status FROM jobs").fetchone()[0],"dead")
    def test_csv_formula_neutralization(self):
        self.put(name="=HYPERLINK(1)")
        output=report_csv(search(self.db),{"kind":"person"})
        rows=list(csv.reader(io.StringIO(output.lstrip("\ufeff"))))
        self.assertTrue(rows[2][1].startswith("'="));self.assertIn("https://dadosabertos",rows[2][3])
class HTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.old=os.environ.get("DATABASE_PATH");os.environ["DATABASE_PATH"]=str(Path(cls.tmp.name)/"http.db")
        with connect() as db:
            auth.create_user(db,"HTTP","http@example.test","http-password-123")
        cls.server=ThreadingHTTPServer(("127.0.0.1",0),Handler);cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
        if cls.old is None: os.environ.pop("DATABASE_PATH",None)
        else: os.environ["DATABASE_PATH"]=cls.old
        cls.tmp.cleanup()
    def request(self,path,body=None,headers=None):
        h=headers or {}
        if body is not None:
            h={"Content-Type":"application/json","Origin":f"http://127.0.0.1:{self.port}","X-Local-Action":"1",**h}
        req=urllib.request.Request(f"http://127.0.0.1:{self.port}"+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        return urllib.request.urlopen(req,timeout=5)
    def test_second_server_cannot_bind_the_same_port(self):
        with self.assertRaises(OSError): ThreadingHTTPServer(("127.0.0.1",self.port),Handler)
    def test_public_health_and_invalid_pagination(self):
        with self.request("/api/health") as r:self.assertEqual(json.load(r)["database"],"ok")
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request("/api/search?page=-1")
        self.assertEqual(cm.exception.code,400)
    def test_rebinding_and_private_area(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request("/api/health",headers={"Host":"evil.test"})
        self.assertEqual(cm.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request("/api/watches")
        self.assertEqual(cm.exception.code,401)
    def test_login_csrf_and_persistent_watch(self):
        with self.request("/api/login",{"email":"http@example.test","password":"http-password-123"}) as r:
            cookie=r.headers["Set-Cookie"].split(";")[0];csrf=json.load(r)["csrf"]
            self.assertIn("HttpOnly",r.headers["Set-Cookie"])
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request("/api/watches",{"query":"saúde"},{"Cookie":cookie})
        self.assertEqual(cm.exception.code,403)
        with self.request("/api/watches",{"query":"saúde"},{"Cookie":cookie,"X-CSRF-Token":csrf}) as r:self.assertEqual(r.status,201)
        with self.request("/api/watches",headers={"Cookie":cookie}) as r:self.assertEqual(len(json.load(r)["watches"]),1)
    def test_plan_limit_is_enforced_on_server(self):
        with self.request("/api/login",{"email":"http@example.test","password":"http-password-123"}) as r:
            cookie=r.headers["Set-Cookie"].split(";")[0];csrf=json.load(r)["csrf"]
        headers={"Cookie":cookie,"X-CSRF-Token":csrf}
        with self.request("/api/watches",headers={"Cookie":cookie}) as r: count=len(json.load(r)["watches"])
        for n in range(5-count):
            with self.request("/api/watches",{"query":"termo "+str(n)},headers) as r:self.assertEqual(r.status,201)
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request("/api/watches",{"query":"excede plano"},headers)
        self.assertEqual(cm.exception.code,409)
    def test_static_assets_and_security_headers(self):
        for path in ["/","/app.js","/financial.js","/style.css"]:
            with self.request(path) as r:
                self.assertEqual(r.status,200);self.assertEqual(r.headers["X-Content-Type-Options"],"nosniff")
                self.assertIn("frame-ancestors 'none'",r.headers["Content-Security-Policy"])
    def test_financial_public_reads_export_and_restricted_sync(self):
        with self.request('/api/financial?year=2026') as r:self.assertEqual(json.load(r)['totals'],[])
        for form,signature in [('csv',b'\xef\xbb\xbf'),('xlsx',b'PK'),('pdf',b'%PDF')]:
            with self.request('/api/financial/export?format='+form+'&year=2026') as r:
                self.assertTrue(r.read().startswith(signature));self.assertIn('attachment',r.headers['Content-Disposition'])
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request('/api/financial/sync',{'source':'senado_ceaps','year':2026})
        self.assertEqual(cm.exception.code,403)
        with self.request('/api/login',{'email':'http@example.test','password':'http-password-123'}) as r:
            cookie=r.headers['Set-Cookie'].split(';')[0];csrf=json.load(r)['csrf']
        with self.assertRaises(urllib.error.HTTPError) as cm:self.request('/api/financial/sync',{'source':'senado_ceaps','year':2026},{'Cookie':cookie,'X-CSRF-Token':csrf})
        self.assertEqual(cm.exception.code,403)
if __name__=="__main__":unittest.main()
