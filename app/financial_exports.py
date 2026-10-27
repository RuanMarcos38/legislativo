"""Dependency-free XLSX and paginated PDF. Values remain exact text in exports."""
import io,json,textwrap,zipfile
from xml.sax.saxutils import escape
from .db import now
from .financial import MISSING

COLUMNS=[('id','Registro'),('person_id','Identidade oficial'),('person_name','Parlamentar / conta'),('institution','Instituição'),('mandate','Legislatura informada'),('year','Ano'),('month','Mês'),('category','Categoria'),('description','Descrição original'),('supplier','Fornecedor'),('amount','Valor BRL'),('gross','Documento BRL'),('disallowed','Glosa BRL'),('nature','Natureza'),('verification','Verificação'),('verification_note','Critério'),('document_date','Data documento'),('expense_date','Data despesa'),('payment_date','Data pagamento'),('document_number','Documento'),('source_url','Fonte oficial'),('receipt_url','Comprovante'),('collected_at','Coleta UTC'),('source_updated_at','Atualização da fonte')]

def val(row,key):
    v=row.get(key)
    return str(v) if v is not None else MISSING if key in {'amount','gross','disallowed'} else 'Não informado'

def xlsx_export(result):
    rows=[['Fiscalização Financeira — cobertura parcial'],['Emissão UTC',now()],['Filtros',json.dumps(result['filters'],ensure_ascii=False)],['Critério',result['methodology']],['Registros exportados',str(len(result['items']))],[label for _,label in COLUMNS]]
    rows += [[val(r,key) for key,_ in COLUMNS] for r in result['items']]
    def cell(v):
        # inlineStr prevents spreadsheet formula execution, including values starting =.
        v=''.join(c for c in str(v) if c in '\n\r\t' or ord(c)>=32)
        return '<c t="inlineStr"><is><t xml:space="preserve">'+escape(v)+'</t></is></c>'
    sheet='<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join('<row r="'+str(i+1)+'">'+''.join(cell(v) for v in r)+'</row>' for i,r in enumerate(rows))+'</sheetData></worksheet>'
    files={'[Content_Types].xml':'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
      '_rels/.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
      'xl/workbook.xml':'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Registros oficiais" sheetId="1" r:id="rId1"/></sheets></workbook>',
      'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
      'xl/worksheets/sheet1.xml':sheet}
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for path,body in files.items():z.writestr(path,body.encode('utf8'))
    return out.getvalue()

def pdf_export(result):
    if len(result['items'])>1000:raise ValueError('Refine a seleção para PDF de até 1000 registros')
    lines=['Fiscalização Financeira — registros oficiais','Emissão UTC: '+now(),'Cobertura parcial. Valores em BRL. Não representa custo total.','Filtros: '+json.dumps(result['filters'],ensure_ascii=False),result['methodology'],'']
    for r in result['items']:
        lines.append('REGISTRO '+r['id'])
        for key,label in COLUMNS[1:]:lines.append(label+': '+val(r,key))
        lines.append('')
    wrapped=[]
    for line in lines:wrapped.extend(textwrap.wrap(line,100,replace_whitespace=True) or [''])
    chunks=[wrapped[i:i+62] for i in range(0,len(wrapped),62)] or [[]]
    objects=[b'<< /Type /Catalog /Pages 2 0 R >>',b'',b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>']
    refs=[]
    def literal(s):return s.encode('cp1252',errors='replace').replace(b'\\',b'\\\\').replace(b'(',b'\\(').replace(b')',b'\\)')
    for n,chunk in enumerate(chunks,1):
        page_id=len(objects)+1;content_id=page_id+1;refs.append(str(page_id)+' 0 R')
        stream=b'BT /F1 9 Tf 12 TL 36 806 Td '+b'\nT* '.join(b'('+literal(s)+b') Tj' for s in chunk)+b' ET\nBT /F1 8 Tf 36 24 Td ('+literal(f'Observatório Legislativo | Página {n} de {len(chunks)} | Cobertura parcial')+b') Tj ET'
        objects.append(f'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>'.encode())
        objects.append(b'<< /Length '+str(len(stream)).encode()+b' >>\nstream\n'+stream+b'\nendstream')
    objects[1]=('<< /Type /Pages /Count '+str(len(refs))+' /Kids ['+' '.join(refs)+'] >>').encode()
    out=io.BytesIO();out.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets=[0]
    for i,obj in enumerate(objects,1):offsets.append(out.tell());out.write(str(i).encode()+b' 0 obj\n'+obj+b'\nendobj\n')
    start=out.tell();out.write(('xref\n0 '+str(len(objects)+1)+'\n0000000000 65535 f \n').encode())
    for offset in offsets[1:]:out.write(f'{offset:010} 00000 n \n'.encode())
    out.write(f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode())
    return out.getvalue()
