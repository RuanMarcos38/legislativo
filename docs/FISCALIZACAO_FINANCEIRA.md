# Fiscalização Financeira

## Integração e preservação

Módulo aditivo ao Observatório, na branch `codex/fiscalizacao-financeira`, a partir de `e6fef0ddb8cf6c3fa750895a53199ec59c2968bc`. A migração 004 acrescenta tabelas e índices, sem apagar, renomear ou recriar entidades anteriores. Identidades oficiais reutilizam `records`; dados financeiros públicos são compartilhados, como os demais registros oficiais. Usuários, sessões, organizações, planos, monitoramentos e seus controles de acesso permanecem separados e preservados.

Antes da alteração foram criados ZIP do código e backup consistente do SQLite, com integrity_check=ok. Backups privados ficam em `work/finance-reference`, fora do repositório e do pacote público. A carga anterior tinha 15.390 registros públicos, zero usuários e zero organizações; novos registros legislativos continuam entrando pelo serviço existente.

## Fontes implementadas

| Fonte | Importação | Interpretação e limites |
| --- | --- | --- |
| Câmara CEAP | CSV anual oficial ZIP, histórico programado desde 2008; API individual paginada disponível ao superadmin | Valor líquido é débito na cota, não limite disponível nem prova de pagamento ao parlamentar. Documento e glosa são separados. Arquivo anual prevalece sobre a consulta estreita da API. |
| Senado CEAPS | Web Service anual oficial, com codSenador e id do lançamento | Valor reembolsado publicado. Mandato, data do pagamento e comprovante digital não são inferidos. Anos sem retorno ou com falha ficam explícitos. |
| ALESC, diárias | CSV anual publicado desde novembro de 2011 | Vínculo Deputado e conta identificada permitem associação. Natureza AUTORIZADO / concedido; não comprova pagamento. Servidores não são vinculados automaticamente a deputados. |
| ALESC, gabinetes | CSV anual publicado desde 2011 | Sem identificador estável de lançamento e de deputado. Preservado como institucional pendente, sem totalização individual ou associação por simples nome. Pode sobrepor diárias; não se soma ao conjunto de diárias. |

Documentação e contratos conferidos em 26/10/2026:

- [Câmara — campos e significado dos valores](https://dadosabertos.camara.leg.br/howtouse/2023-12-26-dados-ceap.html)
- [Câmara — API e arquivos anuais](https://dadosabertos.camara.leg.br/swagger/api.html)
- [Senado — catálogo administrativo](https://www12.senado.leg.br/dados-abertos/conjuntos?grupo=senadores&portal=Administrativo)
- [Senado — contrato do serviço](https://adm.senado.gov.br/adm-dadosabertos/v3/api-docs)
- [ALESC — gabinetes](https://transparencia.alesc.sc.gov.br/gabinetes-parlamentares/dados-abertos)
- [ALESC — diárias](https://transparencia.alesc.sc.gov.br/diarias/dados-abertos)

O endpoint individual da Câmara retornou listas vazias nas amostras consultadas, apesar de o arquivo anual oficial conter registros. A aplicação usa o arquivo anual como via principal e não interpreta resposta vazia como gasto zero.

## Precisão, identidade e conciliação

SQLite pode converter NUMERIC em REAL. Por isso, dinheiro é INTEGER em centavos com CHECK de tipo, normalizado com Decimal, com o texto original preservado. Não se usa FLOAT na persistência ou totalização. As respostas monetárias são strings decimais. Somatórios SQLite recebem exclusivamente inteiros; eventual overflow gera erro. Apenas as barras visuais usam magnitude aproximada, sem produzir valores monetários.

Documento Câmara não é uma chave única de lançamento. A deduplicação considera identificação institucional, documento, lote, ressarcimento, parcela e competência, sem depender do valor que pode ser corrigido. Colisões e documentos sem identificação ficam pendentes. Documentos com restituição publicada e suas parcelas são excluídos dos totais até conciliação. Valores negativos aparecem em natureza separada, sem virar despesas positivas.

Cada registro guarda fonte, identidade quando comprovada, competência, datas disponibilizadas, categoria, descrição original, valor exato e original, fornecedor publicado, documento, links, data de coleta, atualização da fonte quando informada, estado de verificação e lote. CPF e identificadores pessoais desnecessários são removidos do payload preservado. A fonte original possui SHA256 por resposta; alterações e versões de lançamentos ficam na auditoria.

Não há custo total consolidado, comparação eleitoral, acusação de irregularidade, soma de remuneração bruta e líquida ou soma de etapas financeiras. Mandato não é adivinhado pelo ano; a Câmara fornece código de legislatura, exibido como tal. UF vem do cadastro disponível e não comprova situação histórica. Desconhecido permanece desconhecido; zero confirmado permanece zero.

## Automação e operação

`python -m app.server` inicia a coleta financeira automaticamente. `python -m app.worker` permite execução separada. No Compose as duas coletas são desativadas somente no serviço web e executadas no worker.

Variáveis novas, sem alterar credenciais existentes:

- `FINANCIAL_SYNC_ENABLED=1`: ativa o serviço; `0` o desativa.
- `FINANCIAL_START_YEAR=2008`: início da fila histórica; ALESC inicia em 2011. O ano inicial é escopo configurado, não prova de cobertura de todas as fontes.

Anos recentes são revisados diariamente; anos antigos a cada 30 dias. Leases com token, renovação durante arquivos grandes, cursor de paginação, retries com espera progressiva e falha terminal após cinco tentativas permitem retomada. Falhas ficam visíveis na cobertura. Nenhum arquivo inválido substitui os últimos valores confirmados. Registros ausentes em uma nova consulta anual ficam pendentes, sem apagar a auditoria.

Arquivos anuais são normalizados em banco temporário em disco; o banco principal recebe a transação final. CSVs grandes são percorridos em fluxo. O serviço local precisa continuar ativo e com internet. A importação histórica é progressiva, não concluída na entrega inicial.

Leitura pública: `/api/financial`, `/api/financial/coverage`, `/api/financial/export`. `POST /api/financial/sync` usa as proteções existentes de origem, sessão, CSRF e papel superadmin. Não aceita URL arbitrária. Download segue allowlist estrita de host e caminho; redirecionamento entre fontes não leva credenciais. Limite e controles de requisições existentes são preservados.

## Interface e exportações

Menu Fiscalização Financeira e aba Gastos e Custos. Filtros por identidade, nome, fonte/cargo, UF, legislatura informada, competência, categoria, fornecedor, natureza, componente e verificação. Municípios e outras Casas sem integração não são oferecidos como se tivessem dados. A tabela contém comprovantes quando publicados e datas ausentes identificadas.

CSV e Excel exportam toda a seleção filtrada até 10.000 registros. PDF paginado até 1.000. Acima disso, o usuário deve refinar os filtros; não há corte silencioso. Valores exatos são texto no Excel. Fórmulas de planilha são neutralizadas. Cada registro mantém fonte e coleta. PDF é relatório documental, sem gráficos de ranking.

## Bloqueios e pendências explícitas

- **CGU:** documentação e parâmetros de `/api-de-dados/emendas` e `/api-de-dados/emendas/documentos/{codigo}` verificados. Consulta real sem chave retornou HTTP 401; usa cabeçalho `chave-api-dados`. Sem chave e sem conciliação entre identificadores de autor não há importação, documentos ou valores atribuídos. Nome isolado não basta. Estruturas e painel separado existem; conector operacional e reconciliação estão pendentes. Não basta definir uma variável para considerar essa integração concluída.
- **DOU / INLABS:** link oficial e limites apresentados; ingestão autenticada, interpretação e vínculo contextual não implementados. Atos não são convertidos em pagamentos.
- **Demais estados / CLDF e municípios:** nenhum outro conector validado nesta entrega; cadastro geográfico municipal e mapeamento por instituição pendentes. Não há cobertura nacional de despesas.
- **Remuneração, benefícios, pessoal, contratos e outras viagens:** não integrados fora dos conjuntos indicados; não estimados nem somados.
- **IA:** a aplicação anterior não possui IA generativa configurada. Consulta e cálculo são determinísticos. Integração de IA permanece pendente, sem criação de credenciais ou envio de registros a provedores.
- **Produção pública:** nenhum domínio, servidor remoto ou credencial de implantação foi indicado. Entrega em ambiente local e código em PR, sem publicar em outro projeto.

## Rollback

Desative a coleta com `FINANCIAL_SYNC_ENABLED=0`, reinicie o processo e reverta o commit do módulo ou restaure o ZIP de código anterior. Mantenha as tabelas novas: isso preserva os registros e a auditoria e não interfere no código anterior. Não execute DROP, reset ou restauração automática do banco antigo. O backup anterior é um ponto de recuperação a ser usado em cópia isolada; restaurá-lo sobre o banco vivo descartaria coletas posteriores.
