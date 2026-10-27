"""Equivalent-period comparisons. No score or attribution of economic causality."""
from datetime import date,timedelta
from decimal import Decimal
from .economy import snapshot,period_bounds
from .calculations import number,text,change,deflate

SOURCE='https://www.biblioteca.presidencia.gov.br/presidencia/ex-presidentes'
TERMS=[
 dict(id=k,name=n,start=s,end=e,party=p,source_url=u,context=c,photo=None)
 for k,n,s,e,p,u,c in [
 ('fhc1','Fernando Henrique Cardoso — 1º mandato','1995-01-01','1998-12-31','PSDB',SOURCE+'/fernando-henrique-cardoso',''),
 ('fhc2','Fernando Henrique Cardoso — 2º mandato','1999-01-01','2002-12-31','PSDB',SOURCE+'/fernando-henrique-cardoso',''),
 ('lula1','Luiz Inácio Lula da Silva — 1º mandato','2003-01-01','2006-12-31','PT',SOURCE+'/luiz-inacio-lula-da-silva',''),
 ('lula2','Luiz Inácio Lula da Silva — 2º mandato','2007-01-01','2010-12-31','PT',SOURCE+'/luiz-inacio-lula-da-silva',''),
 ('dilma1','Dilma Rousseff — 1º mandato','2011-01-01','2014-12-31','PT',SOURCE+'/dilma-rousseff',''),
 ('dilma2','Dilma Rousseff — 2º mandato','2015-01-01','2016-08-31','PT','https://www25.senado.leg.br/pt_BR/web/atividade/materias/-/materia/125567','Período formal; afastamento desde 12/05/2016. Os resultados do período não são atribuídos pessoalmente à presidente.'),
 ('temer','Michel Temer — exercício definitivo','2016-08-31','2018-12-31','PMDB / MDB','https://www12.senado.leg.br/institucional/presidencia/noticia/renan-calheiros/renan-calheiros-empossa-michel-temer','Exercício interino anterior a 31/08/2016 não incluído neste recorte. PMDB passou a MDB durante o período.'),
 ('bolsonaro','Jair Bolsonaro','2019-01-01','2022-12-31','PSL / sem partido / PL',SOURCE+'/bolsonaro','Mudanças de filiação durante o mandato; a sigla atual não retroage.'),
 ('lula3','Luiz Inácio Lula da Silva — 3º mandato','2023-01-01',None,'PT','https://www.gov.br/planalto/pt-br/conheca-a-presidencia/biografia-do-presidente','Mandato em andamento. Comparação limitada aos períodos completos com dados publicados.')]]

def month_keys(start,end,frequency):
    s=date.fromisoformat(start);e=date.fromisoformat(end);keys=[]
    if frequency=='annual':candidates=[str(y) for y in range(s.year,e.year+1)]
    elif frequency=='quarterly':candidates=[f'{y}-Q{q}' for y in range(s.year,e.year+1) for q in range(1,5)]
    else:candidates=[f'{y}-{m:02}' for y in range(s.year,e.year+1) for m in range(1,13)]
    for p in candidates:
        a,b=period_bounds(p)
        if a>=start and b<=end:keys.append(p)
    return keys

def compare(db,params,today=None):
    today=today or date.today();requested=params.get('terms','bolsonaro,lula3').split(',')
    if not 2<=len(requested)<=6 or len(set(requested))!=len(requested):raise ValueError('Selecione de dois a seis mandatos distintos')
    terms={x['id']:x for x in TERMS}
    if any(k not in terms for k in requested):raise ValueError('Mandato inválido')
    mode=params.get('mode','equivalent');price=params.get('price','nominal')
    if mode not in {'equivalent','first','last','full'} or price not in {'nominal','corrected'}:raise ValueError('Comparação inválida')
    indicator=params.get('indicator','ipca_12m');dataset=snapshot(db,dict(indicator=indicator))
    if not dataset['items']:raise ValueError('Indicador inválido')
    definition=dataset['items'][0];observations=definition['observations'];mapping={}
    for row in observations:
        p=row['period'][:7] if definition['frequency']=='daily' else row['period']
        mapping[p]=row # Daily series: last published value in each closed month.
    frequency='monthly' if definition['frequency']=='daily' else definition['frequency']
    ref_indexes={r['period']:r for r in snapshot(db,dict(indicator='ipca_index'))['items'][0]['observations']}
    reference=max(ref_indexes) if ref_indexes else None
    ranges=[]
    # Only periods closed before today, no extrapolation through unpublished months.
    for key in requested:
        t=terms[key];end=min(t['end'] or today.isoformat(),(today-timedelta(days=1)).isoformat())
        keys=month_keys(t['start'],end,frequency)
        available_end=max(mapping,default='')
        keys=[p for p in keys if p<=available_end]
        year_size=1 if frequency=='annual' else 4 if frequency=='quarterly' else 12
        if mode=='first':keys=keys[:year_size]
        elif mode=='last':keys=keys[-year_size:]
        ranges.append((t,keys))
    n=min((len(keys) for _,keys in ranges),default=0)
    if mode in {'equivalent','first','last'}:ranges=[(t,keys[-n:] if mode=='last' and n else keys[:n]) for t,keys in ranges]
    elif len({len(keys) for _,keys in ranges})>1:
        raise ValueError('Mandatos com durações diferentes: use períodos equivalentes')
    results=[]
    for term,keys in ranges:
        rows=[];missing=[]
        for key in keys:
            row=mapping.get(key)
            if row is None:missing.append(key);continue
            row=dict(row);row['official_value']=row['value']
            if price=='corrected':
                # Express purchasing power using the index at the end of each reference period.
                # This convention is explicit; it does not reconstruct intra-period production.
                index_period=period_bounds(row['period'])[1][:7]
                if definition['unit'] not in {'Reais','Milhões de reais'} or index_period not in ref_indexes or not reference:
                    missing.append(key);continue
                row['value']=deflate(row['value'],ref_indexes[index_period]['value'],ref_indexes[reference]['value'])
                row['deflator_period']=index_period
            rows.append(row)
        complete=bool(keys) and not missing
        values=[number(r['value']) for r in rows];summary=None
        if complete:
            total=sum(values,Decimal(0));summary=dict(first=rows[0]['value'],last=rows[-1]['value'],mean=text(total/len(values)),change=change(rows[-1]['value'],rows[0]['value'],definition['kind']=='rate'),sum=text(total) if definition['kind']=='flow' else None)
            if indicator=='ipca_month':
                compounded=Decimal(1)
                for v in values:compounded*=1+v/100
                summary['cumulative_inflation']=text((compounded-1)*100)
        results.append(dict(term=term,periods_requested=len(keys),periods_found=len(rows),missing_periods=missing,
          complete=complete,summary=summary,series=rows,duration_days=(date.fromisoformat(term['end'] or today.isoformat())-date.fromisoformat(term['start'])).days+1))
    return dict(indicator={k:v for k,v in definition.items() if k!='observations'},terms=TERMS,results=results,mode=mode,price=price,deflator=dict(indicator='ipca_index',reference=reference,methodology='valor nominal × IPCA da referência / IPCA do fim do período original; convenção de poder de compra ao fim de cada período, não PIB em volume') if price=='corrected' else None,
      methodology='Períodos completos inteiramente contidos no mandato formal. Lacunas impedem totalizações. Séries diárias usam o último valor publicado em cada mês fechado; médias são médias aritméticas das observações selecionadas. Fluxos podem ser somados; taxas, estoques e índices não. Não há ranking de melhor governo nem atribuição causal. Fatores externos, políticas anteriores, Congresso e Banco Central também influenciam resultados.',
      unavailable=['Leis sancionadas com atribuição conferida','Vetos presidenciais','Decretos','Medidas provisórias','Execução orçamentária','Investimento público comparável'])
