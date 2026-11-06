# atende-leads

[![Atende Leads](guia/assets/banner-en.jpg)](https://inematds.github.io/atende-leads/guia/en/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## What it is

An open-source system that handles leads coming in through WhatsApp (and your website chat): an agent replies, qualifies them, and when it’s time for a human, forwards the lead to the team member who has been available the longest via Telegram, with all the details and a button to call. Runs on a VPS with Docker, with no API costs, and your data stays on your server.

## 📖 User guide

Complete guide (landing page + walkthrough): **https://inematds.github.io/atende-leads/guia/en/**

🎬 Explainer video (2 min 37 s, in Portuguese): **https://inematds.github.io/atende-leads/videos/** · [YouTube](https://www.youtube.com/watch?v=-6VKlGAYwKY)

**WhatsApp lead** handling with an agent that replies, qualifies leads, and forwards them to the **available team member** via Telegram, with all the details and a button to call. Python 3 using only the standard library, SQLite for state, Docker for VPS deployment. Open source, version `1.4.4`.

## What it does

- **WhatsApp agent** (Evolution API): answers FAQs, shows prices only for listed items, qualifies leads (name → what they’re looking for → when they need it) and scores them (hot / warm / cold).
- **Calls in a human in 3 cases:** the lead asks, the agent recognizes one is needed (complaint, problem, “I don’t understand” twice), or sees a **sales opportunity** (price, “I want to buy,” payment).
- **Offers the lead to the team member who has been available the longest**, in a private Telegram chat: name, phone, score, interest, summary, and latest messages, with the buttons **✅ Accept · ↪️ Pass · 📞 Call · 💬 WhatsApp**.
- **No response in 2 minutes** → passes it to the next person. A hot lead with no owner in 2 minutes (5 normally), or no one available → **🚨 alert in the group**, and the first person to tap Accept gets it.
- **Pinned group panel** (`TEAM NOW`): who is available, handling a lead, busy, or away, plus the queue of waiting leads. Updated whenever anything changes.
- **Close out** using the buttons: Sold (amount) · Follow up (date) · Negotiating · Not interested (reason) · Invalid, with a note in text or audio (optional local transcription). The team member returns to the end of the available queue.
- **Scheduled follow-ups**, reminder for a stalled conversation (30 min), end-of-shift notice, and an out-of-hours message with the next start time.
- **Three web interfaces:** lead (chat, website bubble, and “my conversation” page), team (`/equipe`), and manager (`/gestor`: live, today, leads, records, CSV).
- **LGPD:** `PARAR`, `apagar meus dados`, and the group never receives the lead’s phone number or message text.
- **Knowledge base** (`/gestor` → Knowledge base): business information (human support hours, address, payment, delivery, warranty, website, notes) and FAQ in a form, with the **Test** box ("what would the agent reply?"). "What time is human support available?" replies with the hours and whether it is open now; an empty field never produces an invented answer.
- **Suggested reply for the team:** when a lead writes during a conversation, the owner receives `💡 Sugestão` on Telegram with **✅ Enviar / ✏️ Editar** (and in the panel, already in the reply box). Each reply becomes a record of **learning** (used without editing, edited, or ignored), and the **Learning** tab generates **proposals for the knowledge base** (daily, weekly, or on demand) for the manager to incorporate or discard.
- **Brain:** default rules (no cost, no API). Optional: **Anthropic (Claude)**, **OpenRouter**, local Ollama, an OpenAI-compatible endpoint, or your subscription CLI (`claude`/`codex`, for local testing only), with automatic fallback to rules if it fails.

Complete contract: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md).

## The process, from start to finish

Who does what: 🧠 owner/manager · ⚙️ system · 🤖 agent.

1. 🧠 **Install on the VPS:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads && ./instalar-vps.sh` (asks for name, domain, and Telegram; generates secrets, `.env`, and `dados/negocio.json`; starts Docker).
2. 🧠 **Connect WhatsApp:** tunnel `ssh -L 8081:127.0.0.1:8081 usuario@vps`, open `http://localhost:8081/manager`, create the instance, and scan the QR Code with the support number (use a number dedicated to this).
3. 🧠 **Set up** in `/gestor` → Registrations: team (name, phone, code), products with keywords and price, hours and lead times; → **Knowledge base**: business information, FAQ, and the brain (and **Test** questions as a customer would).
4. 🧠 **Team joins the bot:** each team member sends `/entrar <código>` in a private chat with the bot and taps 🟢 Available.
5. ⚙️ **A lead arrives** via WhatsApp or the website bubble.
6. 🤖 **Agent handles it:** FAQ, listed prices, qualification, and score.
7. ⚙️ **Trigger** (asks for a human / needs one / sales opportunity) → opens a ticket and sends a short line to the group.
8. ⚙️ **Offer** goes to the person who has been available the longest, in a private chat, with details and buttons; after 2 minutes without a response → next person.
9. ⚙️ **🚨 Alert** in the group when the deadline expires or no one is available.
10. 🧠 **Team member takes over**, calls (📞) or replies via WhatsApp (💬) or in a reply in the bot itself; ⚙️ each time a lead sends a message, a `💡 Sugestão` arrives (✅ Enviar / ✏️ Editar), and each reply is added to learning.
11. 🧠 **Closes** with the outcome; ⚙️ records the history, schedules a follow-up, and returns the team member to the queue.
12. 🧠 **Manager monitors** in `/gestor` (live, today, leads, export CSV) and, in the **Learning** tab, incorporates or discards proposals for the knowledge base (⚙️ generated every week by default).
13. ⚙️ **Daily backup** via the single cron job installed by `instalar-vps.sh` (`docker compose exec -T atende ./atende backup ...` → `/opt/atende-leads-backups/`).

> You can complete steps 2 to 12 **on your machine**, without a domain or HTTPS, before moving to the VPS: see [Test on your machine (no domain)](#test-on-your-machine-no-domain) (Telegram with `TELEGRAM_MODO=polling`).

## Run locally

```bash
./atende serve --porta 8080 --dados dados
# lead chat: http://localhost:8080/   team: /equipe   manager: /gestor (token in dados/negocio.json)
python3 -m pytest -q tests/        # contract (320 tests; build and Docker container only with TESTAR_DOCKER=1)
```

Fixed clock for testing: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` and `POST /api/tarefas/rodar`.

## Test on your machine (no domain)

To see the entire system working (real WhatsApp + Telegram bot) on a computer with Docker, without a public domain or HTTPS. Telegram runs in **polling mode**: the server fetches the bot’s messages itself (`getUpdates`), so there’s no need for `setWebhook` or `TELEGRAM_SEGREDO`.

```bash
git clone https://github.com/inematds/atende-leads && cd atende-leads
# gera .env e dados/negocio.json com segredos novos; responda: domínio localhost:8080, modo do Telegram polling
INSTALAR_SO_GERAR=1 ./instalar-vps.sh
sudo chown -R 1000:1000 dados
docker compose --profile evolution up -d --build
```

Without prompts: `NEGOCIO_NOME="Minha Loja" DOMINIO=localhost:8080 TELEGRAM_TOKEN=<token do BotFather> TELEGRAM_GRUPO_ID=<id do grupo> TELEGRAM_MODO=polling COM_EVOLUTION=1 INSTALAR_SO_GERAR=1 ./instalar-vps.sh --sem-perguntas`. In an existing `.env`, just add `TELEGRAM_MODO=polling` and run `docker compose up -d`.

1. **WhatsApp:** open the Evolution manager at <http://localhost:8081/manager> (global API Key = `EVOLUTION_API_KEY` from `.env`), create an instance with the name from `.env` (`EVOLUTION_INSTANCIA`), and scan the QR Code with the phone for the test number.
2. **Telegram:** add the bot to the team group; each team member sends `/entrar <código>` in a private chat with the bot (the codes were printed by the installer and are in `dados/negocio.json`). `GET http://localhost:8080/api/saude` shows `"telegram_modo": "polling"`.
3. **Dashboards:** lead chat at <http://localhost:8080/>, team at <http://localhost:8080/equipe>, manager at <http://localhost:8080/gestor> (token in `dados/negocio.json`).

The bot only talks to **one** server: when polling starts, it disables the bot’s webhook. When moving to the VPS, switch back to `TELEGRAM_MODO=webhook` and run `setWebhook` (step 3 of the installer).

## Deploy to a VPS

All commands below use the path **`/opt/atende-leads`** (the backup cron job does too). If you install elsewhere, change the path in all of them.

0. **Download:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads`
1. **Start:** `cd /opt/atende-leads && ./instalar-vps.sh`. It creates `.env` and `dados/negocio.json` with owner-only permissions (`umask 077`), the manager token, and **team codes** (random, `secrets.token_urlsafe`), assigns the `dados/` folder to uid 1000 (the container **does not run as root**; if you aren’t root, it tries `sudo -n chown -R 1000:1000 dados`, and if that fails, **stops before starting** and shows the command), starts compose, and prints everything at the end.
   - **Running it again** (to change the domain or connect Telegram) **does not replace the secrets**: existing `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY`, and `EVOLUTION_DB_SENHA` values in `.env` are reused (the output lists which ones); only missing values (or ones that still contain `troque`) are generated. Changing the Postgres password after the volume has been created would break Evolution, and a new `TELEGRAM_SEGREDO` would make the Telegram webhook return 401. The manager token and team codes are also preserved.
   - **Without the installer** (`docker compose up -d`, or `docker compose --profile evolution up -d` with Evolution on the same server): `cd /opt/atende-leads && cp .env.exemplo .env && mkdir -p dados && cp exemplos/negocio.json dados/` and **change** `token_gestor` and the team codes in `dados/negocio.json` (codes must be 12+ characters), as well as `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY`, and `EVOLUTION_DB_SENHA` in `.env`; with the `evolution` profile, also set `EVOLUTION_URL=http://evolution-api:8080` (the internal URL; empty = WhatsApp disabled); then run `sudo chown -R 1000:1000 /opt/atende-leads/dados`. With any example secret, the container refuses to start (item 2).
   - **External Evolution** (already running on another server; do not use the `evolution` profile): in `.env`, set `EVOLUTION_URL=https://<sua-evolution>`, `EVOLUTION_API_KEY=<API key dela>`, `EVOLUTION_INSTANCIA=<instância>`; and, in its manager, set the `MESSAGES_UPSERT` webhook to `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (item 5). Start only with `docker compose up -d`.
   - **Update an earlier installation:** `cd /opt/atende-leads && git pull && sudo chown -R 1000:1000 dados && docker compose up -d --build` (for versions before 1.0.2, `chown` is required; with the `openai` brain and a key, add `CEREBRO_HOSTS_PERMITIDOS` to `.env`).
2. **Example secrets cannot go online:** if `negocio.json` still has `token_gestor` = `TROQUE-ESTE-TOKEN` or a code matching one in `exemplos/negocio.json`, or if an integration is enabled with `WEBHOOK_SEGREDO`/`TELEGRAM_SEGREDO` empty, shorter than 16 characters, or containing `troque` (or Evolution is enabled with `EVOLUTION_API_KEY` containing `troque`), the server only allows startup on `127.0.0.1`/`localhost`. On `0.0.0.0` (as in Docker), it **refuses** with the message “run ./instalar-vps.sh or change the secrets.” `.env.exemplo` has empty `EVOLUTION_URL=` and `TELEGRAM_TOKEN=` values: integrations stay disabled until you fill them in. For testing/demos only: `ATENDE_PERMITIR_EXEMPLO=1` in the environment (never in production).
3. **HTTPS:** reverse proxy (Caddy or Nginx) from your domain to `127.0.0.1:8080`. Example with Caddy: `leads.seudominio.com { reverse_proxy 127.0.0.1:8080 }`. Set `url_publica` in `negocio.json`. Per-IP limits (5 wrong passwords per minute → wrong attempts get 429, the right password always works; 5 new web chat conversations in 10 minutes; 3 web support requests per hour) use the `X-Forwarded-For` IP when the connection comes from a trusted proxy: `ATENDE_PROXY_CONFIAVEL` (CIDRs; default `127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16`, which covers Caddy on the host connecting through the Docker bridge). Empty = never trust `X-Forwarded-For`. Web chat is public: in addition to these limits, total new conversations are capped, and a lead can only be taken by the team member it was offered to or, in a 🚨 alert, by whoever taps Accept first.
4. **WhatsApp (QR Code):** Evolution only listens on `127.0.0.1`, so open a tunnel from your computer:
   ```bash
   ssh -L 8081:127.0.0.1:8081 usuario@vps
   ```
   With the tunnel open, go to `http://localhost:8081/manager`. Sign in with the global API Key (`EVOLUTION_API_KEY` from `.env`), click **Instance +**, name it `EVOLUTION_INSTANCIA` (default `loja`), choose the **Baileys** channel, save, open the instance, and scan the **QR Code** with WhatsApp on your phone (Linked Devices → Link a Device). Without the manager, use the API on the VPS: `curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY>" -H 'Content-Type: application/json' -d '{"instanceName":"loja","integration":"WHATSAPP-BAILEYS","qrcode":true}'`.
5. **Evolution webhook:** event `MESSAGES_UPSERT` to `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (with the `evolution` profile, compose already routes it over the internal network). Messages with `remoteJid` `@lid` use the phone number from `remoteJidAlt`/`senderPn`; without it, they appear under **discarded** in `/gestor`.
6. **Telegram webhook:** create the bot with @BotFather, add it to the team group as an admin (to pin the panel), and register:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
7. **Daily backup — a single cron job** (installed in root’s crontab by `instalar-vps.sh`). It runs inside the container and copies data outside the data volume, into a `700` folder with `600` files (the backup contains personal data):
   ```cron
   0 3 * * * cd /opt/atende-leads && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && install -d -m 700 /opt/atende-leads-backups && f=/opt/atende-leads-backups/leads-$(date +\%F).tar.gz && mv /opt/atende-leads/dados/.backup-cron.tar.gz $f && chmod 600 $f && find /opt/atende-leads-backups -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup
   ```
8. **Restore:** stop the service first (`restaurar` refuses to run while the server is up):
   ```bash
   cd /opt/atende-leads
   docker compose stop atende
   docker compose run --rm -v /opt/atende-leads-backups:/backups atende \
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz
   docker compose start atende
   ```

Variables in [`.env.exemplo`](.env.exemplo) (includes `ATENDE_PROXY_CONFIAVEL`, `ATENDE_MAX_CONEXOES` — simultaneous connections, default 64, above that returns 503, but `/api/saude` still responds even when full —, `CEREBRO_HOSTS_PERMITIDOS`, and `ATENDE_PERMITIR_EXEMPLO`, for demos only). Without the variables for an integration, it stays disabled and the rest (web panels) works. Telegram and WhatsApp messages are sent through a background outbox: if an API stalls, customer service and `/api/saude` keep responding.

## AI Brain (optional)

Without any configuration, everything works using **rules** (zero cost). To have the agent answer questions outside the FAQ, summarize the conversation, suggest replies to the team, and propose items for the knowledge base, enable a brain in `/gestor` → **Knowledge base** → Brain (or in `negocio.json`). The key is stored **only** in `.env` (`CEREBRO_API_KEY`), never in the JSON or on screen. If the key is missing, the model refuses, an error occurs, or it takes too long (20 s), the response falls back to the rules; health (`/api/saude`) shows `cerebro_ok` and the reason.

**Anthropic (Claude), recommended:**

```json
"cerebro": { "tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low" }
```

```bash
# .env
CEREBRO_API_KEY=sk-ant-...   # Anthropic API key
```

Then run `docker compose up -d` (or restart `./atende serve`). `esforco` = `low` (default, cheapest), `medium`, `high`, `xhigh`, or `max`. Responses are short (up to 1024 tokens), and the knowledge base is sent with prompt caching, so the cost per short response is low (even lower with `low`). Fixed instruction: Brazilian Portuguese, concise and cordial, use only the knowledge base, never invent prices/lead times/terms; if it does not know, it says it will call someone.

**Other types:**

| type | what it needs | notes |
|---|---|---|
| `openrouter` | `modelo` (e.g. `anthropic/claude-sonnet-5.5`, `z-ai/glm-5`) + `CEREBRO_API_KEY` from OpenRouter | fixed URL `openrouter.ai` |
| `openai` | `url` + `modelo` (+ key and `CEREBRO_HOSTS_PERMITIDOS`) | any `/v1/chat/completions` endpoint |
| `ollama` | `url` + `modelo` | local, no key |
| `claude_cli` | logged-in `claude` CLI (`modelo`, default `sonnet`) | personal subscription |
| `codex_cli` | logged-in `codex` CLI + `modelo` | personal subscription |

> ⚠️ **`claude_cli` / `codex_cli` use your personal subscription through the CLI** (`claude -p` / `codex exec`, prompt via stdin, 60 s). They are only for **the owner to test** by running `./atende serve` directly on a machine with the CLI logged in (`CEREBRO_CLI_BIN` if the binary is not on PATH). **The binary does not exist inside Docker** — health shows `cerebro_ok: false` and everything falls back to the rules. For production customers, use an API (`anthropic`, `openrouter`, `openai`) or Ollama.

## Precautions

- Evolution is not the official WhatsApp API: use a dedicated number and don’t send bulk messages to people who haven’t contacted you.
- Lead data stays on your server (`dados/`). Backups contain personal data: store them with restricted access.
- The Evolution instance in compose **does not save** copies of messages, contacts, or conversations (`DATABASE_SAVE_*` = `false`, for LGPD compliance): the data customer service needs stays in `dados/leads.db`, which “delete my data” clears.
- **Anyone with the manager token can change `cerebro.url`** in `/gestor`. That’s why `CEREBRO_API_KEY` is sent only to a host listed in `CEREBRO_HOSTS_PERMITIDOS` in `.env` (e.g. `CEREBRO_HOSTS_PERMITIDOS=api.seuprovedor.com`); empty = the key is sent to no one. A new manager token set via `/gestor` must have 16+ characters and cannot be the example token.

## Roadmap (outside v1)

Automatic voice agent · reply to WhatsApp from the panel · draggable funnel · external CRM via webhook · goals and rankings · multiple numbers · official Meta API · customer satisfaction survey.

## License

MIT. Open and free content from [INEMA.CLUB](https://inema.club).
