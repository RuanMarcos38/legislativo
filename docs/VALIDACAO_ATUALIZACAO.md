# Verificação da atualização automática e do dashboard

Data: 26/10/2026. Continuação da base funcional anterior; os relatórios anteriores são evidência histórica da primeira versão.

**História verificada:** a pessoa pesquisa e escolhe um parlamentar, a interface consulta /api/politician, o servidor agrega registros oficiais e suas evidências no banco, e o dashboard mostra contagens e pendências dentro do período selecionado. O motor automático consulta as fontes em segundo plano e preserva o cursor.

| Fronteira | Estado | Evidência |
|---|---|---|
| Interface | Confirmada | Menu Dashboard por político, busca nominal e cartão de seleção funcionaram no navegador |
| Interface → API | Confirmada | Seleção abriu URL individual e retornou metrics, sync, timeline e items |
| API → banco/fontes | Confirmada | Senado atual /processo retornou 1.019 proposições na consulta de autoria usada como amostra, sem usar o endpoint legado |
| Dados → resposta | Confirmada | Snapshot com integridade SQLite ok; contagens distintas, campos não apurados como null e pendências de tramitação |
| Resposta → interface | Confirmada | Filtro a partir de 01/01/2026 alterou a amostra para 94 proposições e 20 projetos/PECs; tabela e evidências coerentes com o mesmo período |
| Processo automático | Confirmado ativo | /api/automatic retornou worker_online=true e progresso persistido; requisições oficiais executadas em segundo plano |
| Preservação | Confirmada | Backup consistente antes da migração; organizações, usuários, sessões, monitoramentos e eventos anteriores preservados |
| Navegador | Confirmado para o percurso testado | Sem erros de console; layout estreito conferido; bloco de votos mostra ausência de integração do Senado como não apurado |

## Testes executados
- 39 testes automatizados passaram em 34,524 segundos no Windows.
- Compilação Python e verificação de sintaxe JavaScript passaram.
- Os 21 testes anteriores continuam passando.
- Novos testes: migração aditiva; retomada após reinício e todas as páginas; loop de paginação; falha/backoff/dead letter; lease expirado; proteção contra resposta de worker atrasado; prioridade de tarefas antigas; aprovação de requerimento/urgência/parecer separada de projeto; deduplicação; período baseado na data de apresentação; coautoria; contrato atual do Senado; evidência de decisão preservada entre documentos; votos nominais sem inferência simbólica; validação de entrada e heartbeat.
- Dados sintéticos usados em testes ficam somente em bancos temporários.
- CI da atualização é verificado no PR; não se presume um build remoto apenas pela presença do workflow.

## Correção encontrada na verificação
O bloco de votos nominais não havia sido inserido no HTML montado pelo cliente. A montagem foi corrigida, a sintaxe revalidada e a interface voltou a mostrar o bloco, incluindo o estado explícito de integração pendente para o Senado.

## Limites
As contagens da amostra são um retrato da coleta, não avaliação do parlamentar nem cobertura total de sua atuação. Os detalhes continuam sendo preenchidos. O arquivo automatic-live-verification.json preserva a coleta inicial da amostra; novas execuções podem elevar contagens e reduzir pendências.

Não foram concluídos a carga histórica inteira, todos os datasets nacionais, publicação de normas, votos do Senado, auditoria WCAG completa, testes de carga ou implantação pública. A atualização automática depende de serviço ativo e conectividade.
