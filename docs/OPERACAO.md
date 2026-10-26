# Operação, backup e recuperação

## Ambiente isolado
Python 3.11+, sem instalação de pacotes. Nenhum banco ou serviço de outro projeto é necessário. O arquivo SQLite fica em data/observatorio.db, ignorado pelo Git. Não coloque dados privados ou segredos no repositório. As variáveis de .env.example devem ser exportadas no processo; não há carregamento implícito de .env.

Inicie com `python -m app.server`. O servidor ouve apenas 127.0.0.1 por padrão. Crie a conta com `python -m app.auth --tenant "Organização" --email "endereço"`; a senha é solicitada de maneira interativa, nunca por argumento. Mínimo de 12 caracteres. A conta padrão é admin da organização. Use --role superadmin somente para a conta de operação global.

## Ingestão
A partir da atualização do dashboard, o servidor inicia o motor automático por padrão. O motor percorre todas as páginas e salva o cursor. As instruções abaixo descrevem o coletor manual legado; seus limites não se aplicam ao novo motor. Consulte [ATUALIZACAO_AUTOMATICA.md](ATUALIZACAO_AUTOMATICA.md).

`python -m app.sync --dataset all --max-pages 5` realiza consultas delimitadas nas fontes oficiais. Há limites de páginas e intervalo entre páginas; não representa importação integral. Para lotes históricos da Câmara: `python -m app.sync --dataset camara_proposals --year 2024 --max-pages 20`. Isso consulta o ano selecionado; não garante todos os documentos, mandatos ou relacionamentos. A lista atual de parlamentares não é um histórico completo.

O worker `python -m app.worker` processa as consultas enfileiradas pelo superadmin. Uma tarefa tem lease de 30 minutos, cinco tentativas e backoff. Com o limite padrão de cinco páginas, o lease excede o tempo previsto das requisições e retries. Tarefa interrompida poderá ser retomada após expirar o lease; upserts são idempotentes. O checkpoint do run é diagnóstico: uma nova tentativa repete a consulta a partir da primeira página, com deduplicação. Tarefas dead exigem revisão da causa e uma nova coleta; não são descartadas silenciosamente.

Contagens exibidas são registros locais e processamentos por execução, nunca número de parlamentares únicos nacionais ou percentual de cobertura. IDs de fontes diferentes não são unificados por nome. Falha após algumas páginas preserva os dados e marca o run como falho, sem alegação de conclusão.

## Monitoramentos e relatórios
Um analista/admin cria termos de 2 a 120 caracteres. Documentos novos ou alterados que contiverem o termo geram eventos na organização correspondente. Não há backfill retroativo nem envio de e-mail. Leitores consultam, mas não alteram monitoramentos. Remover o termo remove os eventos privados vinculados.

O CSV exporta uma página de até 100 registros, com filtros, emissão, hash e URL. A interface não chama essa exportação de conjunto completo. Fórmulas são neutralizadas nas células. O relatório de cobertura pode ser impresso pelo navegador; não há geração automatizada de PDF.

## Backup consistente
Use a API backup do SQLite; não copie um banco em escrita sem considerar WAL:

```sh
python -c "import sqlite3; s=sqlite3.connect('data/observatorio.db'); d=sqlite3.connect('data/backup.db'); s.backup(d); d.close(); s.close()"
```

Guarde cópia criptografada fora do servidor, com acesso restrito e retenção definida pelo operador. O banco inclui hashes de senhas e sessões; trate backups como privados. Teste restauração em diretório isolado. Pare web e worker, preserve a base atual, restaure o backup e execute `PRAGMA integrity_check` antes de reiniciar. Nunca substitua o único backup.

## Docker
`docker compose up --build -d` cria web e worker com volume próprio. Porta publicada apenas no loopback do host. Crie o usuário com `docker compose exec web python -m app.auth --tenant "Organização" --email "endereço"`. Coleta CLI: `docker compose exec web python -m app.sync`. Imagem sem usuário root. Docker não foi presumido instalado: consultar relatório de validação.

## Publicação e rollback
Esta entrega não inclui infraestrutura provisionada. Antes de publicar: substituir o servidor de desenvolvimento por serviço de produção, HTTPS, cookies Secure, política de hosts e proxy confiáveis; migrar para PostgreSQL com RLS; avaliar MFA e recuperação de conta; testes de carga, acessibilidade, ameaças e LGPD; retenção e observabilidade. Não exponha BIND_HOST=0.0.0.0 sem a proteção de rede do compose.

A migração 001 é de bootstrap e só contém DDL aditivo. Novas alterações exigem novas migrações e teste sobre cópia do banco. Para rollback de código, volte ao commit anterior em uma nova implantação e restaure banco de backup validado se o formato tiver mudado. Nenhum script apaga bancos automaticamente.

Credenciais de IA, e-mail e gateway não estão configuradas. Cobrança real requer autorização específica. Não há domínio ou URL pública declarada.

A API de votações da Câmara restringe a diferença entre as datas a três meses. O conector consulta os últimos 30 dias por padrão. Com --year em votações, consulta janeiro do ano selecionado; importar um ano completo requer lotes mensais (ainda não automatizados).

## Planos e usuários da organização
A migração 002 inclui planos sem preços e assinaturas sem gateway ativo. O plano gratuito limita a cinco monitoramentos; demais limites são administrativos e não representam uma oferta comercial. A aplicação aplica o limite no servidor, dentro de transação. Configuração por banco local, sem cobrança ou mudança automática de assinatura.

Configurações exibe o ID da organização autenticada. Para adicionar um leitor à mesma organização: `python -m app.auth --tenant-id ID --email endereco --role reader`. A senha é solicitada no terminal. Somente o operador local pode provisionar usuários nesta versão.
