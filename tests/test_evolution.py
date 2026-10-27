import csv,io,json,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from app.db import connect,upsert
from app import economy,governments,rankings,analytics,source_monitor
from app.economic_catalog import BY_ID
from app.calculations import change,ratio,deflate,brasilia
from app.analytics_exports import export
from app.automatic import save_proposal,link_author

class Evolution(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=connect(Path(self.tmp.name)/'test.db')
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def job(self,key):
        self.db.execute('INSERT INTO economic_jobs(indicator) VALUES(?)',(key,));self.db.commit()
    def feed(self,key,points):
        self.job(key)
        if BY_ID[key]['connector']=='bcb':payload=[dict(data=p,valor=v) for p,v in points]
        else:payload=[dict(id=BY_ID[key]['url'].split('/variaveis/')[1].split('?')[0],resultados=[dict(series=[dict(localidade=dict(id='1'),serie=dict(points))])])]
        economy.step(self.db,fetcher=lambda url:payload)
        return payload
    def test_exact_changes_zero_negative_and_points(self):
        self.assertEqual(change('110','100')['percentage'],'10')
        self.assertIsNone(change('10','0')['percentage'])
        self.assertIsNone(change('-5','-10')['percentage'])
        self.assertEqual(change('5.5','4.5',True)['points'],'1')
        self.assertEqual(ratio('1','4')['value'],'25')
        self.assertEqual(deflate('100','100','120'),'120')
    def test_brasilia_independent_of_host_timezone(self):
        self.assertEqual(brasilia('2026-10-27T01:00:00+00:00'),'26/10/2026 22:00:00 — Horário de Brasília')
    def test_additive_migration_preserves_existing_record(self):
        key=upsert(self.db,'camara','person','1','https://dadosabertos.camara.leg.br/api/v2/deputados/1',{},dict(name='Pessoa de teste',search='pessoa'))
        self.db.commit();self.assertEqual(self.db.execute('SELECT id FROM records').fetchone()[0],key)
        self.assertIsNotNone(self.db.execute('SELECT version FROM schema_versions WHERE version=7').fetchone())
    def test_ibge_real_contract_and_quarter_validation(self):
        self.feed('gdp_yoy',[('202501','1.23'),('202502','2.34')])
        self.assertEqual(self.db.execute("SELECT value FROM economic_observations WHERE period='2025-Q2'").fetchone()[0],'2.34')
        with self.assertRaises(ValueError):economy.parse(BY_ID['gdp_yoy'],[dict(id='6561',resultados=[dict(series=[dict(localidade=dict(id='2'),serie={})])])])
    def test_deduplication_revisions_and_ten_minute_due(self):
        payload=self.feed('ipca_month',[('202501','0.12')])
        due=self.db.execute('SELECT next_due FROM economic_jobs').fetchone()[0]
        self.assertGreaterEqual(due,time.time()+590)
        self.db.execute('UPDATE economic_jobs SET next_due=0');self.db.commit()
        economy.step(self.db,fetcher=lambda _:payload)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM economic_revisions').fetchone()[0],1)
        self.db.execute('UPDATE economic_jobs SET next_due=0');self.db.commit()
        payload[0]['resultados'][0]['series'][0]['serie']['202501']='0.13'
        economy.step(self.db,fetcher=lambda _:payload)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM economic_revisions').fetchone()[0],2)
    def test_failure_keeps_last_observation_and_retries(self):
        self.feed('ipca_month',[('202501','0.12')]);self.db.execute('UPDATE economic_jobs SET next_due=0');self.db.commit()
        def fail(_):raise TimeoutError('do not leak private connection details')
        economy.step(self.db,fetcher=fail)
        self.assertEqual(self.db.execute('SELECT value FROM economic_observations').fetchone()[0],'0.12')
        d=economy.snapshot(self.db,dict(indicator='ipca_month'))
        self.assertEqual(d['items'][0]['source_status'],'retry');self.assertNotIn('private',json.dumps(d))
    def test_invalid_contract_no_partial_import(self):
        self.job('selic');economy.step(self.db,fetcher=lambda _:[dict(data='01/01/2025',valor='5'),dict(data='invalid',valor='bad')])
        self.assertEqual(self.db.execute('SELECT count(*) FROM economic_observations').fetchone()[0],0)
    def test_ssrf_and_period_bounds(self):
        for url in ['http://api.bcb.gov.br/','https://api.bcb.gov.br@evil.test/','https://127.0.0.1/']:
            with self.assertRaises(ValueError):economy.validate_url(url)
        self.assertEqual(economy.period_bounds('2024-02'),('2024-02-01','2024-02-29'))
        self.assertEqual(economy.period_bounds('2024-Q2'),('2024-04-01','2024-06-30'))
    def test_snapshot_filters_complete_periods_and_no_publication_invention(self):
        self.feed('gdp_yoy',[('202501','1'),('202502','2')])
        d=economy.snapshot(self.db,dict(indicator='gdp_yoy',start='2025-02-01'))['items'][0]
        self.assertEqual(len(d['observations']),1);self.assertIsNone(d['latest']['published_at'])
    def test_governments_equivalent_periods_and_gaps(self):
        self.feed('ipca_12m',[(f'{y}{m:02}','5') for y in [2019,2023] for m in range(1,13)])
        d=governments.compare(self.db,dict(mode='first'),today=__import__('datetime').date(2024,1,1))
        self.assertEqual([r['periods_requested'] for r in d['results']],[12,12]);self.assertTrue(all(r['complete'] for r in d['results']))
        self.db.execute("DELETE FROM economic_observations WHERE indicator='ipca_12m' AND period='2023-05'");self.db.commit()
        d=governments.compare(self.db,dict(mode='first'),today=__import__('datetime').date(2024,1,1))
        self.assertIsNone(d['results'][1]['summary'])
    def test_full_mandates_with_different_duration_rejected(self):
        self.feed('ipca_12m',[('202512','5')])
        with self.assertRaises(ValueError):governments.compare(self.db,dict(mode='full'),today=__import__('datetime').date(2025,12,31))
    def test_ranking_deduplicates_and_never_calls_stage_a_law(self):
        p=upsert(self.db,'camara','person','1','https://dadosabertos.camara.leg.br/api/v2/deputados/1',{},dict(name='Pessoa de teste',party='TESTE',uf='SC',search='pessoa'))
        proposal=save_proposal(self.db,'camara',dict(id=2,siglaTipo='PL',numero=1,ano=2025,ementa='Teste',dataApresentacao='2025-01-01'),'https://dadosabertos.camara.leg.br/api/v2/proposicoes')
        link_author(self.db,proposal,p,'coauthor','https://dadosabertos.camara.leg.br/api/v2/proposicoes/2/autores');self.db.commit()
        self.assertEqual(rankings.query(self.db,dict(metric='projects'))['items'][0]['value'],1)
        self.assertEqual(rankings.query(self.db,dict(metric='laws'))['items'],[])
        party=rankings.query(self.db,dict(group='party'))['items'][0]
        self.assertIsNone(party['proposals']);self.assertEqual(party['records'],1)
    def test_export_formats_preserve_all_rows_and_formulas_safe(self):
        rows=[dict(id=i,value='=1+1',source='https://www.ibge.gov.br/') for i in range(125)]
        b,_=export('Teste',rows,dict(methodology='Amostra de teste'),'csv')
        parsed=list(csv.reader(io.StringIO(b.decode('utf-8-sig')),delimiter=';'));self.assertEqual(len(parsed),129);self.assertEqual(parsed[-1][1],"'=1+1")
        b,_=export('Teste',rows,{},'json');self.assertEqual(len(json.loads(b)['items']),125)
        b,_=export('Teste',rows,{},'xlsx')
        with zipfile.ZipFile(io.BytesIO(b)) as z:self.assertIsNone(z.testzip());self.assertIn('inlineStr',z.read('xl/worksheets/sheet1.xml').decode())
        self.assertTrue(export('Teste',rows,{},'pdf')[0].startswith(b'%PDF'))
        with self.assertRaises(ValueError):export('Teste',[{}]*1001,{},'pdf')
        with self.assertRaises(ValueError):export('Teste',[{}]*10001,{},'json')
    def test_source_checks_cache_and_ten_minute_interval(self):
        source_monitor.seed(self.db);source_monitor.step(self.db,fetcher=lambda url,headers:dict(status=200,etag='v1'),stamp=1000)
        row=self.db.execute("SELECT * FROM scheduled_source_checks WHERE status='available'").fetchone();self.assertEqual(row['next_due'],1600)
        public=source_monitor.status(self.db);self.assertNotIn('lease_token',public['sources'][0])
    def test_history_jobs_are_leased_idempotent_and_do_not_fake_freshness(self):
        self.db.execute("INSERT INTO economic_backfill_jobs(indicator,year) VALUES('selic',2020)");self.db.commit()
        payload=[dict(data='02/01/2020',valor='4.5')]
        self.assertTrue(economy.step_history(self.db,fetcher=lambda _:payload))
        self.assertFalse(economy.step_history(self.db,fetcher=lambda _:payload))
        self.assertEqual(self.db.execute('SELECT count(*) FROM economic_observations').fetchone()[0],1)
        d=economy.snapshot(self.db,dict(indicator='selic'))['items'][0]
        self.assertEqual(d['status'],'stale');self.assertIsNone(d['last_success'])
    def test_public_connection_does_not_run_schema_migrations(self):
        path=Path(self.tmp.name)/'read.db'
        with connect(path) as d:d.execute("INSERT INTO tenants VALUES('keep','Preservar')");d.commit()
        with connect(path,migrate=False) as d:self.assertEqual(d.execute('SELECT name FROM tenants').fetchone()[0],'Preservar')
    def test_full_record_export_contains_more_than_one_page(self):
        for n in range(125):upsert(self.db,'camara','person',str(n),'https://dadosabertos.camara.leg.br/api/v2/deputados/'+str(n),{},dict(name='Pessoa de teste',search='teste'))
        self.db.commit();title,rows,meta=analytics.dataset(self.db,'records',dict(kind='person'))
        self.assertEqual(len(rows),125)
    def test_revisions_are_public_facts_and_laws_are_not_inferred(self):
        self.feed('ipca_month',[('202501','0.12')])
        d=economy.revisions(self.db,dict(indicator='ipca_month',period='2025-01'))
        self.assertEqual(d['items'][0]['value'],'0.12');self.assertIsNone(d['items'][0]['published_at'])
        d=analytics.answer(self.db,dict(q='Quantos projetos do senador viraram lei?'))
        self.assertEqual(d['kind'],'unavailable');self.assertEqual(d['facts'],[])
    def test_guided_answer_only_uses_stored_facts(self):
        self.feed('ipca_12m',[('202501','5.25')])
        answer=analytics.answer(self.db,dict(q='Qual a inflação?'));self.assertIn('5.25',answer['text']);self.assertTrue(answer['links'][0].startswith('https://'))
        self.assertEqual(analytics.answer(self.db,dict(q='Qual o melhor presidente?'))['kind'],'unsupported')
