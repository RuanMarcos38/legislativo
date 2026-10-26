# Arquitetura e segurança

## Componentes
Interface HTML/CSS/JavaScript responsiva e acessível por teclado; API HTTP em Python; banco SQLite em WAL; worker separado. Sem recursos de terceiros no navegador. A opção reduz dependências e permite operação local. Não atende ainda à stack preferida Next.js/PostgreSQL nem ao conjunto completo de controles de um SaaS público.

## Dados e identidade
Chave composta fonte/tipo/identificador externo, URL, JSON bruto, JSON normalizado, SHA256, primeira/última alteração local, última coleta e versões. IDs distintos nunca são mesclados por nome. Mudanças de dados da fonte geram versões; snapshots de partido não são interpretados como histórico completo de filiação. Horários são UTC no banco e formatados pelo navegador na interface. Datas de publicação permanecem no documento original quando fornecidas; não há normalização universal, validação humana ou auditoria de correções manuais.

Dados públicos compartilhados estão em records/versions/runs/jobs. Tenants, users, sessions, watches e events armazenam dados privados. Filtros de tenant são aplicados no servidor para consultas e remoções; a ingestão entrega eventos a cada watch sem expô-los publicamente. Não há RLS no SQLite, logo a proteção é de aplicação, com testes explícitos. Não trate isso como RLS PostgreSQL validada.

## Autenticação
Senhas com scrypt e salt aleatório; sessão de 8 horas com token de 256 bits armazenado apenas como SHA256; cookie HttpOnly/SameSite=Strict; CSRF aleatório associado à sessão; Origin exato e cabeçalho de ação em POST. Logout invalida sessão. Login tem limite de cinco tentativas por IP em cinco minutos. Limite geral de 120 requisições/minuto/IP, por processo; não é um limitador distribuído.

Papéis: superadmin (opera coleta global), admin (organização), analyst (monitoramentos e consulta sob demanda), reader (somente leitura de área privada). Criação de usuários por CLI local. Não há convite, redefinição de senha ou MFA.

HTTP local: cookie não tem Secure para permitir operação em loopback. Publicação exige HTTPS/Secure e serviço de produção. Host restrito a localhost/127.0.0.1 na porta corrente evita DNS rebinding. Não há CORS. CSP limita recursos à própria origem; dados são escapados antes de inserir na interface; SQL usa parâmetros. Rotas estáticas têm lista fixa, sem concatenação de caminhos de usuário.

## Conectores
URLs HTTPS de Câmara e Senado em allowlist incluindo redirecionamentos; não aceitam URL arbitrária do cliente. Limite de resposta, timeout e retries. Falhas de contrato aparecem como falhas de coleta. Origem, documento e hash são preservados. Nunca se transforma votação simbólica em voto individual; respostas de votos são documentos oficiais brutos e orientação partidária não é voto pessoal. A aplicação não infere conversão em lei a partir de ementa ou rótulo de situação.

## Busca e IA
Busca textual simples com parâmetros SQL e paginação real. Não há ranking de políticos, recomendação eleitoral ou comparação julgadora. O assistente generativo/RAG não foi integrado e não existe chamada para provedor de IA. Não há necessidade de chave de IA para os fluxos implementados. Documentos externos são dados; nenhuma instrução neles é executada.

## Lacunas
Sem full text index, múltiplos mandatos normalizados, RLS, testes de penetração, validação WCAG completa, assinatura/checkout, envio de e-mail, métricas distribuídas, cadastro nacional IBGE ou ingestão estadual/municipal. O painel de cobertura não usa porcentagens sem denominador verificável.

## Planos e auditoria
A migração 002 cadastra planos sem preço, limites de monitoramento, referência de plano por organização e estrutura de assinaturas desativadas. A criação de monitoramentos aplica limite sob transação imediata. Criação e remoção geram auditoria sem copiar o texto privado para logs públicos. A trilha de auditoria ainda não cobre todas as operações administrativas.
