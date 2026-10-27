"""Series definitions verified against official IBGE metadata and BCB catalog."""
IBGE='https://servicodados.ibge.gov.br/api/v3/agregados/'
BCB='https://api.bcb.gov.br/dados/serie/bcdata.sgs.'

def ibge(key,name,table,variable,unit,frequency,kind='rate',classification='',note=''):
    url=IBGE+str(table)+'/periodos/all/variaveis/'+str(variable)+'?localidades=N1[all]'+('&classificacao='+classification if classification else '')
    return dict(id=key,name=name,agency='IBGE',unit=unit,frequency=frequency,kind=kind,url=url,
      metadata_url=IBGE+str(table)+'/metadados',connector='ibge',methodology=note or 'Série oficial nacional. Valores reproduzidos sem estimar lacunas.',favorable='neutral')

def bcb(key,name,code,unit,frequency,kind='stock',note=''):
    return dict(id=key,name=name,agency='Banco Central do Brasil',unit=unit,frequency=frequency,kind=kind,
      url=BCB+str(code)+'/dados',metadata_url='https://www3.bcb.gov.br/sgspub/consultarmetadados/consultarMetadadosSeries.do?method=consultarMetadadosSeriesInternet&hdOidSerieSelecionada='+str(code),
      connector='bcb',methodology=note,favorable='neutral')

CATALOG=[
 ibge('gdp_nominal','PIB nominal trimestral',1846,585,'Milhões de reais','quarterly','flow','11255[90707]','PIB a preços de mercado, valores correntes trimestrais. Variação nominal não mede crescimento real.'),
 ibge('gdp_real','PIB real — índice de volume',1620,583,'Número-índice (média 1995 = 100)','quarterly','index','11255[90707]','Índice de volume encadeado. Não é valor monetário e não deve ser somado.'),
 ibge('gdp_qoq','Crescimento do PIB frente ao trimestre anterior',5932,6564,'%','quarterly','rate','11255[90707]','Taxa trimestre contra trimestre imediatamente anterior, série com ajuste sazonal segundo o IBGE.'),
 ibge('gdp_yoy','Crescimento do PIB frente ao mesmo trimestre do ano anterior',5932,6561,'%','quarterly','rate','11255[90707]'),
 ibge('gdp_annual','Crescimento real anual do PIB',6784,9810,'%','annual'),
 ibge('gdp_per_capita','PIB por pessoa — valores correntes',6784,9812,'Reais','annual','stock'),
 ibge('ipca_month','Inflação IPCA no mês',1737,63,'%','monthly'),
 ibge('ipca_12m','Inflação IPCA em 12 meses',1737,2265,'%','monthly'),
 ibge('ipca_ytd','Inflação IPCA acumulada no ano',1737,69,'%','monthly'),
 ibge('ipca_index','IPCA — índice para correção monetária',1737,2266,'Número-índice (dezembro 1993 = 100)','monthly','index'),
 ibge('unemployment','Taxa de desemprego',6381,4099,'%','monthly','rate','','PNAD Contínua: trimestre móvel encerrado no mês indicado. Meses consecutivos se sobrepõem; não são amostras independentes.'),
 bcb('selic','Meta da taxa Selic',432,'% ao ano','daily','rate','Meta fixada pelo Copom. Não é o juro efetivamente pago em cada operação.'),
 bcb('reserves','Reservas internacionais — conceito caixa',13621,'US$ milhões','daily','stock','Reservas internacionais, conceito caixa, total diário. Estoque; não somar dias.'),
 bcb('gross_debt_gdp','Dívida Bruta do Governo Geral / PIB',13762,'% do PIB','monthly','rate','DBGG, metodologia utilizada a partir de 2008. Conceito diferente de DPF e DLSP.'),
 bcb('net_debt_gdp','Dívida Líquida do Setor Público / PIB',4513,'% do PIB','monthly','rate','DLSP do setor público consolidado. Não é DBGG nem Dívida Pública Federal.')]

def missing(key,name,agency,url,note,unit='Não disponível'):
    return dict(id=key,name=name,agency=agency,url=url,unit=unit,frequency='Não validada',kind='unavailable',connector=None,methodology=note,favorable='neutral')

CATALOG += [missing(k,n,a,u,note,unit) for k,n,a,u,note,unit in [
 ('income','Rendimento médio do trabalho','IBGE','https://www.ibge.gov.br/estatisticas/sociais/trabalho.html','Série e base de preços ainda precisam de validação.','Reais'),
 ('exchange','Taxa de câmbio','Banco Central do Brasil','https://www.bcb.gov.br/estabilidadefinanceira/historicocotacoes','Série e tipo de cotação ainda não validados.','R$/US$'),
 ('primary','Resultado primário do Governo Central','Tesouro Nacional','https://www.tesourotransparente.gov.br/temas/estatisticas-fiscais-e-planejamento/resultado-do-tesouro-nacional-rtn','Integração do RTN ainda não validada. Não substituir por resultado do setor público consolidado.','Milhões de reais'),
 ('nominal','Resultado nominal','Banco Central do Brasil','https://www.bcb.gov.br/estatisticas/estatisticasfiscais','Conceito e sinal fiscal precisam ser validados antes de exibir valores.','Milhões de reais'),
 ('revenue','Receitas públicas','Tesouro Nacional','https://www.tesourotransparente.gov.br/','Integração e conceito ainda não validados.','Milhões de reais'),
 ('spending','Despesas públicas','Tesouro Nacional','https://www.tesourotransparente.gov.br/','Integração e conceito ainda não validados.','Milhões de reais'),
 ('federal_debt','Dívida Pública Federal','Tesouro Nacional','https://www.tesourotransparente.gov.br/temas/divida-publica-federal','DPF não é DBGG nem DLSP. Saldo, custo e prazo ainda não integrados.','Milhões de reais'),
 ('gross_debt','Dívida Bruta do Governo Geral — valor nominal','Banco Central do Brasil','https://www.bcb.gov.br/estatisticas/estatisticasfiscais','Valor nominal não integrado; consulte a série percentual validada separadamente.','Milhões de reais'),
 ('net_debt','Dívida Líquida do Setor Público — valor nominal','Banco Central do Brasil','https://www.bcb.gov.br/estatisticas/estatisticasfiscais','Valor nominal não integrado; não somar conceitos de dívida.','Milhões de reais'),
 ('exports','Exportações de bens','MDIC','https://comexstat.mdic.gov.br/','Contrato da consulta automatizada ainda não validado. Dados mensais FOB.','US$ FOB'),
 ('imports','Importações de bens','MDIC','https://comexstat.mdic.gov.br/','Contrato da consulta automatizada ainda não validado. Dados mensais FOB.','US$ FOB'),
 ('trade_balance','Saldo comercial','MDIC','https://comexstat.mdic.gov.br/','Exportações menos importações, somente após validar as duas séries equivalentes.','US$ FOB'),
 ('trade_flow','Corrente de comércio','MDIC','https://comexstat.mdic.gov.br/','Exportações mais importações, somente após validar as duas séries equivalentes.','US$ FOB')]]
# Additional contracts validated in the official metadata/catalog during this upgrade.
_replacements={
 'income':ibge('income','Rendimento médio mensal nominal do trabalho',6390,5929,'Reais','monthly','stock','','PNAD Contínua: rendimento habitualmente recebido em todos os trabalhos, pessoas ocupadas de 14 anos ou mais com rendimento. Trimestre móvel, valor nominal.'),
 'exchange':bcb('exchange','Dólar americano — venda diária',1,'R$/US$','daily','stock','Taxa de câmbio livre, dólar americano, venda diária, série SGS 1. Não é cotação de compra nem preço garantido ao consumidor.'),
 'net_debt':bcb('net_debt','Dívida Líquida do Setor Público — saldo nominal',4478,'Milhões de reais','monthly','stock','Saldo nominal do setor público consolidado. Conceito diferente de DPF e DBGG.'),
 'nominal':bcb('nominal','Resultado nominal — NFSP do setor público consolidado',4583,'Milhões de reais','monthly','flow','NFSP sem desvalorização cambial, fluxo mensal corrente, resultado nominal do setor público consolidado. Sinal reproduzido da fonte, sem avaliação automática de resultado favorável ou desfavorável.')}
CATALOG=[_replacements.get(x['id'],x) for x in CATALOG]
BY_ID={x['id']:x for x in CATALOG}
