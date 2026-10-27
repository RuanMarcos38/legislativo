"""Exports use the complete filtered selection or reject its size explicitly."""
import csv,io,json,zipfile,textwrap
from xml.sax.saxutils import escape
from .calculations import brasilia
from .financial_exports import xlsx_export as empty_workbook

LIMIT=10000
LABELS={'title':'Título','issued_at':'Emissão em Brasília','filters':'Filtros aplicados','methodology':'Como ler os dados','availability':'Disponibilidade','deflator':'Correção monetária','summaries':'Resumos dos períodos comparados','unavailable':'Dados ainda indisponíveis','indicator':'Indicador','agency':'Órgão responsável','period':'Referência','value':'Valor','unit':'Unidade','source_url':'Fonte oficial','published_at':'Publicação oficial','collected_at':'Última consulta','hash':'Identificador da versão','government':'Governo','mandate_start':'Início do mandato','mandate_end':'Fim do mandato','comparison_complete':'Recorte completo','official_value':'Valor original da série','deflator_period':'Referência do índice usado','id':'Registro','name':'Nome','party':'Partido do cadastro','uf':'UF','url':'Fonte oficial','position':'Posição na seleção','records':'Registros coletados','approval_rate':'Taxa de aprovação final','per_year':'Produção por ano de exercício','proposals':'Proposições atribuídas ao partido no período','approved':'Aprovação atribuída ao partido no período','laws':'Leis conferidas','normalized':'Indicador por tempo de exercício','expenses':'Despesas atribuídas ao partido no período','ufs':'Distribuição dos cadastros por UF','source':'Casa','q':'Nome ou texto','start':'A partir de','end':'Até','year':'Ano','metric':'Indicador selecionado','group':'Agrupamento','nature':'Situação do gasto','terms':'Mandatos','mode':'Recorte','price':'Base de preços','status':'Situação','first':'Primeiro valor','last':'Último valor','mean':'Média das observações','sum':'Soma de fluxos','change':'Mudança','absolute':'Diferença absoluta','percentage':'Variação percentual','points':'Pontos percentuais','formula':'Fórmula','note':'Explicação','complete':'Recorte completo','term':'Mandato','reference':'Referência','cumulative_inflation':'Inflação composta'}
WORDS={'available':'Consulta recente','stale':'Atualização não confirmada','unavailable':'Dado oficial indisponível','camara':'Câmara dos Deputados','senado':'Senado Federal','party':'Partido','person':'Parlamentar','projects':'Projetos apresentados','proposals':'Proposições apresentadas','approved_stage':'Aprovação em alguma etapa','votes':'Votos nominais observados','expenses':'Despesas da mesma natureza','nominal':'Valores nominais','corrected':'Corrigidos pelo IPCA','equivalent':'Períodos equivalentes','first':'Primeiro ano equivalente','last':'Último ano observado equivalente','full':'Mandatos completos de mesma duração','bolsonaro':'Jair Bolsonaro','lula3':'Luiz Inácio Lula da Silva - 3º mandato'}

def readable(v,key=''):
    if isinstance(v,dict):return '; '.join(LABELS.get(k,k)+': '+readable(x,k) for k,x in v.items() if k not in {'module','format'})
    if isinstance(v,list):return ' | '.join(readable(x) for x in v)
    if isinstance(v,bool):return 'Sim' if v else 'Não'
    if v is None:return 'Não aplicada' if key=='deflator' else 'Não aplicável' if key=='sum' else 'Dado oficial indisponível'
    if key=='collected_at':return brasilia(str(v))
    raw=str(v)
    if key=='indicator':
        from .economic_catalog import BY_ID
        if raw in BY_ID:return BY_ID[raw]['name']
    if key=='terms':
        from .governments import TERMS
        names={t['id']:t['name'] for t in TERMS}
        return '; '.join(names.get(x,x) for x in raw.split(','))
    if key in {'period','deflator_period','mandate_start','mandate_end','start','end'}:
        if '-Q' in raw:return 'T'+raw[-1]+'/'+raw[:4]
        if len(raw)==7 and raw[4]=='-':return raw[5:]+'/'+raw[:4]
        if len(raw)==10 and raw[4]=='-' and raw[7]=='-':return raw[8:]+'/'+raw[5:7]+'/'+raw[:4]
    if key in {'value','official_value','first','last','mean','sum','percentage','absolute','points'}:
        import re
        if re.fullmatch(r'-?\d+(\.\d+)?',raw):return raw.replace('.',',')
    return WORDS.get(raw,raw)


def export(title,rows,metadata,form):
    if len(rows)>LIMIT:raise ValueError('Refine os filtros para até 10000 linhas')
    meta=dict(title=title,issued_at=brasilia(),**metadata)
    if form=='json':return json.dumps(dict(metadata=meta,items=rows),ensure_ascii=False,indent=2).encode('utf8'),'application/json; charset=utf-8'
    headers=list(dict.fromkeys(k for row in rows for k in row))
    def value(v):return json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else 'Dado oficial indisponível' if v is None else str(v)
    table=[[LABELS.get(k,k),readable(v,k)] for k,v in meta.items()]+[[LABELS.get(k,k) for k in headers]]+[[readable(r.get(k),k) for k in headers] for r in rows]
    if form=='csv':
        b=io.StringIO(newline='');w=csv.writer(b,delimiter=';')
        for row in table:w.writerow(["'"+v if v.lstrip().startswith(('=','+','-','@','\t','\r')) else v for v in row])
        return ('\ufeff'+b.getvalue()).encode('utf8'),'text/csv; charset=utf-8'
    if form=='xlsx':
        def cell(v):
            v=''.join(c for c in v if c in '\n\r\t' or ord(c)>=32)
            return '<c t="inlineStr"><is><t xml:space="preserve">'+escape(v)+'</t></is></c>'
        sheet='<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join('<row r="'+str(i+1)+'">'+''.join(cell(v) for v in row)+'</row>' for i,row in enumerate(table))+'</sheetData></worksheet>'
        template=empty_workbook(dict(filters={},methodology='',items=[]));out=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(template)) as old,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as new:
            for name in old.namelist():new.writestr(name,sheet.encode('utf8') if name=='xl/worksheets/sheet1.xml' else old.read(name))
        return out.getvalue(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    if form=='pdf':
        if len(rows)>1000:raise ValueError('Refine os filtros para PDF de até 1000 linhas')
        lines=[title]+[LABELS.get(k,k)+': '+readable(v,k) for k,v in meta.items() if k!='title']+['']
        for i,r in enumerate(rows,1):lines+=['REGISTRO '+str(i)]+[LABELS.get(k,k)+': '+readable(v,k) for k,v in r.items()]+['']
        return pdf_lines(lines),'application/pdf'
    raise ValueError('Formato inválido')

def pdf_lines(lines):
    wrapped=[]
    for line in lines:wrapped.extend(textwrap.wrap(line,100,replace_whitespace=True) or [''])
    # Keep each record together; no orphan record heading at the foot of a page.
    chunks=[];current=[];block=[]
    def add_block(block):
        nonlocal current
        if len(block)>59:
            if current:chunks.append(current);current=[]
            chunks.extend(block[i:i+59] for i in range(0,len(block),59));return
        if current and len(current)+len(block)+1>59:chunks.append(current);current=[]
        current+=block+['']
    for line in wrapped:
        if line:block.append(line)
        elif block:add_block(block);block=[]
    if block:add_block(block)
    if current:chunks.append(current)
    if not chunks:chunks=[[]]
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>']
    refs=[]
    def literal(s):return s.replace('−','-').replace('→','->').replace('‑','-').encode('cp1252',errors='replace').replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')
    for n,chunk in enumerate(chunks,1):
        page_id=len(objects)+1;content_id=page_id+1;refs.append(str(page_id)+' 0 R')
        stream=b'BT /F1 9 Tf 12 TL 36 806 Td '+b'\nT* '.join(b'('+literal(s)+b') Tj' for s in chunk)+b' ET\nBT /F1 8 Tf 36 24 Td ('+literal(f'Observatório | Página {n} de {len(chunks)} | Cobertura parcial')+b') Tj ET'
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
    objects[1]=('<< /Type /Pages /Count '+str(len(refs))+' /Kids ['+' '.join(refs)+'] >>').encode()
    out=io.BytesIO();out.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(out.tell());out.write(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    start=out.tell();out.write(('xref\n0 '+str(len(objects)+1)+'\n0000000000 65535 f \n').encode())
    for offset in offsets[1:]:out.write(f'{offset:010} 00000 n \n'.encode())
    out.write(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return out.getvalue()
