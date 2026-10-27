"""Read-only orchestration of the added modules, preserving existing endpoints."""
import json
from . import economy,governments,rankings,productivity
from .db import now,search

def dataset(db,kind,params):
    if kind=='economy':
        d=economy.snapshot(db,params);rows=[]
        for item in d['items']:
            for r in item['observations']:rows.append(dict(indicator=item['name'],agency=item['agency'],methodology=item['methodology'],**r))
        return 'Brasil em números',rows,dict(filters=params,methodology=d['methodology'],availability=[dict(indicator=i['name'],status=i['status']) for i in d['items']])
    if kind=='governments':
        d=governments.compare(db,params);rows=[]
        for r in d['results']:
            for point in r['series']:rows.append(dict(government=r['term']['name'],mandate_start=r['term']['start'],mandate_end=r['term']['end'],comparison_complete=r['complete'],**point))
        return 'Comparativo de Governos Presidenciais',rows,dict(filters=params,methodology=d['methodology'],deflator=d['deflator'],summaries=[dict(term=r['term']['name'],complete=r['complete'],summary=r['summary']) for r in d['results']])
    if kind=='rankings':
        d=rankings.query(db,params)
        return 'Cadastros por partido' if params.get('group')=='party' else 'Atividade parlamentar observada',d['items'],dict(filters=params,methodology=d['methodology'],unavailable=d['unavailable'])
    if kind=='politician':
        d=productivity.dashboard(db,params.get('id',''),params.get('start',''),params.get('end',''),1,10000,params.get('category','all'),export=True)
        rows=[dict(id=r['id'],title=r['data'].get('name'),description=r['data'].get('description'),presented_at=r['presented_at'],relation=r['relation'],status=r['proposal_status'],source_url=r['url'],collected_at=r['collected_at'],evidence=r['evidence']) for r in d['items']]
        return 'Atividade de '+d['person']['data']['name'],rows,dict(filters=params,methodology=d['methodology'],metrics=d['metrics'])
    if kind=='records':
        kind_=params.get('kind','person')
        if kind_ not in {'person','proposal','vote','document'}:raise ValueError('Tipo inválido')
        args={k:params.get(k,'') for k in ['q','source','uf','party','year']};first=search(db,kind=kind_,size=100,**args)
        if first['total']>10000:raise ValueError('Refine os filtros para até 10000 registros')
        rows=first['items']
        for page in range(2,(first['total']+99)//100+1):rows+=search(db,kind=kind_,page=page,size=100,**args)['items']
        return 'Registros oficiais coletados',rows,dict(filters=params,methodology='Seleção filtrada completa, com limite explícito de 10000 registros. Cobertura parcial; cada registro inclui fonte e data da coleta.')
    raise ValueError('Relatório inválido')

def answer(db,params):
    q=params.get('q','').strip().casefold()
    if not q or len(q)>300:raise ValueError('Informe uma pergunta de até 300 caracteres')
    if any(t in q for t in ('viraram lei','virou lei','leis aprovadas','leis sancionadas')):
        return dict(kind='unavailable',text='A publicação das leis ainda não foi conferida por esta ferramenta. Projetos apresentados, aprovação em uma etapa e norma informada pela Casa são contagens diferentes. Abra o perfil do parlamentar para consultar as evidências disponíveis.',facts=[],links=['#produtividade'],limitations=['Não é possível informar uma quantidade de leis publicadas sem a conferência documental correspondente.'])
    if any(t in q for t in ('mais projetos','mais proposições','partido','deputados','senadores')):
        p=dict(source='senado' if 'senador' in q else 'camara',metric='projects',group='party' if 'partido' in q else 'person')
        d=rankings.query(db,p);items=d['items'][:5]
        return dict(kind='structured_query',text='Consulta dos documentos disponíveis, com cobertura parcial. '+d['methodology'],facts=items,links=[r['url'] for r in items if r.get('url')],limitations=d['unavailable'])
    indicator=next((k for word,k in [('inflação','ipca_12m'),('inflacao','ipca_12m'),('pib','gdp_yoy'),('desemprego','unemployment'),('selic','selic'),('dívida','gross_debt_gdp'),('divida','gross_debt_gdp'),('reservas','reserves')] if word in q),None)
    if indicator:
        if any(word in q for word in ('compare','comparar','governo','mandato')):
            return dict(kind='guided_query',text='Escolha os mandatos e os períodos no comparativo de governos. Não atribuímos os resultados econômicos automaticamente ao presidente.',facts=[],links=['#governos'],limitations=['A pergunta não informa todos os filtros necessários para uma comparação verificável.'])
        d=economy.snapshot(db,dict(indicator=indicator))['items'][0];last=d['latest']
        return dict(kind='structured_query',text=d['name']+': '+(last['value']+' '+d['unit']+'; referência '+last['period'] if last else 'Dado oficial indisponível')+'. '+d['methodology'],facts=[last] if last else [],links=[last['source_url'] if last else d['url']],limitations=[d['publication_note'],'Status da consulta: '+d['status']])
    return dict(kind='unsupported',text='Não há informação suficiente para responder com segurança. Você pode consultar PIB, inflação, desemprego, Selic, dívida, reservas ou a atividade parlamentar observada.',facts=[],links=['#economia','#ranking'],limitations=['Consulta guiada a dados estruturados; não usa geração de texto por IA nem cria indicadores.'])
