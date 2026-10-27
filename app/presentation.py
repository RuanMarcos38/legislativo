"""Public-facing summaries; original facts and operator diagnostics stay intact."""
from copy import deepcopy

FINANCE_NOTES={
 'camara_ceap':'Despesas informadas pela Câmara dos Deputados. O valor descontado da cota não é o limite disponível. A data do pagamento nem sempre é informada.',
 'senado_ceaps':'Reembolsos informados pelo Senado. O período do mandato, a data do pagamento e o comprovante podem não estar disponíveis.',
 'alesc_office':'Despesas de gabinetes divulgadas pela ALESC. Como a ligação de cada gasto com um parlamentar ainda precisa ser confirmada, esses valores ficam fora dos totais individuais.',
 'alesc_travel':'Diárias autorizadas pela ALESC. Só ligamos um registro a um deputado quando a própria fonte faz essa identificação. Autorização não comprova pagamento.',
 'cgu_amendments':'As emendas ainda não estão disponíveis nesta ferramenta. Elas são recursos do orçamento público e ficam separadas dos gastos do parlamentar.',
 'dou':'O Diário Oficial pode ajudar a conferir documentos. A publicação de um ato, sozinha, não comprova um pagamento.',
 'states':'As demais Assembleias e a Câmara Legislativa do Distrito Federal ainda não têm dados financeiros disponíveis nesta ferramenta.',
 'municipal':'Os dados financeiros das Câmaras Municipais ainda não estão disponíveis nesta ferramenta.'}

def automatic(value):
    d=deepcopy(value);d['streams']=[]
    d['note']='Os dados são atualizados aos poucos. Uma consulta concluída não significa que todo o histórico do parlamentar já esteja disponível.'
    return d

def coverage(value):
    d=deepcopy(value);d['automatic']=automatic(d['automatic']);d['runs']=[];d['jobs']=[]
    notes={
      'camara':'Dados publicados pela Câmara dos Deputados. A consulta inclui os registros já encontrados; o histórico pode estar incompleto.',
      'senado':'Dados publicados pelo Senado Federal. O histórico pode estar incompleto. Os votos individuais do Senado ainda não estão disponíveis aqui.',
      'tse':'Dados eleitorais ainda não estão disponíveis nesta consulta. Candidatura não comprova exercício de mandato.',
      'planalto':'A confirmação das leis publicadas ainda não está disponível nesta consulta.',
      'lexml':'Esta fonte ainda não está disponível nesta consulta.',
      'estados':'A atividade legislativa dos estados ainda não está disponível aqui. Os dados financeiros da ALESC aparecem em Gastos e Custos.',
      'municipios':'A atividade das Câmaras Municipais ainda não está disponível nesta consulta.'}
    for s in d['sources']:
        s['note']=notes.get(s['id'],'Confira os registros disponíveis e seus documentos oficiais.')
        s['historical_coverage']='Os anos listados mostram os registros encontrados, sem garantir que o histórico esteja completo.'
    return d

def finance_coverage(value):
    d=deepcopy(value);d['jobs']=[]
    d['note']='Confira quais fontes e anos já podem ser consultados. Não encontrar um registro não significa que não houve despesa.'
    for s in d['sources']:s['note']=FINANCE_NOTES.get(s['id'],'Confira a disponibilidade dos registros e seus documentos oficiais.')
    for c in d['coverage']:
        c.pop('job_key',None);c['note']='Consulta realizada para este período. O histórico disponível pode estar incompleto.'
    return d

def verification(row):
    note=row.get('verification_note') or ''
    if row['verification']=='unavailable':return 'VALOR NÃO DISPONIBILIZADO PELA FONTE OFICIAL'
    if row['verification']=='pending':
        if 'restituição' in note:return 'Há uma devolução relacionada a este documento. O registro fica fora dos totais até a conferência.'
        if 'ambígua' in note:return 'Há registros que ainda precisam ser diferenciados. Eles ficam fora dos totais até a conferência.'
        if 'diverge' in note:return 'Os valores divulgados precisam ser conferidos. Este registro não entra nos totais.'
        if 'não retornou' in note:return 'Este registro não apareceu na atualização mais recente da fonte. O valor anterior foi preservado, mas não entra nos totais.'
        if 'vínculo' in note or 'atribuição' in note:return 'Ainda não foi possível confirmar a ligação deste gasto com um parlamentar. Ele não entra nos totais individuais.'
        return 'DADO PENDENTE DE VERIFICAÇÃO. Este registro não entra nos totais confirmados.'
    return {
      'camara_ceap':'Valor informado pela Câmara como desconto na cota parlamentar. Isso não comprova a data de um pagamento ao deputado.',
      'senado_ceaps':'Reembolso informado pelo Senado. A data do pagamento pode não ter sido divulgada.',
      'alesc_travel':'Diária autorizada pela ALESC para um deputado identificado na fonte. Isso não comprova o pagamento.'
    }.get(row['source_id'],'Valor conferido com o registro publicado pela instituição responsável.')

def financial(value):
    d=deepcopy(value);d['coverage']=finance_coverage(d['coverage'])
    d['methodology']='Somamos apenas os registros confirmados nesta consulta. Cada tipo de gasto e cada situação aparecem separados. Devoluções e ajustes não são novas despesas. Não apresentamos um custo total do parlamentar sem conferir todas as parcelas. Emendas ficam em uma área separada.'
    d['amendments']['note']='Os dados de emendas ainda não estão disponíveis nesta ferramenta. Consulte também o portal oficial.'
    for row in d['items']:
        row.pop('batch_id',None);row['verification_note']=verification(row)
    return d

def politician(value):
    d=deepcopy(value)
    if d.get('sync',{}).get('error'):d['sync']['error']='Uma fonte não respondeu à atualização. Os registros anteriores foram mantidos.'
    for field in ('key','initial_url','next_url','lease_token','lease_until'):d.get('sync',{}).pop(field,None)
    return d
