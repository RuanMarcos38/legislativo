"use strict";
const $=s=>document.querySelector(s);
const e=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt=d=>d?new Date(d).toLocaleString("pt-BR"):"Não coletado";
const labels={partial:"Parcial",not_synced:"Sem coleta",not_integrated:"Não integrado",failed:"Falhou",complete_query:"Consulta concluída",running:"Em andamento",pending:"Na fila",done:"Processado",dead:"Requer revisão"};
let csrf="";
let route="inicio",page=1,lastParams=new URLSearchParams(),generation=0;
async function api(path,body){
 const r=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json","X-Local-Action":"1","X-CSRF-Token":csrf},body:JSON.stringify(body)});
 const data=await r.json();if(!r.ok)throw new Error(data.error||"Falha na consulta");return data;
}
function empty(title,text){return '<div class="empty"><strong>'+e(title)+'</strong><p>'+e(text)+'</p></div>';}
function sourceCard(s){return '<div class="source"><div><h3><a href="'+e(s.url)+'" target="_blank" rel="noopener noreferrer">'+e(s.name)+' ↗</a></h3><p>'+e(s.note)+'</p><small>Última coleta: '+e(fmt(s.last_collected))+' · '+Object.values(s.counts).reduce((a,b)=>a+b,0)+' registros locais</small></div><span class="pill">'+e(labels[s.status])+'</span></div>';}
function setTitle(title,subtitle){$("#title").textContent=title;$("#subtitle").textContent=subtitle;}
async function dashboard(token){
 setTitle("Panorama legislativo","Acompanhe a atividade parlamentar a partir de documentos oficiais.");
 const c=await api("/api/coverage");if(token!==generation)return;
 const count=k=>c.sources.reduce((sum,s)=>sum+(s.counts[k]||0),0);
 $("#content").innerHTML='<div class="stats">'+[["Parlamentares coletados",count("person"),"Identidades por fonte; sem unificação automática"],["Proposições coletadas",count("proposal"),"Apresentação não significa aprovação"],["Votações coletadas",count("vote"),"Votos nominais somente quando documentados"],["Fontes com registros",c.sources.filter(s=>Object.keys(s.counts).length).length,"De 7 grupos cadastrados; integração parcial"]].map(([l,n,s])=>'<div class="stat"><div class="label">'+e(l)+'</div><div class="value">'+n.toLocaleString("pt-BR")+'</div><small>'+e(s)+'</small></div>').join("")+'</div><div class="big-search"><h2>O que você quer acompanhar?</h2><p>Encontre parlamentares, proposições e registros de votação.</p><a class="button" href="#pesquisa">Pesquisar nos dados coletados →</a></div><div class="grid"><section class="panel"><div class="panel-head"><h2>Conexões oficiais</h2><a href="#historico">Todas as fontes ↗</a></div>'+c.sources.slice(0,4).map(sourceCard).join("")+'</section><section class="panel"><h2>Da proposta à implementação</h2><p>Quatro etapas, quatro evidências diferentes.</p><div class="timeline"><div><strong>01 · Proposição apresentada</strong><p>Texto protocolado e autoria registrada.</p></div><div><strong>02 · Deliberação legislativa</strong><p>Uma etapa aprovada pode não concluir a tramitação.</p></div><div><strong>03 · Norma publicada</strong><p>Vínculo com a lei exige documentação oficial.</p></div><div><strong>04 · Implementação verificada</strong><p>Publicação, por si só, não comprova execução.</p></div></div></section></div>';
}
function filters(kind){
 return '<form id="filters" class="filters"><label class="field grow">Nome, assunto ou número<input name="q" maxlength="200" placeholder="Busque nos registros coletados"></label><label class="field">Casa<select name="source"><option value="">Todas as fontes</option value="camara">Câmara dos Deputados</option value="senado">Senado Federal</option></select></label>'+(kind==="person"?'<label class="field">UF<input name="uf" maxlength="2" placeholder="Ex.: SP" size="3"></label><label class="field">Partido<input name="party" maxlength="30" placeholder="Sigla" size="8"></label>':'<label class="field">Ano<input name="year" type="number" min="1800" max="2200" placeholder="Ano"></label>')+'<button type="submit">Pesquisar</button></form>';
}
async function listing(kind,token){
 const title={person:"Parlamentares",proposal:"Projetos e Leis",vote:"Votações",document:"Pesquisa documental"}[kind];
 setTitle(title,kind==="proposal"?"Proposições coletadas. A integração de leis e os vínculos com normas ainda estão pendentes.":kind==="document"?"Recupere documentos oficiais coletados. O assistente generativo ainda não está configurado.":"Explore a base local com filtros e paginação no servidor.");
 $("#content").innerHTML='<section class="panel">'+(route==="pesquisa"?'<label class="field">Pesquisar em<select id="kind"><option value="person">Parlamentares</option><option value="proposal">Proposições</option><option value="vote">Votações</option><option value="document">Documentos coletados</option></select></label><br>':'')+filters(kind)+'</section><section class="panel"><div class="panel-head"><h2>Registros oficiais</h2><span id="total" class="muted"></span></div><div id="results">Carregando…</div></section>';
 if($("#kind")){$("#kind").value=kind;$("#kind").onchange=()=>{page=1;listing($("#kind").value,token).catch(showError);};}
 $("#filters").onsubmit=ev=>{ev.preventDefault();page=1;run().catch(showError);};
 async function run(){
  const params=new URLSearchParams(new FormData($("#filters")));params.set("kind",kind);params.set("page",page);params.set("size",20);
  params.set("uf",(params.get("uf")||"").toUpperCase());lastParams=params;
  $("#results").textContent="Consultando a base local…";
  const data=await api("/api/search?"+params);if(token!==generation)return;
  $("#total").textContent=data.total.toLocaleString("pt-BR")+" registros";
  const rows=data.items.map(r=>'<tr><td><button class="text-button record" data-id="'+e(r.id)+'">'+e(r.data.name)+'</button><p>'+e(r.data.description||r.data.role||"")+'</p></td><td>'+e(r.data.party||r.data.type||"—")+'</td><td>'+e(r.data.uf||r.data.year||"—")+'</td><td>'+e(r.source==="camara"?"Câmara":"Senado")+'</td><td>'+e(fmt(r.collected_at))+'</td></tr>').join("");
  $("#results").innerHTML=(rows?'<div class="table-wrap"><table><thead><tr><th>Nome / título</th><th>Partido / tipo</th><th>UF / ano</th><th>Fonte</th><th>Coletado em</th></tr></thead><tbody>'+rows+'</tbody></table></div>':empty("Nenhum registro encontrado","Ajuste os filtros ou execute uma coleta em Histórico e cobertura. Ausência na base não significa ausência de atuação."))+'<div class="pager"><span>Página '+page+' de '+Math.max(1,Math.ceil(data.total/20))+'</span><div><button class="secondary" id="previous" '+(page===1?"disabled":"")+'>Anterior</button><button class="secondary" id="next" '+(page*20>=data.total?"disabled":"")+'>Próxima</button></div></div>';
  $("#previous").onclick=()=>{page--;run().catch(showError);};$("#next").onclick=()=>{page++;run().catch(showError);};
  document.querySelectorAll(".record").forEach(b=>b.onclick=()=>openRecord(b.dataset.id));
 }
 await run();
}
function documentView(doc){
 const payload=doc.payload||{},rows=Array.isArray(payload.dados)?payload.dados:[],section=doc.section||"detail";
 let body="";
 const table=(heads,lines)=>'<div class="table-wrap"><table><thead><tr>'+heads.map(h=>'<th>'+e(h)+'</th>').join("")+'</tr></thead><tbody>'+lines.map(line=>'<tr>'+line.map(cell=>'<td>'+e(cell||"Não informado")+'</td>').join("")+'</tr>').join("")+'</tbody></table></div>';
 if(section==="tramitacoes"){
  body=rows.length?'<div class="timeline">'+rows.map(r=>'<div><strong>'+e(r.dataHora||"Data não informada")+' · '+e(r.siglaOrgao||"Órgão não informado")+'</strong><p>'+e(r.descricaoTramitacao||"")+'</p><p>'+e(r.despacho||"")+'</p></div>').join("")+'</div>':empty("Sem tramitação nesta resposta","Consulte a fonte para outras páginas e períodos.");
 }else if(section==="votos"){
  body='<p>As categorias abaixo reproduzem o registro oficial. Não se deduz voto individual de votação simbólica ou orientação partidária.</p>'+(rows.length?table(["Parlamentar","Partido","UF","Voto registrado"],rows.map(r=>{const p=r.deputado_||r.deputado||{};return [p.nome,p.siglaPartido,p.siglaUf,r.tipoVoto];})):empty("Sem votos individuais nesta resposta","Isso não permite inferir como cada parlamentar votou."));
 }else if(section==="autores"){
  body=table(["Nome","Tipo de autoria","Proponente"],rows.map(r=>[r.nome,r.tipo,String(r.proponente??"Não informado")]));
 }else if(section==="historico"){
  body=table(["Período inicial","Período final","Nome","Partido","UF","Situação"],rows.map(r=>[r.dataInicio,r.dataFim,r.nome,r.siglaPartido,r.siglaUf,r.situacao]));
 }else if(section==="despesas"){
  body=table(["Ano / mês","Tipo","Fornecedor","Valor líquido (R$)"],rows.map(r=>[r.ano+" / "+r.mes,r.tipoDespesa,r.nomeFornecedor,r.valorLiquido]));
 }else{
  const p=payload.dados&&!Array.isArray(payload.dados)?payload.dados:payload.DetalheParlamentar?.Parlamentar;
  if(p){
   const v=p.ultimoStatus||p.IdentificacaoParlamentar||{};
   body=table(["Campo institucional","Valor"],[["Nome",v.nome||v.NomeParlamentar||p.nomeCivil||p.descricao],["Partido",v.siglaPartido||v.SiglaPartidoParlamentar],["UF",v.siglaUf||v.UfParlamentar],["Situação informada",v.situacao||p.statusProposicao?.descricaoSituacao],["Resumo",p.ementa]]);
  }
 }
 return '<section class="panel"><h3>Documento oficial · '+e(section)+'</h3><div class="provenance">'+e(doc.note)+'<br><a href="'+e(doc.url)+'" target="_blank" rel="noopener noreferrer">Documento na fonte ↗</a> · '+e(fmt(doc.collected_at))+'</div>'+body+'<details><summary>Ver resposta original e links de paginação</summary><pre>'+e(JSON.stringify(payload,null,2))+'</pre></details></section>';
}
async function openRecord(id){
 const dialog=$("#detail");$("#detail-body").textContent="Carregando registro…";if(!dialog.open)dialog.showModal();
 try{
 const result=await api("/api/record?id="+encodeURIComponent(id)),r=result.record;
 $("#detail-body").innerHTML='<h2>'+e(r.data.name)+'</h2><p>'+e(r.data.description||r.data.role||"")+'</p><div class="provenance"><strong>Rastreabilidade</strong><br>ID institucional: '+e(r.external_id)+' · Fonte: '+e(r.source)+'<br>Coleta: '+e(fmt(r.collected_at))+'<br>Alteração local: '+e(fmt(r.updated_at))+'<br>SHA256: '+e(r.hash)+'<br><a href="'+e(r.url)+'" target="_blank" rel="noopener noreferrer">Abrir registro na fonte oficial ↗</a><br>Recebido da fonte; revisão humana não realizada. Data de publicação não normalizada.</div><p>A lista atual não comprova histórico completo de mandatos ou filiações. Dados de candidatura e exercício não são intercambiáveis.</p><div class="actions" id="sections"></div><div id="document"></div><h3>Versões coletadas</h3>'+result.versions.map(v=>'<p><small>'+e(fmt(v.collected_at))+' · '+e(v.hash.slice(0,16))+'…</small></p>').join("");
 const sections=r.source==="senado"?["detail"]:({person:["detail","historico","despesas"],proposal:["detail","autores","tramitacoes"],vote:["detail","votos"]}[r.kind]||[]);
 const names={detail:"Consultar detalhes oficiais",historico:"Histórico institucional",despesas:"Despesas",autores:"Autoria",tramitacoes:"Tramitação",votos:"Votos registrados"};
 $("#sections").innerHTML=sections.map(s=>'<button class="secondary section" data-section="'+s+'">'+e(names[s])+'</button>').join("");
 if(result.documents?.length)$("#document").innerHTML=result.documents.map(documentView).join("");
 document.querySelectorAll(".section").forEach(b=>b.onclick=async()=>{
  $("#document").textContent="Consultando a fonte oficial…";b.disabled=true;
  try{const d=await api("/api/detail",{id,section:b.dataset.section});$("#document").innerHTML=documentView({...d,section:b.dataset.section});}
  catch(err){$("#document").textContent=err.message;}finally{b.disabled=false;}
 });
 }catch(err){$("#detail-body").textContent=err.message;}
}
async function history(token){
 setTitle("Histórico e cobertura","Consulte as lacunas, execuções e documentos efetivamente coletados.");
 const d=await api("/api/coverage");if(token!==generation)return;
 $("#content").innerHTML='<section class="panel"><h2>Coleta de dados oficiais</h2><p>Enfileire uma consulta e execute o processo de coleta local. A consulta padrão limita a cinco páginas: proposições do ano atual e votações dos últimos 30 dias.</p><div class="actions">'+[["camara_people","Deputados"],["senado_people","Senadores"],["camara_proposals","Proposições"],["camara_votes","Votações"]].map(([id,name])=>'<button class="secondary sync" data-dataset="'+id+'">Coletar '+name+'</button>').join("")+'</div><p id="sync-status" role="status"></p><small>Processar fila: <code>python -m app.worker</code>. Importação histórica: <code>python -m app.sync --dataset camara_proposals --year 2024 --max-pages 20</code>.</small></section><section class="panel"><h2>Matriz de fontes</h2>'+d.sources.map(s=>sourceCard(s)+'<small>Anos observados: '+e(s.observed_years.join(", ")||"Nenhum")+'. '+e(s.historical_coverage)+'</small>').join("")+'</section><section class="panel"><h2>Execuções recentes</h2>'+ (d.runs.length?'<div class="table-wrap"><table><thead><tr><th>Conjunto</th><th>Estado</th><th>Registros processados</th><th>Início</th><th>Erro</th></tr></thead><tbody>'+d.runs.map(r=>'<tr><td>'+e(r.dataset)+'</td><td>'+e(labels[r.status]||r.status)+'</td><td>'+r.count+'</td><td>'+e(fmt(r.started_at))+'</td><td>'+e(r.error||"—")+'</td></tr>').join("")+'</tbody></table></div>':empty("Nenhuma execução","A base está pronta para receber a primeira coleta."))+'</section><section class="panel"><h2>Fila persistente</h2><pre>'+e(JSON.stringify(d.jobs,null,2))+'</pre><button id="refresh" class="secondary">Atualizar estado</button></section>';
 document.querySelectorAll(".sync").forEach(b=>b.onclick=async()=>{b.disabled=true;try{const r=await api("/api/sync",{dataset:b.dataset.dataset});$("#sync-status").textContent=r.message;}catch(err){$("#sync-status").textContent=err.message;}finally{b.disabled=false;}});
 $("#refresh").onclick=()=>history(token).catch(showError);
}
async function watches(token){
 setTitle("Monitoramentos","Termos acompanhados nesta instalação. Eventos locais surgem após alterações coletadas.");
 const d=await api("/api/watches");if(token!==generation)return;
 $("#content").innerHTML='<section class="panel"><h2>Criar monitoramento</h2><form id="watch-form" class="filters"><label class="field grow">Nome, assunto ou identificador<input id="watch-query" required minlength="2" maxlength="120" placeholder="Ex.: educação"></label><button>Salvar monitoramento</button></form><p>Sem envio de e-mails ou notificações externas. Os termos e eventos são privados da sua organização.</p><p id="watch-status" role="status"></p></section><section class="panel"><h2>Termos acompanhados</h2>'+ (d.watches.length?d.watches.map(w=>'<div class="source"><strong>'+e(w.query)+'</strong><button class="secondary delete-watch" data-id="'+w.id+'">Remover</button></div>').join(""):empty("Nenhum monitoramento","Salve um termo para acompanhar próximas alterações."))+'</section><section class="panel"><h2>Alterações detectadas</h2>'+ (d.events.length?d.events.map(v=>'<div class="source"><div><strong>'+e(v.query)+'</strong><p>'+e(JSON.parse(v.data).name)+'</p><small>'+e(fmt(v.created_at))+'</small></div><button class="secondary event-record" data-id="'+e(v.record_id)+'">Ver registro</button></div>').join(""):empty("Nenhum evento","Somente documentos novos ou alterados após a criação de um monitoramento geram eventos."))+'</section>';
 $("#watch-form").onsubmit=async ev=>{ev.preventDefault();try{await api("/api/watches",{query:$("#watch-query").value});await watches(token);}catch(err){$("#watch-status").textContent=err.message;}};
 document.querySelectorAll(".delete-watch").forEach(b=>b.onclick=async()=>{try{await api("/api/watches/delete",{id:Number(b.dataset.id)});await watches(token);}catch(err){showError(err);}});
 document.querySelectorAll(".event-record").forEach(b=>b.onclick=()=>openRecord(b.dataset.id));
}
function reports(){
 setTitle("Relatórios","Exporte registros com filtros, data de emissão e rastreabilidade.");
 $("#content").innerHTML='<section class="panel"><h2>Exportação CSV</h2><p>Exportação explícita de uma página de até 100 registros. Para extrair mais registros, avance o número da página. A cobertura continua parcial.</p><form id="report-form" class="filters"><label class="field">Conjunto<select name="kind"><option value="person">Parlamentares</option><option value="proposal">Proposições</option><option value="vote">Votações</option></select></label><label class="field grow">Texto<input name="q" maxlength="200"></label><label class="field">Fonte<select name="source"><option value="">Todas</option><option value="camara">Câmara</option><option value="senado">Senado</option></select></label><label class="field">Ano<input name="year" type="number" min="1800" max="2200"></label><label class="field">Página<input name="page" type="number" value="1" min="1" max="100000"></label><button>Baixar CSV</button></form></section><section class="panel"><h2>Relatório de cobertura</h2><p>Abra o histórico de fontes e use a impressão do navegador para salvar em PDF. Geração automatizada de PDF ainda não está integrada.</p><a class="button secondary" href="#historico">Abrir cobertura</a></section>';
 $("#report-form").onsubmit=ev=>{ev.preventDefault();const p=new URLSearchParams(new FormData(ev.target));p.set("size",100);const a=document.createElement("a");a.href="/api/export?"+p;a.download="observatorio-registros.csv";a.click();};
}
async function settings(token){
 setTitle("Configurações","Estado desta instalação e serviços ainda não configurados.");
 const [d,s]=await Promise.all([api("/api/config"),api("/api/session")]);if(token!==generation)return;
 csrf=s.user?.csrf||"";
 $("#content").innerHTML='<section class="panel"><h2>Acesso à organização</h2>'+(s.user?'<p>'+e(s.user.email)+' · '+e(s.user.tenant)+' · '+e(s.user.role)+'</p><p>Organização: '+e(s.user.tenant_id)+'<br>Plano: '+e(s.plan?.name)+' · '+e(s.plan?.watch_count)+' / '+e(s.plan?.watch_limit??"sem limite definido")+' monitoramentos. Sem cobrança.</p><button id="logout" class="secondary">Sair</button>':'<p>Crie sua organização pelo comando seguro descrito no manual de operação. Não há credenciais padrão.</p><form id="login" class="filters"><label class="field grow">E-mail<input name="email" type="email" autocomplete="username" required></label><label class="field grow">Senha<input name="password" type="password" minlength="12" maxlength="256" autocomplete="current-password" required></label><button>Entrar</button></form>')+'<p id="auth-status" role="status"></p></section><section class="panel"><h2>'+e(d.name)+'</h2><p>'+e(d.mode)+'</p><div class="source"><strong>Assinaturas e checkout</strong><span>'+e(d.billing)+'</span></div><div class="source"><strong>Assistente IA</strong><span>'+e(d.ai)+'</span></div><div class="source"><strong>Organizações e autenticação</strong><span>Autenticação local, papéis e isolamento no servidor</span></div><div class="source"><strong>Marca</strong><span>Configurável pela variável APP_NAME</span></div><div class="source"><strong>Administração</strong><a href="#historico">Monitorar fontes e fila ↗</a></div></section><section class="panel"><h2>Limites de uso</h2><p>Esta versão opera localmente com sessões e organizações. A publicação como SaaS depende de HTTPS, infraestrutura, banco PostgreSQL com RLS, MFA e testes de produção. Nenhum gateway, domínio ou credencial de outro projeto foi reutilizado.</p></section>';
 if($("#login"))$("#login").onsubmit=async ev=>{ev.preventDefault();try{const r=await api("/api/login",Object.fromEntries(new FormData(ev.target)));csrf=r.csrf;await settings(token);}catch(err){$("#auth-status").textContent=err.message;}};
 if($("#logout"))$("#logout").onclick=async()=>{try{await api("/api/logout",{});csrf="";await settings(token);}catch(err){$("#auth-status").textContent=err.message;}};
}
function showError(err){$("#content").innerHTML='<div class="error" role="alert">'+e(err.message)+' <a href="#configuracoes">Entrar na conta →</a></div>';}
async function render(){
 const token=++generation;route=location.hash.slice(1)||"inicio";if(route==="main")route="inicio";page=1;
 document.querySelectorAll("nav a").forEach(a=>a.classList.toggle("active",a.hash==="#"+route));
 $("#content").textContent="Carregando…";
 try{switch(route){case "inicio":await dashboard(token);break;case "pesquisa":case "parlamentares":await listing("person",token);break;case "projetos":await listing("proposal",token);break;case "votacoes":await listing("vote",token);break;case "historico":await history(token);break;case "monitoramentos":await watches(token);break;case "relatorios":reports();break;case "configuracoes":await settings(token);break;default:setTitle("Página não encontrada","Escolha uma seção no menu.");$("#content").innerHTML=empty("Página não encontrada","Use o menu para continuar.");}}
 catch(err){if(token===generation)showError(err);}
}
$("#close-detail").onclick=()=>$("#detail").close();
window.addEventListener("hashchange",()=>{if(location.hash==="#main"){$("#main").focus();return;}render();});
api("/api/session").then(s=>{csrf=s.user?.csrf||"";}).finally(render);
