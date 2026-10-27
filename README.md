# Observatório Legislativo Brasil

Aplicação local de transparência parlamentar com dados oficiais, rastreabilidade, busca paginada, perfis, documentos, cobertura e monitoramentos por organização. **Implementação parcial** da especificação nacional: o estado real de cada integração aparece no produto. Não há dados simulados na base de produção.

## Iniciar

Requer Python 3.11 ou superior. Sem bibliotecas externas.

```sh
python -m app.server
```

Abra http://127.0.0.1:8080. A atualização automática inicia com o servidor: percorre todas as páginas das consultas suportadas, preserva cursores e revisita as fontes periodicamente. Clique em **Dashboard por político**, pesquise e selecione o parlamentar. Os indicadores se atualizam a cada 30 segundos enquanto a página estiver aberta.

As consultas manuais delimitadas anteriores continuam disponíveis (opcionais):

```sh
python -m app.sync --dataset all --max-pages 5
python -m app.worker
```

A interface informa lacunas durante a carga inicial. Câmara: lista de deputados, proposições, autoria, tramitação, perfis e votos nominais. Senado: senadores e processos/autorias pelo serviço atual, incluindo decisões estruturadas e detalhes. O comando manual app.sync mantém seu limite explícito de páginas; o motor automático não usa esse limite. Histórico extenso é processado em segundo plano e pode levar dias. Veja [atualização automática e metodologia](docs/ATUALIZACAO_AUTOMATICA.md).

Crie uma organização e seu administrador sem passar senha na linha de comando:

```sh
python -m app.auth --tenant "Minha organização" --email "seu-email@exemplo.com"
```

Para a conta operacional que poderá enfileirar coletas pela interface, use explicitamente `--role superadmin`. Não há senha padrão. Entre em **Configurações**. As consultas públicas funcionam sem login; monitoramentos são privados por organização.

## Validar

```sh
python -m unittest discover -s tests -v
python -m compileall -q app
node --check web/app.js
```

Veja [operação e recuperação](docs/OPERACAO.md), [arquitetura e segurança](docs/ARQUITETURA.md), [matriz de requisitos](docs/ESCOPO.md) e [evidências de validação](docs/VALIDACAO.md).

## Limites

Esta versão não é o SaaS nacional completo. Next.js/PostgreSQL são preferidos na especificação; a base executável usa Python/SQLite para permitir operação verificável sem provisionar serviços ou reutilizar credenciais. O isolamento é aplicado no servidor e testado, mas não há PostgreSQL/RLS, MFA, checkout, envio de e-mails, IA generativa ou ingestão nacional. Leis, TSE, assembleias, municípios e SAPL ainda não estão integrados. Nenhuma implantação pública foi realizada.

A plataforma informa e não recomenda voto. Proposta não equivale a lei publicada; publicação não comprova implementação; votos simbólicos não são convertidos em votos individuais.


## Economia e comparações

A evolução preserva os módulos anteriores. Consulte [operação, fontes, limites e rollback](docs/EVOLUCAO_ECONOMIA.md). Novas áreas: Brasil em números, comparação de governos, atividade observada por Casa, cadastros partidários e supervisão das fontes. Dados não integrados não recebem valores simulados.
