import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from app.db import connect,upsert
from app.automatic import save_record_document,add_stream,author_stream,step,claim,save_proposal,save_document,link_author,status,APPROVAL_CODES
from app.productivity import dashboard

class Automatic(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/"test.db";self.db=connect(self.path)
        self.pid=upsert(self.db,"camara","person","1","https://dadosabertos.camara.leg.br/api/v2/deputados/1",{"nome":"Pessoa de teste"},dict(name="Pessoa de teste",search="pessoa"))
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def proposal(self,eid=2,type_="PL",date_="2024-01-10"):
        key=save_proposal(self.db,"camara",dict(id=eid,siglaTipo=type_,numero=eid,ano=2026,ementa="Teste",dataApresentacao=date_),"https://dadosabertos.camara.leg.br/api/v2/proposicoes")
        link_author(self.db,key,self.pid,"coauthor","https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/autores")
        return key
    def test_additive_migration_preserves_private_and_public_data(self):
        self.db.execute("INSERT INTO tenants VALUES('t','Organização')")
        self.db.execute("INSERT INTO watches(tenant_id,query,created_at) VALUES('t','termo','2026-01-01')")
        self.db.commit();self.db.close();self.db=connect(self.path)
        self.assertEqual(self.db.execute("SELECT count(*) FROM watches").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT count(*) FROM records").fetchone()[0],1)
        self.assertEqual(self.db.execute("SELECT MAX(version) FROM schema_versions").fetchone()[0],9)
    @patch("app.automatic.fetch")
    def test_all_pages_resume_across_restart_without_page_cap(self,fetch):
        u="https://dadosabertos.camara.leg.br/api/v2/proposicoes?pagina=1"
        nxt="https://dadosabertos.camara.leg.br/api/v2/proposicoes?pagina=2"
        add_stream(self.db,"test","camara","proposals",u,target=self.pid,priority=0,scope="teste")
        self.db.commit()
        fetch.return_value={"dados":[dict(id=2,siglaTipo="PL",ano=2026,numero=1)],"links":[{"rel":"next","href":nxt}]}
        step(self.db)
        self.assertEqual(self.db.execute("SELECT next_url FROM sync_streams WHERE key='test'").fetchone()[0],nxt)
        self.db.close();self.db=connect(self.path)
        self.db.execute("UPDATE sync_streams SET next_due=0 WHERE key='test'");self.db.commit()
        fetch.return_value={"dados":[dict(id=3,siglaTipo="PL",ano=2026,numero=2)],"links":[]}
        step(self.db)
        self.assertEqual(fetch.call_args.args[0],nxt)
        row=self.db.execute("SELECT * FROM sync_streams WHERE key='test'").fetchone()
        self.assertEqual((row["state"],row["pages"],row["items"]),("idle",2,2))
        self.assertEqual(self.db.execute("SELECT count(*) FROM authorships").fetchone()[0],2)
    @patch("app.automatic.fetch",side_effect=TimeoutError("teste"))
    def test_failed_page_preserves_cursor_and_retries(self,fetch):
        u="https://dadosabertos.camara.leg.br/api/v2/proposicoes?pagina=2"
        add_stream(self.db,"fail","camara","proposals",u);self.db.commit();step(self.db)
        row=self.db.execute("SELECT * FROM sync_streams WHERE key='fail'").fetchone()
        self.assertEqual(row["state"],"retry");self.assertEqual(row["next_url"],u)
        self.assertIsNone(row["completed_at"]);self.assertEqual(row["pages"],0)
    @patch("app.automatic.fetch")
    def test_pagination_loop_is_not_marked_complete(self,fetch):
        u="https://dadosabertos.camara.leg.br/api/v2/proposicoes"
        add_stream(self.db,"loop","camara","proposals",u);self.db.commit()
        fetch.return_value={"dados":[],"links":[{"rel":"next","href":u}]}
        step(self.db)
        self.assertEqual(self.db.execute("SELECT state FROM sync_streams WHERE key='loop'").fetchone()[0],"retry")
    def test_stale_lease_can_be_recovered_with_new_token(self):
        add_stream(self.db,"lease","camara","proposals","https://dadosabertos.camara.leg.br/api/v2/proposicoes");self.db.commit()
        self.db.execute("UPDATE sync_streams SET next_due=0");self.db.commit()
        first=claim(self.db,10);self.assertIsNone(claim(self.db,100));second=claim(self.db,200)
        self.assertNotEqual(first["lease_token"],second["lease_token"])
    @patch("app.automatic.fetch")
    def test_expired_worker_cannot_overwrite_new_lease(self,fetch):
        add_stream(self.db,"lease","camara","proposals","https://dadosabertos.camara.leg.br/api/v2/proposicoes");self.db.commit()
        def response(url):
            self.db.execute("UPDATE sync_streams SET error='other-lease' WHERE key='lease'");self.db.commit()
            return {"dados":[{"id":22,"siglaTipo":"PL","numero":22,"ano":2026}],"links":[]}
        fetch.side_effect=response;step(self.db)
        self.assertFalse(self.db.execute("SELECT 1 FROM records WHERE id='camara:proposal:22'").fetchone())
    def test_dead_letter_after_five_failures(self):
        add_stream(self.db,"dead","camara","proposals","https://dadosabertos.camara.leg.br/api/v2/proposicoes")
        self.db.execute("UPDATE sync_streams SET failures=4");self.db.commit()
        with patch("app.automatic.fetch",side_effect=TimeoutError("teste")):step(self.db)
        self.assertEqual(self.db.execute("SELECT state FROM sync_streams WHERE key='dead'").fetchone()[0],"dead")
    def test_approval_excludes_urgency_reports_and_requirements(self):
        key=self.proposal()
        stream=dict(source="camara",target=key,scope="tramitacoes")
        rows=[dict(codTipoTramitacao=c,sequencia=i,descricaoTramitacao="Teste",dataHora="2024-01-20") for i,c in enumerate(["196","336","195","194","191","237","244"])]
        save_document(self.db,stream,{"dados":rows},"https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/tramitacoes")
        self.db.commit();d=dashboard(self.db,self.pid)
        self.assertEqual(d["metrics"]["projects_with_approval_stage"],1)
        self.assertEqual(len(d["items"][0]["evidence"]),2)
        self.assertEqual(d["metrics"]["projects_history_pending"],0)
    def test_approved_requirement_does_not_become_approved_project(self):
        key=self.proposal(type_="REQ")
        save_document(self.db,dict(source="camara",target=key,scope="tramitacoes"),{"dados":[dict(codTipoTramitacao="244",sequencia=1)]},"https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/tramitacoes")
        d=dashboard(self.db,self.pid)
        self.assertEqual(d["metrics"]["proposals"],1);self.assertEqual(d["metrics"]["projects"],0)
        self.assertEqual(d["metrics"]["projects_with_approval_stage"],0)
    def test_period_uses_actual_presentation_not_renumbering(self):
        self.proposal(date_="2018-02-01")
        self.assertEqual(dashboard(self.db,self.pid,start="2026-01-01")["metrics"]["proposals"],0)
        self.assertEqual(dashboard(self.db,self.pid,start="2018-01-01",end="2018-12-31")["metrics"]["proposals"],1)
    def test_authority_and_no_invented_law_or_implementation(self):
        self.proposal();d=dashboard(self.db,self.pid)
        self.assertEqual(d["metrics"]["projects_history_pending"],1)
        self.assertIsNone(d["metrics"]["laws_publication_verified"])
        self.assertIsNone(d["metrics"]["implementation_verified"])
        self.assertFalse(d["sync"]["author_query_complete"])
    def test_duplicate_author_is_not_double_counted_and_people_are_separate(self):
        key=self.proposal()
        link_author(self.db,key,self.pid,"first_signatory","https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/autores")
        link_author(self.db,key,"camara:person:99","coauthor","https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/autores")
        d=dashboard(self.db,self.pid)
        self.assertEqual(d["metrics"]["proposals"],1);self.assertEqual(d["metrics"]["first_signatory"],1)
    def test_senate_current_contract_preserves_authorship_and_approval(self):
        pid=upsert(self.db,"senado","person","7","https://legis.senado.leg.br/dadosabertos/senador/7.json",{},dict(name="Teste",search="teste"))
        key=save_proposal(self.db,"senado",dict(id=81,identificacao="PL 1/2026",dataApresentacao="2026-01-01",siglaTipoDeliberacao="APROVADA_NO_PLENARIO",dataDeliberacao="2026-02-01"),"https://legis.senado.leg.br/dadosabertos/processo?codigoParlamentarAutor=7")
        payload=dict(id=81,documento=dict(dataApresentacao="2026-01-01"),autoriaIniciativa=[dict(codigoParlamentar=7,ordem=1)],autuacoes=[dict(numero=1,situacoes=[dict(sigla="APRVD",inicio="2026-02-01",descricao="APROVADA")])])
        save_document(self.db,dict(source="senado",target=key,scope="detail"),payload,"https://legis.senado.leg.br/dadosabertos/processo/81")
        d=dashboard(self.db,pid)
        self.assertEqual(d["metrics"]["first_signatory"],1);self.assertEqual(d["metrics"]["projects_with_approval_stage"],1)
    def test_senate_detail_does_not_erase_explicit_list_decision(self):
        key=save_proposal(self.db,"senado",dict(id=81,identificacao="PL 1/2026",siglaTipoDeliberacao="APROVADA_NO_PLENARIO"),"https://legis.senado.leg.br/dadosabertos/processo?ano=2026")
        save_document(self.db,dict(source="senado",target=key,scope="detail"),dict(id=81,autoriaIniciativa=[],autuacoes=[]),"https://legis.senado.leg.br/dadosabertos/processo/81")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM approval_evidence WHERE proposal_id=?",(key,)).fetchone()[0],1)
        save_proposal(self.db,"senado",dict(id=81,identificacao="PL 1/2026",siglaTipoDeliberacao="REJEITADO_PLENARIO"),"https://legis.senado.leg.br/dadosabertos/processo?ano=2026")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM approval_evidence WHERE proposal_id=?",(key,)).fetchone()[0],0)
    def test_dates_and_categories_are_validated(self):
        for opts in [dict(start="not-a-date"),dict(start="2026-02-01",end="2026-01-01"),dict(page=0),dict(category="best")]:
            with self.assertRaises(ValueError):dashboard(self.db,self.pid,**opts)
    def test_old_background_work_does_not_starve(self):
        u="https://dadosabertos.camara.leg.br/api/v2/proposicoes"
        add_stream(self.db,"fresh","camara","proposals",u,priority=30)
        add_stream(self.db,"old","camara","proposals",u,priority=55)
        self.db.execute("UPDATE sync_streams SET next_due=0 WHERE key='old'");self.db.commit()
        self.assertEqual(claim(self.db)["key"],"old")
    def test_nominal_votes_keep_real_categories_and_never_infer_symbolic_votes(self):
        vid=upsert(self.db,"camara","vote","55-1","https://dadosabertos.camara.leg.br/api/v2/votacoes/55-1",{},dict(date="2026-01-01",search="voto"))
        stream=dict(source="camara",target=vid,scope="votos")
        url="https://dadosabertos.camara.leg.br/api/v2/votacoes/55-1/votos"
        save_record_document(self.db,stream,{"dados":[{"deputado_":{"id":1},"tipoVoto":"Obstrução"}]},url)
        self.assertEqual(dashboard(self.db,self.pid)["voting"],[dict(choice="Obstrução",count=1)])
        save_record_document(self.db,stream,{"dados":[]},url)
        self.assertEqual(dashboard(self.db,self.pid)["voting"],[])
    def test_offline_worker_is_reported(self):
        self.assertFalse(status(self.db)["worker_online"])
        self.db.execute("INSERT INTO sync_heartbeats VALUES('worker',?,NULL)",(time.time(),))
        self.assertTrue(status(self.db)["worker_online"])
if __name__=="__main__":unittest.main()
