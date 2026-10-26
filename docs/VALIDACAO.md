# Evidências de validação — 26/10/2026

## Execução local confirmada
Python 3.11.9 e Node 24.22.1 no Windows. Aplicação local iniciada em http://127.0.0.1:8080. Nenhuma URL pública foi publicada.

- `python -m unittest discover -s tests -v`: **21 testes passaram**, 19,947 segundos na execução final.
- `python -m compileall -q app`: passou.
- `node --check web/app.js`: passou.
- `python -m app.verify`: perfis da Câmara e Senado, tramitação e documento de votos recebidos de APIs reais; integridade SQLite e backup restaurado com integrity_check=ok.
- Navegador real: painel renderizado; busca nominal retornou um registro com paginação coerente; perfil exibiu fonte/data/hash; Configurações exibiu formulário de login e limites reais dos serviços.
- Captura do painel incluída na entrega local. Testes HTTP validaram login, cookie HttpOnly, CSRF, consultas privadas e gravação de monitoramento.
- O Docker não estava disponível no PATH; o build da imagem não foi validado localmente. O workflow CI prepara esse check, mas não se presume executado ou aprovado.

## Coleta oficial observada
513 identidades da lista atual de deputados; 81 senadores em exercício; 100 proposições; 78 votações no intervalo consultado. Estas contagens são da base local, não prova de cobertura histórica ou nacional. A importação de proposições foi limitada a uma página. As consultas de deputados e senadores chegaram ao fim da lista retornada, e a de votações ao fim do intervalo dos últimos 30 dias.

Fontes: [Câmara](https://dadosabertos.camara.leg.br/swagger/api.html) e [Senado](https://www12.senado.leg.br/dados-abertos). As URLs concretas das amostras e horários UTC estão em [live-verification.json](live-verification.json).

Falhas encontradas e corrigidas: consulta de votações com intervalo superior ao permitido; parâmetros de paginação enviados a rotas que não os aceitam; conexão SQLite não fechada pelo contexto padrão no Windows. As execuções falhas continuam no histórico local. Não foram apagadas para apresentar sucesso integral.

## O que os testes cobrem
Idempotência, histórico de versões, homônimos, mudança de partido, busca/paginação, caracteres SQL, múltiplos usuários na mesma organização, isolamento entre organizações, credenciais e expiração de sessão, allowlist de URL, falha de fonte, paginação parcial, contrato de detalhes, retomada de lease e dead letter, neutralização de fórmula CSV, healthcheck, Host, CSP/headers, CSRF e limite real do plano no servidor.

Os dados sintéticos dos testes ficam somente em diretórios temporários. Nunca foram inseridos na base real. Testes mockados não são descritos como ingestão real.

## Não verificado ou pendente
Lint por analisador dedicado; testes de carga e penetração; acessibilidade WCAG completa; viewport móvel; todos os percursos privados em navegador; PostgreSQL/RLS; MFA; gateway; SMTP; IA generativa; TSE/leis/SAPL/estados/municípios; cobertura nacional completa; build Docker e CI remoto. Responsividade tem regras CSS, sem alegação de validação móvel concluída.

## Verificação posterior no GitHub
O workflow [Validate #1](https://github.com/RuanMarcos38/legislativo/actions/runs/40325031917) concluiu com sucesso no commit `77f3526c62cb12151177ff68d08979e6737bef3e`. Executou testes em Linux, compilação Python, sintaxe JavaScript e build Docker. Esta evidência complementa a execução local; Docker continuou indisponível no computador local. A alteração posterior desta seção é somente documental.

A verificação final também confirmou healthcheck e recuperação HTTP de documento em cache. Foi corrigida a possibilidade de duas instâncias locais compartilharem a mesma porta no Windows; o 21º teste impede regressão desse comportamento.
