# Matriz de requisitos e estado

| Área | Estado | Evidência / limite |
|---|---|---|
| Repositório isolado | Implementado | Diretório dedicado, branch exclusiva, sem alteração de outros projetos |
| UI em português e menus | Implementado | Início, pesquisa, parlamentares, projetos, votações, histórico, monitoramentos, relatórios e configurações |
| Dashboard individual | Implementado com cobertura explícita | Seleção por parlamentar, período, autoria, projetos, aprovação por etapa, normas informadas e votos nominais coletados | 
| Atualização automática | Implementada para conjuntos integrados | Cursor persistente, agendamento, retry/backoff, heartbeat, histórico configurável; sem promessa de todos os conjuntos nacionais | 
| Busca e paginação | Implementado | API com filtros; somente base coletada |
| Câmara | Parcial | Coleta automática com cursor: deputados, proposições, autoria, tramitação, perfis e votos nominais; histórico em preenchimento |
| Senado | Parcial | Lista atual, processos/autorias e detalhes pelo serviço atual; votos do Senado ainda pendentes |
| Proveniência e histórico | Parcial | IDs/URLs/hashes/versões; publicação e validação humana não normalizadas |
| Identidade e mandatos | Parcial | Identidade por fonte; sem fusão por homônimos; detalhes históricos sob demanda |
| Projetos, leis e tramitação | Parcial | Proposições e documentos de tramitação; vínculo com lei não integrado |
| Votações | Parcial | Lista e documento de votos; sem inferência simbólica |
| Fontes nacionais e cobertura | Parcial | Matriz honesta; sem percentual nacional ou cadastro geográfico completo |
| Tenants e papéis | Parcial | Autenticação e isolamento no servidor; sem PostgreSQL/RLS ou MFA |
| IA com fontes | Pendente | Busca de documentos coletados; sem modelo generativo ou embeddings |
| Monitoramentos | Parcial | Persistência por tenant e eventos após alterações; sem envio externo |
| Relatórios | Parcial | CSV paginado e impressão de cobertura; sem PDF automático |
| Fila e recuperação | Implementado no ambiente local | Lease, retry, backoff, dead letter, upserts |
| Administração | Parcial | Fontes/runs/fila; bootstrap CLI; sem gestão completa de planos/identidades |
| TSE, legislação, SAPL, estados e municípios | Não integrado | Adaptadores de ingestão e validação ainda precisam ser implementados |
| Planos e assinaturas | Parcial | Planos configuráveis sem preços, limite real de monitoramentos e schema de assinaturas; sem checkout ou cobrança |
| Deploy | Preparado, não publicado | Docker/CI/healthcheck; falta ambiente público e validação de produção |

## Próximas etapas necessárias para o produto solicitado
1. Migrar backend e modelo para PostgreSQL, ampliar schema de mandatos, leis, comissões e jurisdições e validar RLS com dois tenants.
2. Ampliar votos do Senado e demais datasets históricos; TSE e publicação de normas com evidência.
3. Ingestão estadual e SAPL por município/IBGE com autorização e limites próprios.
4. Gestão de usuários, MFA, recuperação de conta e auditoria administrativa.
5. RAG com evidência por afirmação, limites por tenant e resistência a instruções embutidas nos documentos.
6. SMTP opt-in e relatórios PDF; gateway somente após autorização expressa.
7. Publicação em staging, suíte E2E em navegadores, testes de carga e segurança; produção após verificação.

A ausência de integrações na tabela é trabalho de implementação pendente; não é atribuída a falta de credenciais quando a fonte é pública. Serviços externos de IA/e-mail/gateway e publicação dependem de configuração específica e não foram provisionados.
