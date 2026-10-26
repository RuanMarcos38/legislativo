import csv,io,json,tempfile,time,unittest,zipfile
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from app.db import connect,upsert
from app import financial as f
from app.financial_exports import xlsx_export,pdf_export

class Financial(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=connect(Path(self.tmp.name)/'test.db')
        with patch.dict('os.environ',{'FINANCIAL_START_YEAR':'2026'}):f.seed(self.db)
        self.row=dict(id=2283505,tipoDocumento='Nota Fiscal',ano=2026,mes=3,codSenador=6338,nomeSenador='TERESA LEITÃO',tipoDespesa='Aluguel de imóveis para escritório político',cpfCnpj='10.835.932/0001-08',fornecedor='COMPANHIA ENERGETICA DE PERNAMBUCO',documento='401210844',data='2026-03-09',detalhamento=None,valorReembolsado=Decimal('440.5'))
        self.url=f.SENADO+'2026'
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def put(self,row=None):
        r=f.normalized(self.db,'senado_ceaps',row or self.row,self.url);f.save(self.db,r,None);self.db.commit();return r
    def job(self):
        self.db.execute("UPDATE financial_sync_jobs SET next_due=? WHERE source_id<>'senado_ceaps'",(time.time()+10000,));self.db.commit()
    def body(self,rows):return json.dumps(rows,default=str).encode()
    def test_exact_decimal_and_zero_unknown(self):
        self.assertEqual(f.cents('0.10')+f.cents('0.20'),30)
        self.assertEqual(f.cents('0'),0);self.assertIsNone(f.cents(''));self.assertIsNone(f.cents(None))
        self.assertEqual(f.cents('1.078,00',True),107800)
        for v in [0.1,'NaN','1.001','1e3',True,'1,2']:
            with self.assertRaises(ValueError):f.cents(v)
    def test_official_sample_reconciles_exactly(self):
        self.put();d=f.query(self.db,{'person':'senado:person:6338','year':'2026'})
        self.assertEqual(d['totals'][0]['amount'],'440.50');self.assertEqual(d['items'][0]['original_amount'],'440.5')
        self.assertEqual(d['items'][0]['source_url'],self.url)
        self.assertIsNone(d['items'][0]['payment_date']);self.assertIsNone(d['items'][0]['mandate'])
    def test_idempotence_and_corrections_preserve_history(self):
        self.put();self.put();self.assertEqual(self.db.execute('select count(*) from financial_audit_logs').fetchone()[0],1)
        self.put(dict(self.row,valorReembolsado=Decimal('441.51')))
        self.assertEqual(self.db.execute('select count(*) from parliamentary_expenses').fetchone()[0],1)
        self.assertEqual(self.db.execute('select count(*) from financial_audit_logs').fetchone()[0],2)
        self.assertEqual(f.query(self.db,{})['totals'][0]['amount'],'441.51')
    def test_negative_adjustment_not_new_positive_expense(self):
        self.put();self.put(dict(self.row,id=2283506,valorReembolsado=Decimal('-40.50')))
        d=f.query(self.db,{});self.assertEqual({t['nature']:t['amount'] for t in d['totals']},{'REEMBOLSADO':'440.50','ESTORNADO':'-40.50'})
    def test_missing_value_never_zero(self):
        self.put(dict(self.row,valorReembolsado=None));d=f.query(self.db,{})
        self.assertEqual(d['totals'],[]);self.assertIsNone(d['items'][0]['amount']);self.assertEqual(d['items'][0]['verification'],'unavailable')
        self.assertIn(f.MISSING,f.csv_export(d))
    def test_supplier_ids_minimized(self):
        r=self.put();self.assertNotIn('cpfCnpj',r['raw']);self.assertNotIn('raw',f.query(self.db,{})['items'][0])
    def test_public_financial_facts_do_not_expose_tenants(self):
        self.put();s=json.dumps(f.query(self.db,{}),ensure_ascii=False)
        for key in ['password_hash','csrf','tenant_id','email']:self.assertNotIn(key,s)
    def test_filters_and_sql_injection(self):
        self.put();self.assertEqual(f.query(self.db,{'person':'senado:person:6338','month':'3','supplier':'ENERGETICA'})['total'],1)
        self.assertEqual(f.query(self.db,{'month':'4'})['total'],0)
        self.assertEqual(f.query(self.db,{'q':"' OR 1=1 --"})['total'],0)
        for params in [{'month':'13'},{'year':'1999'},{'page':'0'},{'size':'1000'}]:
            with self.assertRaises(ValueError):f.query(self.db,params)
    def test_portuguese_accent_case_in_name_filter(self):
        self.put()
        self.assertEqual(f.query(self.db,{'q':'Teresa Leitão'})['total'],1)
        self.assertEqual(f.query(self.db,{'q':'teresa leitão'})['total'],1)
    def test_source_and_receipt_allowlist(self):
        for u in ['http://www.camara.leg.br/cotas/a','https://localhost/a','https://www.camara.leg.br.evil.test/cotas/a','https://user:pass@www.camara.leg.br/cotas/a','https://www.camara.leg.br:444/cotas/a','https://www.camara.leg.br/unrelated']:
            with self.assertRaises(ValueError):f.validate_url(u)
        self.assertIsNone(f.receipt_url('javascript:alert(1)'));self.assertIsNone(f.receipt_url('https://evil.test/a'))
    def test_failed_sync_preserves_confirmed_data(self):
        self.put();self.job();f.step(self.db,fetcher=lambda u:(_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(f.query(self.db,{})['totals'][0]['amount'],'440.50')
        r=self.db.execute("select state,last_success from financial_sync_jobs where source_id='senado_ceaps'").fetchone()
        self.assertEqual(r['state'],'retry');self.assertIsNone(r['last_success'])
    def test_import_and_reconciliation(self):
        self.job();f.step(self.db,fetcher=lambda u:(self.body([self.row]),'Mon, 26 Oct 2026 00:00:00 GMT'))
        self.assertEqual(f.query(self.db,{})['total'],1)
        self.assertEqual(self.db.execute('select expected_rows,persisted_rows from financial_reconciliations').fetchone()[:],(1,1))
        self.assertEqual(self.db.execute("select state from financial_sync_jobs where source_id='senado_ceaps'").fetchone()[0],'complete')
    def test_lease_prevents_stale_worker_commit(self):
        self.job()
        def fetcher(u):
            self.db.execute("update financial_sync_jobs set lease_token='other' where source_id='senado_ceaps'");self.db.commit()
            return self.body([self.row]),None
        f.step(self.db,fetcher=fetcher);self.assertEqual(f.query(self.db,{})['total'],0)
    def test_atomic_rollback_invalid_record(self):
        self.job();f.step(self.db,fetcher=lambda u:(self.body([self.row,dict(self.row,id=2,mes=13)]),None))
        self.assertEqual(f.query(self.db,{})['total'],0);self.assertEqual(self.db.execute('select count(*) from financial_import_batches').fetchone()[0],0)
    def test_migrations_repeat_and_keep_existing_data(self):
        upsert(self.db,'camara','person','123','https://dadosabertos.camara.leg.br/api/v2/deputados/123',{'nome':'Anterior'},{'name':'Anterior','search':'anterior'});self.db.commit()
        with connect(Path(self.tmp.name)/'test.db') as db:self.assertEqual(db.execute("select count(*) from records where id='camara:person:123'").fetchone()[0],1)
        self.assertEqual(self.db.execute('pragma integrity_check').fetchone()[0],'ok')
    def test_camara_document_glosa_and_multiple_entries(self):
        row=dict(ideCadastro='62881',txNomeParlamentar='Danilo Forte',ideDocumento='8158134',numLote='2265923',numRessarcimento='',numParcela='0',numAno='2026',numMes='8',vlrDocumento='117.72',vlrGlosa='0',vlrLiquido='117.72',txtDescricao='MANUTENÇÃO DE ESCRITÓRIO',codLegislatura='57',txtFornecedor='ALARES INTERNET S/A')
        r=f.normalized(self.db,'camara_ceap',row,'https://www.camara.leg.br/cotas/Ano-2026.csv.zip')
        self.assertEqual(r['amount_cents'],11772);self.assertEqual(r['nature'],'DEBITADO_COTA');self.assertEqual(r['mandate'],'57')
        self.assertNotEqual(r['id'],f.normalized(self.db,'camara_ceap',dict(row,numLote='999'),'https://www.camara.leg.br/cotas/Ano-2026.csv.zip')['id'])
        self.assertEqual(f.normalized(self.db,'camara_ceap',dict(row,vlrGlosa='1'),r['source_url'])['verification'],'pending')
        self.assertEqual(f.normalized(self.db,'camara_ceap',dict(row,vlrRestituicao='117.72'),r['source_url'])['verification'],'pending')
    def test_mandates_are_not_guessed_or_merged(self):
        r=self.put();self.assertIsNone(r['mandate']);self.assertEqual(f.query(self.db,{'mandate':'57'})['total'],0)
        self.assertEqual(f.query(self.db,{'person':'camara:person:6338'})['total'],0)
    def test_alesc_explicit_deputy_not_staff(self):
        row={'Nome':'IVAN NAATZ','Conta':'15739','Vínculo':'Deputado','Data':'23/10/2026','Valor':'1.078,00','Relatório':'https://diarias.alesc.sc.gov.br/prestacao-contas/164115'}
        r=f.normalized(self.db,'alesc_travel',row,'https://transparencia.alesc.sc.gov.br/diarias/csv/2026')
        self.assertEqual(r['person_id'],'alesc:person:15739');self.assertEqual(r['nature'],'AUTORIZADO');self.assertEqual(r['amount_cents'],107800)
        other=f.normalized(self.db,'alesc_travel',dict(row,Vínculo='Servidor'),r['source_url'])
        self.assertIsNone(other['person_id']);self.assertEqual(other['verification'],'pending')
    def test_export_excel_and_pdf_sources_and_precision(self):
        self.put();d=f.query(self.db,{},export=True);csvbody=f.csv_export(d);self.assertIn('440.50',csvbody);self.assertIn(self.url,csvbody)
        x=xlsx_export(d)
        with zipfile.ZipFile(io.BytesIO(x)) as z:
            sheet=z.read('xl/worksheets/sheet1.xml').decode();self.assertIn('440.50',sheet);self.assertIn(self.url,sheet);self.assertNotIn('<f>',sheet)
        pdf=pdf_export(d);self.assertTrue(pdf.startswith(b'%PDF-1.4'));self.assertIn(b'440.50',pdf);self.assertIn(self.url.encode(),pdf)
    def test_csv_formula_injection(self):
        self.put(dict(self.row,fornecedor='=HYPERLINK("bad")'))
        text=f.csv_export(f.query(self.db,{},export=True));self.assertIn("'=HYPERLINK",text)
    def test_empty_response_is_coverage_not_zero_spending(self):
        self.job();f.step(self.db,fetcher=lambda u:(b'[]',None));d=f.query(self.db,{})
        self.assertEqual(d['totals'],[]);self.assertTrue(d['coverage']['coverage']);self.assertEqual(d['amendments']['items'],[])
    def test_removed_source_record_is_pending_and_audited(self):
        self.put();self.job();f.step(self.db,fetcher=lambda u:(b'[]',None))
        d=f.query(self.db,{});self.assertEqual(d['total'],1);self.assertEqual(d['totals'],[])
        self.assertEqual(d['items'][0]['verification'],'pending')
        self.assertEqual(self.db.execute('select count(*) from financial_audit_logs').fetchone()[0],2)
    def test_read_connection_remains_available_during_writer(self):
        self.put();self.db.execute('BEGIN IMMEDIATE')
        self.db.execute("UPDATE parliamentary_expenses SET supplier='Correção ainda não confirmada'")
        with connect(Path(self.tmp.name)/'test.db') as reader:
            self.assertNotEqual(f.query(reader,{})['items'][0]['supplier'],'Correção ainda não confirmada')
        self.db.rollback()
    def test_camara_api_pagination_and_bulk_share_key(self):
        upsert(self.db,'camara','person','62881',f.CAMARA+'deputados/62881',{'id':62881},{'name':'Danilo Forte','search':'danilo forte'})
        self.db.execute('UPDATE financial_sync_jobs SET next_due=?',(time.time()+10000,))
        key=f.enqueue(self.db,'camara_api',2026,'camara:person:62881');self.db.commit()
        row=dict(codDocumento=8158134,codLote=2265923,numRessarcimento='',parcela=0,ano=2026,mes=8,valorDocumento='117.72',valorGlosa='0',valorLiquido='117.72',tipoDespesa='MANUTENÇÃO DE ESCRITÓRIO')
        nxt=f.CAMARA+'deputados/62881/despesas?ano=2026&itens=100&pagina=2'
        f.step(self.db,fetcher=lambda u:(self.body({'dados':[row],'links':[{'rel':'next','href':nxt}]}),None))
        self.assertEqual(self.db.execute('select cursor from financial_sync_jobs where key=?',(key,)).fetchone()[0],nxt)
        self.db.execute('update financial_sync_jobs set next_due=0 where key=?',(key,));self.db.commit()
        f.step(self.db,fetcher=lambda u:(b'{"dados":[],"links":[]}',None))
        self.assertEqual(self.db.execute('select imported from financial_sync_jobs where key=?',(key,)).fetchone()[0],1)
        api=f.query(self.db,{'source':'camara_ceap'})['items'][0]
        bulk=f.normalized(self.db,'camara_ceap',dict(ideCadastro='62881',txNomeParlamentar='Danilo Forte',ideDocumento='8158134',numLote='2265923',numRessarcimento='',numParcela='0',numAno='2026',numMes='8',vlrDocumento='117.72',vlrGlosa='0',vlrLiquido='117.72',txtDescricao='MANUTENÇÃO DE ESCRITÓRIO'),'https://www.camara.leg.br/cotas/Ano-2026.csv.zip')
        self.assertEqual(api['id'],bulk['id'])
    def test_invalid_pagination_does_not_commit(self):
        upsert(self.db,'camara','person','1',f.CAMARA+'deputados/1',{'id':1},{'name':'Teste','search':'teste'})
        self.db.execute('UPDATE financial_sync_jobs SET next_due=?',(time.time()+10000,));key=f.enqueue(self.db,'camara_api',2026,'camara:person:1');self.db.commit()
        url=f.CAMARA+'deputados/1/despesas?ano=2026&itens=100&pagina=1'
        f.step(self.db,fetcher=lambda u:(self.body({'dados':[],'links':[{'rel':'next','href':url}]}),None))
        self.assertEqual(self.db.execute('select state from financial_sync_jobs where key=?',(key,)).fetchone()[0],'retry')
        self.assertEqual(self.db.execute('select count(*) from financial_import_batches').fetchone()[0],0)

if __name__=='__main__':unittest.main()
