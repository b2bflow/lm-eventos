# OmniFlow LM: backend

Django 6 + DRF + MongoEngine (dados de negócio) + SQLite (usuários) + Celery/Redis + Socket.IO.

## Rodar localmente

```bash
cd BackEnd
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env                                           # preencha os valores
docker compose up -d mongo redis
.venv/Scripts/python manage.py migrate                         # SQLite dos usuários
.venv/Scripts/python manage.py runserver
```

### Worker e beat do Celery

O worker processa eventos (`EventBus.publish`), a resposta da IA com debounce e as tarefas
periódicas. O beat dispara as tarefas periódicas definidas em `nucleus/beat_schedule.py`
(horários em America/Sao_Paulo). Rode os dois processos, além do servidor web:

```bash
# Worker (no Windows use --pool=solo)
.venv/Scripts/celery -A nucleus worker -l info --pool=solo
# Beat (um único processo em todo o ambiente)
.venv/Scripts/celery -A nucleus beat -l info
```

Em produção, o beat deve rodar em **uma única** instância para não duplicar tarefas.

## Webhook da Z-API

`POST /api/v1/gateway/webhook/zapi/?token=<ZAPI_WEBHOOK_TOKEN>`

- Sem token configurado (`ZAPI_WEBHOOK_TOKEN` ou Configurações > Sistema > token do webhook),
  todo webhook é recusado com 401. Na Z-API, cadastre a URL já com `?token=`.
- Mesmo número + mesmo texto em até `WEBHOOK_DEDUP_SECONDS` (120 s) é ignorado; reentrega
  com o mesmo `messageId` também.

## Testes

```bash
.venv/Scripts/python -m pytest
```

Os testes usam `nucleus/settings_test.py`: Mongo em memória (mongomock), Redis falso
(fakeredis), Celery eager e Z-API/Socket.IO substituídos por fakes no `conftest.py`.
`tests/test_security.py` varre todas as rotas da API (login obrigatório, exceto as públicas com
proteção própria) e cobre XSS por URL, injeção em buscas, Socket.IO e segredos;
`tests/test_business_rules.py` cobre aceite e estoque, travas da calculadora, qualificação,
agenda da Erica e avisos sem emoji.

## Demonstração local sem Docker

```bash
.venv/Scripts/python manage.py rundemo --settings=nucleus.settings_demo
# outro terminal
cd ../FrontEnd && echo VITE_API_URL=http://127.0.0.1:8000 > .env.local && npm run dev
```

Mongo em memória, Redis falso, Z-API e IA desligadas (envios só no log). Login `erica / demo1234`
(admin) ou `sdr / demo1234`. Os dados somem ao parar o servidor.

## Implantação do processo com SDR (ordem)

1. Variáveis novas no `.env` (ver `.env.example`): `ZAPI_WEBHOOK_TOKEN`, `FRONTEND_URL`,
   `GOOGLE_OAUTH_CLIENT_FILE` (caminho **fora** do repositório), `GOOGLE_OAUTH_REDIRECT_URI`
   ou `GOOGLE_REFRESH_TOKEN`. `JWT_SECRET_KEY` (ou `DJANGO_SECRET_KEY`, usada quando a primeira
   está vazia) com **32 bytes ou mais**, senão o PyJWT avisa a cada token. Gere com
   `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Trocar a chave desloga todo mundo
   (os tokens antigos deixam de valer); quem estiver logado só precisa entrar de novo.
2. `pip install -r requirements.txt` (entrou a biblioteca do Google Agenda e as dependências
   subiram de versão na revisão de 19/10).
3. `python manage.py migrate`: campo `role` do usuário e as tabelas do `token_blacklist`
   (logout revoga o refresh token e cada renovação invalida o anterior). Sem essa migração o
   login e a renovação da sessão dão erro 500.
4. `python manage.py migrate_lm_stages --dry-run` e depois sem `--dry-run`.
5. `python manage.py seed_inventory` (contagem de 22/01/2025, aproximada).
6. Na Z-API, trocar a URL do webhook para `.../api/v1/gateway/webhook/zapi/?token=<ZAPI_WEBHOOK_TOKEN>`.
   **Sem isso o webhook passa a responder 401.**
7. Subir o Celery **beat** (além do worker). Tarefas: lead parado (de hora em hora),
   cadência da SDR (30 min: follow-up D+1/D+3/D+5 da proposta, Perdido "sem resposta" em
   D+7 com reativação em 30 dias, reunião amanhã), propostas vencidas, sincronização do
   Google (10 min) e lembretes da agenda (15 min). Dias e prazos em `lm_settings`
   (`follow_up_days`, `auto_lost_days`, `reactivation_days`).
8. Em Configurações (ou `PATCH /api/v1/crm/settings/`): telefone ou grupo de aprovação,
   telefones da Erica, da SDR e da Lúcia; papéis dos usuários (`role`: admin, sdr, porta, b2bflow).
9. Google Agenda (decisão de 16/10: token pelo serviço OAuth da b2bflow):
   - Gere o refresh token em `https://oauth.b2bflow.com.br` autorizando com a conta **Contato LM**
     e o escopo `https://www.googleapis.com/auth/calendar` (ou `calendar.events`). O token só vale
     com o mesmo client OAuth ("LM B2B Flow") que o emitiu.
   - No servidor: `GOOGLE_OAUTH_CLIENT_FILE` apontando para o client secret desse mesmo client
     (fora do repositório) e `GOOGLE_REFRESH_TOKEN=<token>`. `GOOGLE_CALENDAR_ID=primary`.
   - Confira: `python manage.py check_google_calendar --create-test` (mostra a agenda conectada,
     os próximos eventos e cria/apaga um evento de teste com Meet; nunca imprime o token).
   - A página Agenda passa a mostrar "Sincronizar"; o beat lê o Google a cada 10 minutos.
10. Segurança (revisão de 19/10):
   - **Socket.IO exige login**: o front manda o JWT no handshake (`auth.token`) e o servidor só
     aceita as origens de `CORS_ALLOWED_ORIGINS`. Front e backend desta versão sobem juntos; front
     antigo deixa de receber mensagens em tempo real (a lista ainda atualiza a cada 30 s).
   - `/admin/` do Django fica desligado (`DJANGO_ADMIN_ENABLED=True` liga). Usuários e papéis pela
     API: `POST /users/usuarios/` e `PATCH /users/usuarios/<id>/` com `role` (só admin).
   - Atrás de proxy HTTPS: `SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO`; depois de confirmar
     o HTTPS, `SECURE_HSTS_SECONDS=31536000`. Limite por usuário: `API_USER_THROTTLE` (300/min).
   - `docker-compose.yml` é de desenvolvimento (portas presas a 127.0.0.1, senhas padrão): não use
     em produção como está.
   - Senhas novas seguem os validadores do Django (mínimo 8, não só números, não comuns). Senhas
     já cadastradas continuam entrando normalmente; a regra vale só ao criar usuário ou trocar senha.
11. Frontend (sobe junto com o backend, por causa do Socket.IO com JWT e da renovação de sessão):
   - `VITE_API_URL` com a URL pública do backend (sem `/api/v1`) no `.env` do build. Ela entra no
     bundle na hora do build: trocar depois exige buildar de novo.
   - `npm ci` (o `package-lock.json` é o lockfile válido; `pnpm-lock.yaml` e `bun.lock` estão
     desatualizados) e `npm run build`. Publicar o conteúdo de `FrontEnd/dist/` no lugar do anterior.
   - A URL onde o painel abre precisa estar em `CORS_ALLOWED_ORIGINS` do backend (HTTP e Socket.IO)
     e em `FRONTEND_URL` (links dos avisos por WhatsApp).
   - Depois de publicar, peça para todos recarregarem a página (Ctrl+F5): uma aba aberta com o front
     antigo não renova a sessão e não recebe mensagens em tempo real.

## Roteiro de teste manual (P0)

Webhook (troque o token e o telefone):

```bash
curl -X POST "http://localhost:8000/api/v1/gateway/webhook/zapi/?token=SEU_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"phone":"5562999990000","isGroup":false,"status":"RECEIVED","senderName":"Ana","text":{"message":"Olá"}}'
```

- Sem `?token=` ou com token errado: 401. O mesmo texto de novo em menos de 2 minutos: `duplicate`.
- Aba WhatsApp: aparecem "Olá" e o menu de boas-vindas com os botões.
- Clique de botão: `{"phone":"5562999990000","isGroup":false,"status":"RECEIVED","buttonsResponseMessage":{"buttonId":"1","message":"Solicitar orçamento"}}`
  aparece na conversa como "Solicitar orçamento", seguido do submenu.
- Imagem: `{"phone":"5562999990000","isGroup":false,"status":"RECEIVED","image":{"imageUrl":"https://.../foto.jpg","caption":"meu palco"}}`
  aparece como imagem com legenda.

Funil e qualificação (com o id do cliente criado acima, JWT de um usuário):

1. `POST /api/v1/crm/customers/<id>/qualification/start/ {"product":"estrutura_porta"}`
2. `POST .../qualification/field/ {"field":"data_retirada","value":"24/10/2026"}` (e `data_devolucao`)
3. `POST .../qualification/attachment/ {"url":"https://.../foto.jpg","kind":"lista_pecas"}`
4. `POST .../qualification/qualify/ {"pending_fields":["lista_pecas"]}`
5. Página Funil: card em "Lead qualificado" com anexo, pendência e tarefa "Ligar para o lead".
6. "Calculadora" no card: torre Q30 5 m = R$ 75; 10 dias de locação pede aprovação.
7. Salvar, "Marcar enviada" (vai para "Proposta enviada"), "Aceita" (reserva o estoque;
   a página Estoque mostra o reservado no período).
8. "Agendar" no card: reunião online aparece na Agenda (e no Google, se conectado) com link do Meet.
