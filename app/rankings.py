"""Observed counts within one institution, with explicit coverage limitations."""
import json
from datetime import date
from .automatic import PROJECT_TYPES
from .calculations import ratio
from .financial import money

def query(db,params):
    source=params.get('source','camara');metric=params.get('metric','proposals');group=params.get('group','person')
    if source not in {'camara','senado','alesc'} or group not in {'person','party'}:raise ValueError('Casa inválida')
    if metric not in {'proposals','projects','approved_stage','votes','expenses','laws','reports','attendance'}:raise ValueError('Métrica inválida')
    start=params.get('start','');end=params.get('end','');year=params.get('year','')
    for v in (start,end):
        if v:date.fromisoformat(v)
    if year:
        y=int(year)
        if not 1800<=y<=date.today().year:raise ValueError('Ano inválido')
        start=max(start or f'{y}-01-01',f'{y}-01-01');end=min(end or f'{y}-12-31',f'{y}-12-31')
    if start and end and start>end:raise ValueError('Período inválido')
    people=[]
    for r in db.execute("SELECT id,url,data,collected_at FROM records WHERE kind='person' AND source=?",(source,)):
        d=json.loads(r['data']);name=d.get('name','');party=d.get('party')
        if params.get('q','').casefold() not in name.casefold():continue
        if params.get('party') and params['party']!=party:continue
        if params.get('uf') and params['uf'].upper()!=d.get('uf'):continue
        people.append(dict(id=r['id'],name=name,party=party,uf=d.get('uf'),url=r['url'],collected_at=r['collected_at']))
    note='Contagens apenas dos documentos coletados, não de toda a atividade. Mesma Casa e mesmo período; a ordem não mede qualidade ou mérito. Zero significa nenhum registro encontrado nesta base. Filtro de partido seleciona o cadastro disponível e não atribui produção histórica à sigla.'
    if group=='party':
        groups={}
        for p in people:
            k=p['party'] or 'Partido não informado';g=groups.setdefault(k,dict(party=k,records=0,ufs={},proposals=None,approved=None,laws=None,normalized=None,expenses=None))
            g['records']+=1;uf=p['uf'] or 'Não informada';g['ufs'][uf]=g['ufs'].get(uf,0)+1
        return dict(items=sorted(groups.values(),key=lambda x:(-x['records'],x['party'])),total=len(groups),source=source,metric='collected_profiles',
          methodology='Agrupamento dos cadastros coletados por sigla informada. Não representa necessariamente a bancada atual. Produção, despesas históricas e médias por mandato não são atribuídas sem filiação válida na data de cada ato. Propostas com vários autores não são somadas para atribuir produção partidária.',
          unavailable=['Filiação histórica com vigência','Produção por partido no período','Normalização por tempo efetivo de mandato'],filters=params)
    if metric in {'laws','reports','attendance'} or source=='alesc' and metric!='expenses':
        return dict(items=[],total=0,source=source,metric=metric,methodology=note,unavailable=['Dado oficial indisponível para este indicador e Casa.'],filters=params)
    counts={};extra={}
    if metric=='expenses':
        component=params.get('component','cota');nature=(params.get('nature') or ('DEBITADO_COTA' if source=='camara' else 'REEMBOLSADO' if source=='senado' else 'AUTORIZADO'))
        if source=='alesc':component='diarias'
        valid={'camara':('cota',{'DEBITADO_COTA','ESTORNADO'}),'senado':('cota',{'REEMBOLSADO','ESTORNADO'}),'alesc':('diarias',{'AUTORIZADO'})}
        if component!=valid[source][0] or nature not in valid[source][1]:raise ValueError('Separe tipos e situações de gasto')
        clauses=["source_id=?","verification='confirmed'","person_id IS NOT NULL","component=?","nature=?"]
        args=[{'camara':'camara_ceap','senado':'senado_ceaps','alesc':'alesc_travel'}[source],component,nature]
        if start:clauses.append("printf('%04d-%02d-01',year,month)>=?");args.append(start)
        if end:clauses.append("date(printf('%04d-%02d-01',year,month),'+1 month','-1 day')<=?");args.append(end)
        for r in db.execute('SELECT person_id,SUM(amount_cents) amount,COUNT(*) n FROM parliamentary_expenses WHERE '+' AND '.join(clauses)+' GROUP BY person_id',args):counts[r['person_id']]=r['amount'];extra[r['person_id']]=r['n']
        note+=' Despesas confirmadas da mesma natureza e competência, sem parcelas institucionais pendentes. Não é custo total. Ajustes negativos são listados separadamente. Meses parciais nos filtros são excluídos.'
    elif metric=='votes':
        if source=='senado':return dict(items=[],total=0,source=source,metric=metric,methodology=note,unavailable=['Votos nominais do Senado ainda não disponíveis.'],filters=params)
        clauses=['person_id LIKE ?'];args=[source+':person:%']
        if start:clauses.append('substr(vote_date,1,10)>=?');args.append(start)
        if end:clauses.append('substr(vote_date,1,10)<=?');args.append(end)
        for r in db.execute('SELECT person_id,COUNT(DISTINCT vote_id) n FROM nominal_votes WHERE '+' AND '.join(clauses)+' GROUP BY person_id',args):counts[r['person_id']]=r['n']
        note+=' Contagem de votos nominais disponíveis; não é percentual de presença. O universo de votações elegíveis não foi apurado.'
    else:
        clauses=['f.source=?'];args=[source]
        if start:clauses.append('substr(f.presented_at,1,10)>=?');args.append(start)
        if end:clauses.append('substr(f.presented_at,1,10)<=?');args.append(end)
        if metric in {'projects','approved_stage'}:
            clauses.append('f.type IN ('+','.join('?' for _ in PROJECT_TYPES)+')');args+=sorted(PROJECT_TYPES)
        if metric=='approved_stage':clauses.append('EXISTS(SELECT 1 FROM approval_evidence e WHERE e.proposal_id=f.proposal_id)')
        sql='SELECT a.person_id,COUNT(DISTINCT a.proposal_id) n FROM authorships a JOIN proposal_facts f ON f.proposal_id=a.proposal_id WHERE '+' AND '.join(clauses)+' GROUP BY a.person_id'
        for r in db.execute(sql,args):counts[r['person_id']]=r['n']
        if metric=='approved_stage':note+=' Aprovação em alguma etapa, comprovada por evento da Casa. Não é aprovação final nem lei.'
        note+=' Propostas são distintas por parlamentar; coautoria pode aparecer em mais de um perfil. Não somar a coluna para obter propostas únicas da Casa.'
    items=[]
    for p in people:
        value=counts.get(p['id'],0);p.update(value=money(value) if metric=='expenses' else value,raw_value=value,unit='Reais' if metric=='expenses' else 'Registros observados',records=extra.get(p['id']),approval_rate=None,per_year=None)
        items.append(p)
    items.sort(key=lambda p:(-p['raw_value'],p['name']))
    rank=0;previous=None
    for i,p in enumerate(items,1):
        if p['raw_value']!=previous:rank=i
        previous=p.pop('raw_value');p['position']=rank
    return dict(items=items,total=len(items),source=source,metric=metric,methodology=note,filters=params,
      unavailable=['Taxa de aprovação final','Produção por tempo efetivo de mandato','Participação percentual em sessões elegíveis','Filtros de município e legislatura sem histórico validado'])
