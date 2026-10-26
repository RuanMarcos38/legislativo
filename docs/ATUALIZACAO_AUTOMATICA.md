# Atualização automática e dashboard individual

## Preservação
A migração 003 só cria tabelas e índices. Não remove nem renomeia os registros, usuários, organizações, sessões e monitoramentos existentes. A atualização foi precedida de backup SQLite consistente, verificado com integrity_check. Os testes conferem preservação de dados existentes. O banco de backup fica em data/, fora do Git e do ZIP de código.

## Início e continuidade
`python -m app.server` inicia automaticamente a coleta em segundo plano. Não é necessário apertar um botão para cada consulta. O serviço precisa permanecer ativo, com acesso à internet; desligar o computador interrompe as consultas e a próxima execução retoma do cursor salvo.

`python -m app.worker` pode executar o mesmo motor separado do servidor. No Docker Compose o motor fica no worker e o servidor usa AUTO_SYNC_ENABLED=0. Os leases no banco evitam que dois processos processem o mesmo cursor simultaneamente. Tokens de lease impedem que uma resposta atrasada sobrescreva o progresso de outro processo após recuperação.

Cada requisição processa uma página, atomicamente. Só a ausência de uma próxima página válida conclui uma consulta da Câmara. O Senado retorna um array no serviço atual de processos. Um lote é idempotente, e um ciclo periódico revisita as fontes. Repetição circular de URL é erro, não conclusão. Falhas têm backoff e cinco tentativas, depois ficam visíveis como dead; superadmin pode reabrir por POST /api/automatic/retry com CSRF, preservando o cursor.

Uma consulta concluída significa apenas o escopo indicado, não todo o histórico brasileiro. Cada stream mostra páginas, itens, datas, escopo e erro. O painel detecta ausência de heartbeat e não chama dados antigos de atualização ativa.

## Escopo padrão do motor
- Câmara: deputados atuais e parlamentares identificados em autoria; proposições por ano de identificação de 1934 até o ano atual; autorias/coautorias por identificador parlamentar em todos os anos retornados; detalhes e tramitação; perfis; votações mensais desde 2023 e respectivos votos nominais.
- Senado: lista atual; processos por ano de identificação desde 1826 até o ano atual; consulta de autoria por código do parlamentar, sem fundir por nome; detalhes, autores estruturados, situações e decisões.
- Datas iniciais são escopos solicitados às APIs, não afirmações de existência ou completude histórica. A documentação da Câmara reconhece lacunas antes de 2001. Anos e conjuntos sem retorno ou com falha permanecem identificados.
- Fontes estaduais, municipais/SAPL, TSE, publicação oficial de normas, despesas em massa, discursos/comissões e votos do Senado ainda não integram este motor. Não são apresentados como cobertura completa.

Variáveis exportadas pelo operador: AUTO_SYNC_ENABLED (1/0), AUTO_CAMARA_START_YEAR (1934), AUTO_SENADO_START_YEAR (1826), AUTO_VOTES_START_YEAR (2023) e AUTO_REQUEST_INTERVAL (1 segundo). O arquivo .env.example não é carregado automaticamente. Reduzir um ano inicial amplia a fila; não exclui registros já coletados.

Consultas de autoria são revisitadas a cada seis horas após concluídas, assim como documentos e dados recentes. Consultas de anos/meses antigos são revisitadas mensalmente. O relógio do processo verifica novas datas/escopos a cada hora. Essas frequências não são garantias de disponibilidade ou de atraso máximo: uma carga inicial extensa e falhas da fonte aumentam o tempo de coleta. Parlamentares abertos na interface recebem prioridade; tarefas antigas ganham prioridade para não ficarem permanentemente bloqueadas.

## Indicadores
O menu Dashboard por político abre um seletor com busca por nome, Casa, UF e partido. Clicar no nome na lista de parlamentares também abre a página individual. A URL é compartilhável dentro da instalação: #politico/ID. O painel atualiza os dados exibidos a cada 30 segundos; isso não altera o intervalo de coleta oficial.

O período usa **data de apresentação** para proposições; um número/ano de renumeração não substitui essa data. Votos usam a data da votação e a interface explicita essa diferença. Registros sem data são declarados e excluídos de filtros datados.

- Proposições: IDs distintos vinculados à autoria/coautoria. Primeiro signatário, coautoria e posição não verificada ficam separados. Nenhuma proposição compartilhada é atribuída exclusivamente a uma pessoa.
- Projetos e PECs: tipos explicitamente listados na metodologia. Requerimentos e outros tipos são exibidos separadamente.
- Aprovação em etapa: projetos distintos com evento estruturado de aprovação. Uma proposta com três eventos aprovados é contada uma vez. Não significa aprovação final, lei publicada ou implementação.
- Câmara: códigos de tramitação 237, 238, 239, 240, 244, 1235, 1518 e 1519. Aprovação de parecer (336), urgência (196), recurso (191) e requerimentos (195 etc.) não entram. Cada evidência tem descrição, data e URL.
- Senado: decisões explícitas do serviço atual e situações APRVD documentadas nas autuações. Decisão de aprovação em um requerimento não entra no contador de projetos.
- Norma informada: vínculo/status que a Casa informou; não afirma que a publicação da norma foi conferida. Publicação e implementação são exibidas como não apuradas, e nunca como zero por falta de integração.
- Votos nominais: categorias exatas da fonte, por ID institucional. Resposta vazia não gera voto, ausência ou orientação partidária presumida. A coleta do Senado segue pendente.

Indicadores são contagens observadas. O painel mostra quantos projetos ainda não tiveram o histórico detalhado coletado e se a consulta de autoria terminou. Não há nota, ranking, taxa de sucesso político ou recomendação de voto.

## Fontes técnicas verificadas
[Câmara — API e arquivos](https://dadosabertos.camara.leg.br/swagger/api.html)
[Câmara — códigos de tramitação](https://dadosabertos.camara.leg.br/api/v2/referencias/proposicoes/codTipoTramitacao)
[Senado — documentação atual](https://legis.senado.leg.br/dadosabertos/api-docs/swagger-ui/index.html)
[Senado — tipos de decisão](https://legis.senado.leg.br/dadosabertos/processo/tipos-decisao)

O endpoint legado /senador/{codigo}/autorias.json informa depreciação e substituição por /processo. A nova integração usa /processo?codigoParlamentarAutor=... e /processo/{id}, conforme o contrato atual.

## Testar e observar
`python -m unittest discover -s tests -v`; `python -m compileall -q app`; `node --check web/app.js`.
Para executar um número delimitado de passos do motor, use `python -m app.automatic --steps 10`. O cursor permanece salvo e não significa que dez passos concluíram a base.
