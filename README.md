# Observatório Legislativo Brasil

Aplicação local de transparência parlamentar com dados oficiais, rastreabilidade, busca paginada, perfis, documentos, cobertura e monitoramentos por organização. **Implementação parcial** da especificação nacional: o estado real de cada integração aparece no produto. Não há dados simulados na base de produção.

## Iniciar

Requer Python 3.11 ou superior. Sem bibliotecas externas.

```sh
python -m app.server
```

Abra http://127.0.0.1:8080. Em outro terminal, colete os dados:

```sh
python -m app.sync --dataset all --max-pages 5
python -m app.worker
```

A interface nasce vazia e informa lacunas; a coleta real depende da disponibilidade das APIs oficiais. A rotina padrão processa somente cinco páginas de cada consulta e registra parcialidade. Senado: senadores em exercício. Câmara: deputados, proposições e votações dos últimos 30 dias; detalhes, autoria, tramitação, histórico e despesas consultáveis sob demanda após autenticação.

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
