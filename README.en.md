# atende-leads

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## 📖 User guide

Full guide (landing page + step-by-step instructions): **https://inematds.github.io/atende-leads/guia/en/**

Handle **WhatsApp leads** with an agent that replies, qualifies them, and passes them to the **available team member** via Telegram, with all their details and a button to call. Python 3 with the standard library only, SQLite for state, Docker for VPS deployment. Open source, version `1.0.1`.

## What it does

- **WhatsApp agent** (Evolution API): answers FAQs, shows prices only for registered products, qualifies leads (name → what they’re looking for → when they need it) and scores them (hot / warm / cold).
- **Calls a human in 3 cases:** the lead asks, the agent determines it’s necessary (complaint, problem, 2× “I don’t understand”), or it sees a **sales opportunity** (price, “I want to buy,” payment).
- **Offers the lead to the longest-waiting available team member** in a private Telegram chat: name, phone, score, interest, summary, and recent messages, with the **✅ Assumir (Take) · ↪️ Passar (Pass) · 📞 Ligar (Call) · 💬 WhatsApp** buttons.
- **No response in 2 minutes** → offers the lead to the next person. A hot lead with no owner after 2 minutes (5 minutes normally), or no one available → **🚨 alert in the group**, and the first person to tap Assumir (Take) gets the lead.
- **Pinned group panel** (`EQUIPE AGORA` (TEAM NOW)): who is available, handling a lead, busy, or away, and the queue of waiting leads. Updated whenever anything changes.
- **Close out leads** using the buttons: Vendeu (Sold) (amount) · Retornar (Follow up) (date) · Negociando (Negotiating) · Sem interesse (Not interested) (reason) · Inválido (Invalid), with a text or audio note (optional local transcription). The team member returns to the end of the available queue.
- **Scheduled follow-ups**, reminders for stalled conversations (30 min), end-of-shift alerts, and an out-of-hours message with the next opening time.
- **Three web interfaces:** lead (chat, website bubble, and “my support” page), team (`/equipe`), and manager (`/gestor`: live, today, leads, records, CSV).
- **LGPD:** `PARAR` (STOP), `apagar meus dados` (delete my data), and the group never receives the lead’s phone number or messages.
- **Brain:** rule-based by default (no cost, no API). Optional: local Ollama or an OpenAI-compatible endpoint configured by the business itself, with automatic fallback to rules if it fails.

Full specification: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md) (in Portuguese).

## The process, from start to finish

Who does what: 🧠 owner/manager · ⚙️ system · 🤖 agent.

1. 🧠 **Install on the VPS:** `./instalar-vps.sh` (asks for the business name, domain, and Telegram details; generates secrets, `.env`, and `dados/negocio.json`; starts Docker).
2. 🧠 **Connect WhatsApp:** create an `ssh -L 8081:127.0.0.1:8081 usuario@vps` tunnel, open `http://localhost:8081/manager`, create the instance, and scan the QR code with the support number (use a number dedicated to this).
3. 🧠 **Set things up** in `/gestor` → Cadastros: team (name, phone, code), products with keywords and prices, FAQs, hours, and deadlines.
4. 🧠 **Team members join the bot:** each team member sends `/entrar <código>` (join <code>) to the bot privately and taps 🟢 Livre (Available).
5. ⚙️ **A lead arrives** via WhatsApp or the website bubble.
6. 🤖 **The agent responds:** FAQs, registered prices, qualification, and score.
7. ⚙️ **Trigger** (asked for a human / needs one / sales opportunity) → opens a request and sends a short line to the group.
8. ⚙️ **Offer** to the longest-waiting available person, privately, with details and buttons; no response after 2 minutes → next person.
9. ⚙️ **🚨 Alert** in the group when the deadline is exceeded or no one is available.
10. 🧠 **Team member takes the lead**, calls them (📞), replies via WhatsApp (💬), or responds in the bot.
11. 🧠 **Close it** with the outcome; ⚙️ records the history, schedules a follow-up, and returns the team member to the queue.
12. 🧠 **Manager monitors** in `/gestor` (live, today, leads, export CSV).
13. ⚙️ **Daily backup** via the single cron job installed by `instalar-vps.sh` (`docker compose exec -T atende ./atende backup ...` → `/opt/atende-leads-backups/`).

## Run locally

```bash
./atende serve --porta 8080 --dados dados
# lead chat: http://localhost:8080/   team: /equipe   manager: /gestor (token in dados/negocio.json)
python3 -m pytest -q tests/        # contract (282 tests; build and Docker container only with TESTAR_DOCKER=1)
```

Fixed clock for testing: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` and `POST /api/tarefas/rodar`.

## Deploy to a VPS

1. **Start:** `./instalar-vps.sh` (or `docker compose up -d`; with Evolution on the same server: `docker compose --profile evolution up -d`). The application listens only on `127.0.0.1:8080`, and Evolution on `127.0.0.1:8081`. The installer generates the manager token and **team codes** (random, `secrets.token_urlsafe`) and prints them all at the end.
2. **Example secrets are blocked from network access:** if `negocio.json` still has `token_gestor` = `TROQUE-ESTE-TOKEN` or any code matching one in `exemplos/negocio.json`, the server only accepts connections on `127.0.0.1`/`localhost`. On `0.0.0.0` (as in Docker), it **refuses to start** with the message “run ./instalar-vps.sh or replace the secrets.” For testing/demos only: set `ATENDE_PERMITIR_EXEMPLO=1` in the environment (never in production).
3. **HTTPS:** configure a reverse proxy (Caddy or Nginx) from your domain to `127.0.0.1:8080`. Example with Caddy: `leads.seudominio.com { reverse_proxy 127.0.0.1:8080 }`. Set `url_publica` in `negocio.json`. The rate limit (5 wrong passwords per minute → 429) uses the `X-Forwarded-For` IP only when the connection comes from the local proxy.
4. **WhatsApp (QR code):** Evolution listens only on `127.0.0.1`, so open a tunnel from your computer:
   ```bash
   ssh -L 8081:127.0.0.1:8081 usuario@vps
   ```
   With the tunnel open, go to `http://localhost:8081/manager`. Sign in with the global API key (`EVOLUTION_API_KEY` from `.env`), click **Instance +**, name it `EVOLUTION_INSTANCIA` (default `loja`), choose the **Baileys** channel, save, open the instance, and scan the **QR code** with WhatsApp on your phone (Linked devices → Link a device). Without the manager, create the instance through the API on the VPS: `curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY>" -H 'Content-Type: application/json' -d '{"instanceName":"loja","integration":"WHATSAPP-BAILEYS","qrcode":true}'`.
5. **Evolution webhook:** set the `MESSAGES_UPSERT` event to `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (with the `evolution` profile, Compose already points it over the internal network). Messages with a `remoteJid` of `@lid` use the phone number from `remoteJidAlt`/`senderPn`; if neither is present, they appear under **discarded** in `/gestor`.
6. **Telegram webhook:** create a bot with @BotFather, add it to the team group as an admin (so it can pin the panel), and register it:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
7. **Daily backup — a single cron job** (installed in the root crontab by `instalar-vps.sh`). It runs inside the container and copies the backup **outside** the data volume:
   ```cron
   0 3 * * * cd /opt/atende-leads && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && mkdir -p /opt/atende-leads-backups && mv /opt/atende-leads/dados/.backup-cron.tar.gz /opt/atende-leads-backups/leads-$(date +\%F).tar.gz && find /opt/atende-leads-backups -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup
   ```
8. **Restore:** stop the service first (`restaurar` refuses to run while the server is up):
   ```bash
   docker compose stop atende
   docker compose run --rm -v /opt/atende-leads-backups:/backups atende \
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz
   docker compose start atende
   ```

Variables are in [`.env.exemplo`](.env.exemplo) (in Portuguese) (includes `ATENDE_PERMITIR_EXEMPLO`, for demos only). If an integration’s variables are missing, that integration stays disabled and everything else (the web panels) continues to work. Messages sent to Telegram and WhatsApp go through a background outbox: if an API hangs, support and `/api/saude` continue responding.

## Precautions

- Evolution is not the official WhatsApp API: use a dedicated number and do not send bulk messages to people who have not contacted you.
- Lead data is stored on your server (`dados/`). The backup contains personal data: store it with restricted access.

## Roadmap (outside v1)

Automatic voice agent · reply to WhatsApp through the panel · drag-and-drop sales funnel · external CRM via webhook · targets and rankings · multiple numbers · official Meta API · customer satisfaction survey.

## License

MIT. Open and free content from [INEMA.CLUB](https://inema.club).