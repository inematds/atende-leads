# atende-leads

[![Atende Leads](guia/assets/banner.jpg)](https://inematds.github.io/atende-leads/guia/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## O que é

Um sistema de código aberto que atende os leads que chegam pelo WhatsApp (e pelo chat do site): um agente responde, qualifica e, quando é hora de um humano, passa o lead ao colaborador livre há mais tempo pelo Telegram, com todos os dados e um botão para ligar. Roda numa VPS com Docker, sem custo de API, e os dados ficam no seu servidor.

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/atende-leads/guia/**

🎬 Vídeo explicativo (2 min 37 s): **https://inematds.github.io/atende-leads/videos/** · [YouTube](https://www.youtube.com/watch?v=-6VKlGAYwKY)

Atendimento de **leads pelo WhatsApp** com um agente que responde, qualifica e passa o lead para o **colaborador livre** pelo Telegram, com todos os dados e um botão para ligar. Python 3 só com biblioteca padrão, estado em SQLite, Docker para VPS. Código aberto, versão `1.5.5`.

## O que faz

- **Agente no WhatsApp** (Evolution API): responde o FAQ, mostra preço só do que está cadastrado, qualifica (nome → o que procura → para quando) e dá a nota do lead (quente / morno / frio).
- **Chama um humano em 3 casos:** o lead pede, o agente percebe que precisa (reclamação, problema, ou não sabe responder: "Essa eu não sei com certeza. Quer que eu chame alguém da equipe?") ou vê **chance de venda** (preço, "quero comprar", pagamento).
- **Oferece ao colaborador livre há mais tempo**, no privado do Telegram: nome, telefone, nota, interesse, resumo e últimas mensagens, com os botões **Assumir · Passar · Ligar (telefone) · WhatsApp (conversa ou chamada)**.
- **Sem resposta em 2 min** → passa ao próximo. Lead quente sem dono em 2 min (normal em 5) ou ninguém livre → **alerta 🚨 no grupo**, e o primeiro que tocar em Assumir leva.
- **Painel fixo no grupo** (`EQUIPE AGORA`): quem está livre, atendendo, ocupado ou fora, e a fila de leads esperando. Editado a cada mudança.
- **Fechamento** pelos botões: Vendeu (valor) · Retornar (data) · Negociando · Sem interesse (motivo) · Inválido, com nota em texto ou áudio (transcrição local opcional). O colaborador volta ao fim da fila de livres.
- **Retornos agendados**, lembrete de atendimento parado (30 min), aviso de fim do expediente, fora do horário com o próximo início.
- **Três interfaces web:** lead (chat, bolha para o site e página "meu atendimento"), equipe (`/equipe`) e gestor (`/gestor`: ao vivo, hoje, leads, cadastros, CSV).
- **LGPD:** `PARAR`, `apagar meus dados`, e o grupo nunca recebe telefone nem texto do lead.
- **Base de conhecimento** (`/gestor` → Base de conhecimento): informações do negócio (horário de atendimento humano, endereço, pagamento, entrega, garantia, site, observações) e FAQ num formulário, com a caixa **Testar** ("o que o agente responderia?"). "Que hora tem atendimento humano?" responde o horário e se agora está aberto; campo vazio nunca vira resposta inventada.
- **Sugestão de resposta para a equipe:** quando o lead escreve num atendimento, o dono recebe `💡 Sugestão` no Telegram com **✅ Enviar / ✏️ Editar** (e no painel, já na caixa de resposta). Cada resposta vira um registro de **aprendizado** (usou sem editar, editou ou ignorou), e a aba **Aprendizado** gera **propostas para a base** (diária, semanal ou na hora) para o gestor incorporar ou descartar.
- **Cérebro:** regras por padrão (sem custo, sem API). Opcional: **Anthropic (Claude)**, **OpenRouter**, Ollama local, endpoint compatível com OpenAI ou o CLI da sua assinatura (`claude`/`codex`, só para teste local), com volta automática às regras se falhar.

Contrato completo: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md).

## O processo, do início ao fim

Quem faz: 🧠 o dono/gestor · ⚙️ o sistema · 🤖 o agente.

1. 🧠 **Instalar na VPS:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads && ./instalar-vps.sh` (pergunta nome, domínio, Telegram; gera segredos, `.env` e `dados/negocio.json`; sobe o Docker).
2. 🧠 **Conectar o WhatsApp:** túnel `ssh -L 8081:127.0.0.1:8081 usuario@vps`, abrir `http://localhost:8081/manager`, criar a instância e ler o QR Code com o número do atendimento (use um número só para isso).
3. 🧠 **Cadastrar** em `/gestor` → Cadastros: equipe (nome, telefone, código), produtos com palavras e preço, horários e prazos; → **Base de conhecimento**: informações do negócio, FAQ e o cérebro (e **Testar** perguntas como o cliente).
4. 🧠 **Equipe entra no bot:** cada colaborador manda `/entrar <código>` no privado do bot e toca 🟢 Livre.
5. ⚙️ **Lead chega** pelo WhatsApp ou pela bolha do site.
6. 🤖 **Agente atende:** FAQ, preço cadastrado, qualificação e nota.
7. ⚙️ **Gatilho** (pediu humano / precisa / chance de venda) → abre o chamado e manda a linha curta ao grupo.
8. ⚙️ **Oferta** ao livre há mais tempo, no privado, com dados e botões; 2 min sem resposta → próximo.
9. ⚙️ **Alerta 🚨** no grupo quando estoura o prazo ou não há ninguém livre.
10. 🧠 **Colaborador assume**, liga (📞) ou responde pelo WhatsApp (💬) ou em resposta no próprio bot; ⚙️ a cada mensagem do lead chega a `💡 Sugestão` (✅ Enviar / ✏️ Editar) e cada resposta entra no aprendizado.
11. 🧠 **Fecha** com o resultado; ⚙️ grava o histórico, agenda o retorno e devolve o colaborador à fila.
12. 🧠 **Gestor acompanha** em `/gestor` (ao vivo, hoje, leads, exportar CSV) e, na aba **Aprendizado**, incorpora ou descarta as propostas para a base (⚙️ geradas toda semana, por padrão).
13. ⚙️ **Backup diário** pelo cron único que o `instalar-vps.sh` instala (`docker compose exec -T atende ./atende backup ...` → `/opt/atende-leads-backups/`).

> Dá para fazer os passos 2 a 12 **na sua máquina**, sem domínio nem HTTPS, antes de ir para a VPS: veja [Testar na sua máquina (sem domínio)](#testar-na-sua-máquina-sem-domínio) (Telegram em `TELEGRAM_MODO=polling`).

## Rodar local

```bash
./atende serve --porta 8080 --dados dados
# chat do lead: http://localhost:8080/   equipe: /equipe   gestor: /gestor (token em dados/negocio.json)
python3 -m pytest -q tests/        # contrato (320 testes; build e container Docker só com TESTAR_DOCKER=1)
```

Relógio fixo para testar: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` e `POST /api/tarefas/rodar`.

## Testar na sua máquina (sem domínio)

Para ver o sistema inteiro funcionando (WhatsApp de verdade + bot do Telegram) num computador com Docker, sem domínio público nem HTTPS. O Telegram fica no **modo polling**: o servidor busca as mensagens do bot sozinho (`getUpdates`), então não precisa de `setWebhook` nem de `TELEGRAM_SEGREDO`.

```bash
git clone https://github.com/inematds/atende-leads && cd atende-leads
# gera .env e dados/negocio.json com segredos novos; responda: domínio localhost:8080, modo do Telegram polling
INSTALAR_SO_GERAR=1 ./instalar-vps.sh
sudo chown -R 1000:1000 dados
docker compose --profile evolution up -d --build
```

Sem perguntas: `NEGOCIO_NOME="Minha Loja" DOMINIO=localhost:8080 TELEGRAM_TOKEN=<token do BotFather> TELEGRAM_GRUPO_ID=<id do grupo> TELEGRAM_MODO=polling COM_EVOLUTION=1 INSTALAR_SO_GERAR=1 ./instalar-vps.sh --sem-perguntas`. Num `.env` já existente, basta acrescentar `TELEGRAM_MODO=polling` e rodar `docker compose up -d`.

1. **WhatsApp:** abra o manager da Evolution em <http://localhost:8081/manager> (API Key global = `EVOLUTION_API_KEY` do `.env`), crie a instância com o nome do `.env` (`EVOLUTION_INSTANCIA`) e leia o QR Code com o celular do número de teste.
2. **Telegram:** ponha o bot no grupo da equipe; cada colaborador manda `/entrar <código>` no privado do bot (os códigos foram impressos pelo instalador e estão em `dados/negocio.json`). `GET http://localhost:8080/api/saude` mostra `"telegram_modo": "polling"`.
3. **Painéis:** chat do lead em <http://localhost:8080/>, equipe em <http://localhost:8080/equipe>, gestor em <http://localhost:8080/gestor> (token em `dados/negocio.json`).

O bot só fala com **um** servidor: ao subir em polling, ele desliga o webhook do bot. Ao passar para a VPS, volte a `TELEGRAM_MODO=webhook` e rode o `setWebhook` (passo 3 do instalador).

## Deploy na VPS

> **Nunca instalou um servidor?** Siga o passo a passo para leigos: **[docs/INSTALAR-VPS.md](docs/INSTALAR-VPS.md)** (9 passos, ~40 min, do zero até o WhatsApp conectado).

Todos os comandos abaixo usam o caminho **`/opt/atende-leads`** (o cron de backup também). Se instalar em outro lugar, troque o caminho em todos eles.

0. **Baixar:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads`
1. **Subir:** `cd /opt/atende-leads && ./instalar-vps.sh`. Ele gera `.env` e `dados/negocio.json` com permissão só do dono (`umask 077`), o token do gestor e os **códigos da equipe** (aleatórios, `secrets.token_urlsafe`), dá a pasta `dados/` ao uid 1000 (o container **não roda como root**; sem ser root, tenta `sudo -n chown -R 1000:1000 dados`, e se não conseguir **para antes de subir** e mostra o comando), sobe o compose e imprime tudo no fim. A aplicação escuta só em `127.0.0.1:8080` e a Evolution em `127.0.0.1:8081`.
   - **Rodar de novo** (mudar domínio, ligar o Telegram) **não troca os segredos**: `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY` e `EVOLUTION_DB_SENHA` que já estão no `.env` são reaproveitados (a saída diz quais); só os que faltam (ou ainda têm `troque`) são gerados. Trocar a senha do Postgres com o volume já criado derrubaria a Evolution, e um `TELEGRAM_SEGREDO` novo faria o webhook do Telegram dar 401. O token do gestor e os códigos da equipe também são mantidos.
   - **Sem o instalador** (`docker compose up -d`, ou `docker compose --profile evolution up -d` com a Evolution no mesmo servidor): `cd /opt/atende-leads && cp .env.exemplo .env && mkdir -p dados && cp exemplos/negocio.json dados/` e **troque** o `token_gestor` e os códigos da equipe em `dados/negocio.json` (códigos com 12+ caracteres) e `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY` e `EVOLUTION_DB_SENHA` no `.env`; com o perfil `evolution`, ponha também `EVOLUTION_URL=http://evolution-api:8080` (a URL interna; vazio = WhatsApp desligado); depois `sudo chown -R 1000:1000 /opt/atende-leads/dados`. Com algum segredo de exemplo o container recusa subir (item 2).
   - **Evolution externa** (já roda em outro servidor; não use o perfil `evolution`): no `.env`, `EVOLUTION_URL=https://<sua-evolution>`, `EVOLUTION_API_KEY=<API key dela>`, `EVOLUTION_INSTANCIA=<instância>`; e, no manager dela, o webhook `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (item 5). Suba só `docker compose up -d`.
   - **Atualizar uma instalação anterior:** `cd /opt/atende-leads && git pull && sudo chown -R 1000:1000 dados && docker compose up -d --build` (de antes da 1.0.2, o `chown` é obrigatório; com o cérebro `openai` e chave, acrescente `CEREBRO_HOSTS_PERMITIDOS` no `.env`).
2. **Segredos de exemplo não sobem na rede:** se o `negocio.json` ainda tem `token_gestor` = `TROQUE-ESTE-TOKEN` ou algum código igual ao do `exemplos/negocio.json`, ou se uma integração está ligada com `WEBHOOK_SEGREDO`/`TELEGRAM_SEGREDO` vazio, com menos de 16 caracteres ou contendo `troque` (ou a Evolution ligada com `EVOLUTION_API_KEY` contendo `troque`), o servidor só aceita subir em `127.0.0.1`/`localhost`. Em `0.0.0.0` (como no Docker) ele **recusa** com a mensagem "rode ./instalar-vps.sh ou troque os segredos". O `.env.exemplo` vem com `EVOLUTION_URL=` e `TELEGRAM_TOKEN=` vazios: as integrações ficam desligadas até você preencher. Para teste/demonstração apenas: `ATENDE_PERMITIR_EXEMPLO=1` no ambiente (nunca em produção).
3. **HTTPS:** proxy reverso (Caddy ou Nginx) do seu domínio para `127.0.0.1:8080`. Ex. Caddy: `leads.seudominio.com { reverse_proxy 127.0.0.1:8080 }`. Ajuste `url_publica` no `negocio.json`. Limites por IP (5 senhas erradas por minuto → as erradas recebem 429, a certa sempre passa; 5 conversas novas do chat web em 10 min; 3 pedidos de atendimento pelo web por hora) usam o IP do `X-Forwarded-For` quando a conexão vem de um proxy confiável: `ATENDE_PROXY_CONFIAVEL` (CIDRs; padrão `127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16`, que cobre o Caddy no host chegando pela bridge do Docker). Vazio = nunca confiar no `X-Forwarded-For`. O chat web é público: além desses limites, o total de conversas novas também tem teto, e quem assume um lead é só o colaborador a quem ele foi ofertado ou, em alerta 🚨, quem tocar primeiro em Assumir.
4. **WhatsApp (QR Code):** a porta da Evolution só escuta em `127.0.0.1`, então abra um túnel do seu computador:
   ```bash
   ssh -L 8081:127.0.0.1:8081 usuario@vps
   ```
   e, com o túnel aberto, acesse `http://localhost:8081/manager`. Entre com a API Key global (`EVOLUTION_API_KEY` do `.env`), clique em **Instance +**, dê o nome de `EVOLUTION_INSTANCIA` (padrão `loja`), canal **Baileys**, salve, abra a instância e leia o **QR Code** pelo WhatsApp do celular (Aparelhos conectados → Conectar aparelho). Sem o manager, pela API na VPS: `curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY>" -H 'Content-Type: application/json' -d '{"instanceName":"loja","integration":"WHATSAPP-BAILEYS","qrcode":true}'`.
5. **Webhook da Evolution:** evento `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (com o perfil `evolution` o compose já aponta pela rede interna). Mensagens com `remoteJid` `@lid` usam o telefone de `remoteJidAlt`/`senderPn`; sem ele, aparecem em **descartes** no `/gestor`.
6. **Webhook do Telegram:** crie o bot no @BotFather, ponha no grupo da equipe como admin (para fixar o painel) e registre:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
7. **Backup diário — um único cron** (o `instalar-vps.sh` instala no crontab do root). Roda dentro do container e copia para **fora** do volume de dados, numa pasta `700` com arquivos `600` (o backup tem dados pessoais):
   ```cron
   0 3 * * * cd /opt/atende-leads && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && install -d -m 700 /opt/atende-leads-backups && f=/opt/atende-leads-backups/leads-$(date +\%F).tar.gz && mv /opt/atende-leads/dados/.backup-cron.tar.gz $f && chmod 600 $f && find /opt/atende-leads-backups -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup
   ```
8. **Restaurar:** pare o serviço antes (o `restaurar` recusa com o servidor no ar):
   ```bash
   cd /opt/atende-leads
   docker compose stop atende
   docker compose run --rm -v /opt/atende-leads-backups:/backups atende \
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz
   docker compose start atende
   ```

Variáveis em [`.env.exemplo`](.env.exemplo) (inclui `ATENDE_PROXY_CONFIAVEL`, `ATENDE_MAX_CONEXOES` — conexões simultâneas, padrão 64, acima disso 503, mas o `/api/saude` responde mesmo lotado —, `CEREBRO_HOSTS_PERMITIDOS` e `ATENDE_PERMITIR_EXEMPLO`, só para demonstração). Sem as de uma integração, ela fica desligada e o resto funciona (painéis web). Envios ao Telegram e ao WhatsApp saem por uma caixa de saída em segundo plano: se uma API travar, o atendimento e o `/api/saude` continuam respondendo.

## Cérebro com IA (opcional)

Sem nada configurado, tudo funciona por **regras** (custo zero). Para o agente responder dúvidas fora do FAQ, resumir o chamado, sugerir respostas à equipe e propor itens para a base, ligue um cérebro em `/gestor` → **Base de conhecimento** → Cérebro (ou no `negocio.json`). A chave fica **só** no `.env` (`CEREBRO_API_KEY`), nunca no JSON nem na tela. Se a chave faltar, o modelo recusar, der erro ou demorar (20 s), a resposta volta para as regras; a saúde (`/api/saude`) mostra `cerebro_ok` e o motivo.

**Anthropic (Claude), o recomendado:**

```json
"cerebro": { "tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low" }
```

```bash
# .env
CEREBRO_API_KEY=sk-ant-...   # chave da API da Anthropic
```

Depois `docker compose up -d` (ou reinicie o `./atende serve`). `esforco` = `low` (padrão, mais barato), `medium`, `high`, `xhigh` ou `max`. As respostas são curtas (até 1024 tokens) e a base vai com cache de prompt, então o custo por resposta curta é baixo (ainda menor em `low`). Instrução fixa: português do Brasil, curto e cordial, só a base, nunca inventa preço/prazo/condição; se não souber, diz que vai chamar alguém.

**Outros tipos:**

| tipo | o que precisa | observação |
|---|---|---|
| `openrouter` | `modelo` (ex.: `anthropic/claude-sonnet-5.5`, `z-ai/glm-5`) + `CEREBRO_API_KEY` do OpenRouter | URL fixa `openrouter.ai` |
| `openai` | `url` + `modelo` (+ chave e `CEREBRO_HOSTS_PERMITIDOS`) | qualquer endpoint `/v1/chat/completions` |
| `ollama` | `url` + `modelo` | local, sem chave |
| `claude_cli` | CLI `claude` logado (`modelo`, padrão `sonnet`) | assinatura pessoal |
| `codex_cli` | CLI `codex` logado + `modelo` | assinatura pessoal |

> ⚠️ **`claude_cli` / `codex_cli` usam a sua assinatura pessoal pelo CLI** (`claude -p` / `codex exec`, prompt pelo stdin, 60 s). Servem só para **o dono testar** rodando `./atende serve` direto na máquina com o CLI logado (`CEREBRO_CLI_BIN` se o binário não estiver no PATH). **Dentro do Docker o binário não existe** — a saúde mostra `cerebro_ok: false` e tudo cai nas regras. Para cliente em produção use API (`anthropic`, `openrouter`, `openai`) ou Ollama.

## Cuidados

- A Evolution não é a API oficial do WhatsApp: use um número dedicado e não faça disparo em massa para quem não falou com você.
- Os dados de leads ficam no seu servidor (`dados/`). O backup contém dados pessoais: guarde com acesso restrito.
- A Evolution do compose **não guarda** cópia das mensagens, contatos e conversas (`DATABASE_SAVE_*` = `false`, por LGPD): o que o atendimento precisa fica em `dados/leads.db`, que o "apagar meus dados" limpa.
- **Quem tem o token do gestor pode mudar `cerebro.url`** no `/gestor`. Por isso a `CEREBRO_API_KEY` só é enviada a um host listado em `CEREBRO_HOSTS_PERMITIDOS` no `.env` (ex.: `CEREBRO_HOSTS_PERMITIDOS=api.seuprovedor.com`); vazio = a chave não vai a ninguém. Um token do gestor novo pelo `/gestor` precisa de 16+ caracteres e não pode ser o do exemplo.

## Roteiro (fora da v1)

Agente de voz automático · responder o WhatsApp pelo painel · funil arrastável · CRM externo por webhook · metas e ranking · vários números · API oficial da Meta · pesquisa de satisfação.

## Licença

MIT. Conteúdo aberto e gratuito do [INEMA.CLUB](https://inema.club).
