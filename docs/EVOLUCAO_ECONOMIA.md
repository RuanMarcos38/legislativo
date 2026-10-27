# Evolução política e econômica — operação e limites

## Arquitetura preservada

Python 3.11, servidor HTTP da biblioteca padrão, SQLite/WAL, JavaScript e CSS existentes. Nenhum framework, provedor, usuário, senha, sessão ou integração de outro projeto foi substituído. Os módulos antigos e suas rotas foram mantidos. Novos módulos usam o mesmo banco, os mesmos controles de acesso e o mesmo tema visual.

Baseline: commit f2bc8b1bcd1dafe9135039d525c2ce167b51a944. Antes da alteração, 71 testes passaram. Backup consistente por SQLite Backup API e arquivo do código em `work/evolution-backup`, fora dos arquivos públicos e fora do Git. A comparação posterior preservou todos os IDs anteriores, usuários, organizações, sessões, planos e monitoramentos.

## Novas rotas

- `#economia`: Brasil em números, séries, períodos, origem, disponibilidade e revisões.
- `#governos`: comparações por mandato, incluindo mandatos não consecutivos, períodos equivalentes e lacunas explícitas.
- `#ranking`: contagens observadas dentro de uma Casa, com filtros e despesas de uma mesma natureza.
- `#partidos`: cadastros coletados por sigla, com distribuição por UF e explicação das limitações históricas.
- `#consulta`: consulta guiada a fatos estruturados; sem LLM e sem nova credencial.
- `#supervisao`: histórico, disponibilidade, falhas e solicitação de consulta. Somente administrador global; acesso técnico também protegido no servidor.

Novas APIs: `/api/economy`, `/api/economic-revisions`, `/api/governments`, `/api/rankings`, `/api/assistant`, `/api/source-status`, `/api/analytics/export`. A solicitação de atualização econômica usa POST `/api/economy/sync`, sessão de superadmin, origem e CSRF. Interfaces públicas não recebem filas ou configurações internas.

## Migrações aditivas

- 006: observações, revisões, filas e histórico de consultas econômicas.
- 007: verificação periódica de disponibilidade das fontes.
- 008: histórico do BCB em lotes anuais independentes.
- 009: índices de leitura das despesas existentes. Não altera valores.

As migrações são executadas antes de iniciar o servidor e os coletores. As consultas públicas usam conexões sem execução de migrações. Uma falha na inicialização fecha a conexão. Essa separação corrigiu uma disputa de gravação descoberta durante os testes reais.

## Atualização e cache

Os workers econômicos e as verificações de disponibilidade são executados a cada 600 segundos, com leases, timeout, retentativas e proteção de unicidade. O último valor válido é mantido se a fonte falhar. Os dados persistidos são o cache de leitura. As verificações de fontes usam ETag/Last-Modified quando disponíveis; esses cabeçalhos não são apresentados como data de publicação oficial.

A consulta frequente não significa nova medição estatística. PIB e IPCA preservam suas competências e periodicidades. A data de publicação fica nula quando não fornecida pela API; não se inventa uma data a partir da consulta.

O histórico do BCB é dividido em anos e executado em segundo plano. Séries atuais são consultadas em janela menor para reduzir o tempo de resposta. Histórico pendente não é apresentado como completo. Os coletores legislativos e financeiros existentes continuam progressivos: verificar uma fonte a cada dez minutos não garante importar todas as suas páginas nesse intervalo.

Na instalação local, a opção `AUTO_SYNC_ENABLED` foi reativada porque a auditoria anterior confirmou que estava desligada. As opções financeiras foram preservadas e foi acrescentado o worker econômico. Nenhuma variável de credencial foi alterada. No Compose, o web continua sem coletores para evitar duplicar o worker dedicado; os novos coletores são iniciados no worker.

## Séries oficiais conectadas

IBGE, API de agregados, metadados verificados:
- Tabela 1846, variável 585, categoria 90707: PIB nominal trimestral.
- Tabela 1620, variável 583, categoria 90707: índice de volume do PIB, média 1995 = 100.
- Tabela 5932, variáveis 6564 e 6561, categoria 90707: crescimento trimestral e frente ao mesmo trimestre do ano anterior.
- Tabela 6784, variáveis 9810 e 9812: crescimento real anual e PIB per capita corrente.
- Tabela 1737, variáveis 63, 2265, 69 e 2266: IPCA mensal, em 12 meses, no ano e número-índice.
- Tabela 6381, variável 4099: desocupação no trimestre móvel.
- Tabela 6390, variável 5929: rendimento nominal habitual, todos os trabalhos, pessoas ocupadas de 14 anos ou mais com rendimento.

BCB, SGS, definições verificadas no catálogo oficial:
- 432: meta Selic, % ao ano, diária.
- 13621: reservas internacionais, conceito caixa, US$ milhões, diária.
- 13762: DBGG / PIB, metodologia utilizada a partir de 2008, mensal.
- 4513: DLSP / PIB, setor público consolidado, mensal.
- 1: dólar americano, livre, venda diária, R$/US$.
- 4478: saldo nominal da DLSP, setor público consolidado, R$ milhões, mensal.
- 4583: NFSP sem desvalorização cambial, resultado nominal, fluxo mensal corrente, setor público consolidado, R$ milhões. Não equivale ao resultado primário do Governo Central.

Metadados: `https://servicodados.ibge.gov.br/api/v3/agregados/{tabela}/metadados` e `https://dadosabertos.bcb.gov.br/`. A definição e o endereço exato de cada série estão em `app/economic_catalog.py` e acompanham os dados públicos.

## Cálculos e comparação

Decimais são armazenados como texto e calculados com Decimal. As despesas existentes permanecem em centavos inteiros. Variação percentual usa base positiva; base zero ou negativa resulta em não aplicável. Diferenças de taxas usam pontos percentuais. Fluxos, estoques, índices e taxas permanecem distintos.

Comparações usam períodos completos, sem recortar uma observação oficial entre dois governos. Lacunas impedem o resumo. Séries diárias são comparadas pelo último valor publicado de cada mês fechado. Não se misturam durações diferentes em comparação de mandato completo; nesses casos são exigidos períodos equivalentes. A média é explicitamente aritmética das observações; não representa ponderação por dias.

A correção monetária aplica o IPCA do fim do período original e o índice da referência. É uma convenção de poder de compra, não uma reconstrução do PIB em volume. O deflator e a referência acompanham a exportação. Séries em moeda estrangeira ou sem índice equivalente não são corrigidas silenciosamente.

Proposto, aprovado em etapa, norma informada pela Casa e lei com publicação conferida continuam separados. A nova taxa por perfil divide projetos com aprovação em etapa entre projetos com histórico consultado, exibindo numerador, denominador e fórmula. Não é taxa de aprovação final.

## Rankings e partidos

Os rankings descrevem documentos observados e não qualidade. A mesma proposição é contada uma vez por parlamentar; coautoria em mais de um perfil não autoriza somar a coluna para obter o total único da Casa. O ranking financeiro exige natureza e componente comparáveis, sem tratar reembolso, débito de cota ou autorização como o mesmo evento.

A tela de partidos agrupa cadastros disponíveis. Não declara bancada atual nem atribui produção histórica ao partido atual. Filiação com vigência, mandato efetivamente exercido, normalização histórica e métricas partidárias de produção continuam indisponíveis até validação documental. Não existe ranking de melhor presidente.

## Exportação

CSV, XLSX, PDF e JSON dos dados filtrados; gráfico selecionado em SVG. Exportações genéricas incluem título, emissão em Brasília, filtros, metodologia e referências. O conjunto selecionado é completo ou a solicitação é rejeitada por limite, sem truncamento silencioso na primeira página. Limites: 10000 linhas, ou 1000 no PDF. CSV neutraliza fórmulas e XLSX usa texto explícito. PDF é relatório dos dados e metadados; não é uma reprodução visual integral do dashboard com todos os gráficos.

A exportação financeira original foi preservada, ganhou JSON público sem diagnósticos internos e passou a identificar a emissão em Brasília. As páginas antigas de relatório usam o novo exportador completo, mantendo o endpoint antigo para compatibilidade.

## Pendências reais

- Comex Stat estava em manutenção e a API respondeu 503. Exportações, importações, saldos, parceiros, produtos e UFs não receberam valores inventados.
- O acesso ao catálogo do Tesouro falhou na verificação do certificado nesta instalação. A validação TLS não foi desativada. DPF, custo/prazo, RTN, receitas e despesas não estão integrados.
- O valor nominal da DBGG ainda não foi conectado; não se calcula a partir de conceitos incompatíveis.
- Histórico do BCB em coleta progressiva; falhas transitórias preservam dados e aparecem como atraso.
- Filiações históricas, normalização por tempo de mandato e produção por partido ainda não validadas.
- Leis sancionadas com autoria conferida, vetos, decretos, MPs, investimento e execução orçamentária presidencial não integrados.
- Votos do Senado, comissões, relatorias e sessões verificadas não foram declarados completos. Estados e municípios permanecem progressivos, por instituição.
- Fotos presidenciais não foram adicionadas sem uma imagem oficial e licença verificadas.
- Consulta analítica é guiada e determinística; não há chatbot generativo nem nova chave de IA.
- Não há novo domínio nem publicação na internet. A verificação real refere-se à instalação local em 127.0.0.1:8081. Concorrência de produção e disponibilidade prolongada ainda precisam de validação em infraestrutura publicada.

## Rollback seguro

Voltar o código ao commit baseline ou ao arquivo de código preservado. As tabelas e índices novos podem permanecer: não removem colunas ou registros usados pela versão anterior. Não restaurar automaticamente uma cópia antiga do banco sobre dados coletados depois do backup. Em recuperação integral, parar os coletores, preservar o banco atual e restaurar a cópia consistente somente com decisão explícita sobre os dados posteriores.

Não foram executadas migrações destrutivas, remoção de usuários ou alteração de senha. Evidências de regressão, validação real, preservação e screenshots ficam em outputs; o relatório final registra os resultados observados e as pendências, sem certificação de funcionamento de 100%.
