# Instalar numa VPS — passo a passo (para quem nunca fez)

Ao final você terá o atendimento no ar num endereço seu, com cadeado (HTTPS), por exemplo `https://atende.sualoja.com.br`.
Tempo: cerca de 40 minutos. Custo: a VPS (a partir de uns R$ 30/mês) e, se quiser a IA, a chave do modelo.

> Combinado de leitura: o que está em `caixa cinza` você **copia e cola** no terminal. Troque só o que estiver entre `<sinais>`.

---

## O que você precisa antes

| Item | Para quê | Onde conseguir |
|---|---|---|
| Uma **VPS** com Ubuntu 24.04, 2 GB de RAM ou mais | É o computador na nuvem que fica ligado 24 h | Hetzner, Hostinger, DigitalOcean, Contabo… |
| Um **domínio** (ou subdomínio) | O endereço do sistema | Registro.br, Namecheap, Cloudflare… |
| Um **bot do Telegram** + um **grupo da equipe** | Onde a equipe recebe os leads | Telegram → @BotFather (passo 3) |
| Um **número de WhatsApp só para o atendimento** | Onde os clientes falam | Um chip pré-pago com WhatsApp num celular |
| (Opcional) **chave de IA** | Sugestões de resposta e respostas mais inteligentes | Anthropic, OpenRouter… Sem ela, funciona por regras |

⚠️ Não use seu número pessoal no WhatsApp do sistema: a Evolution não é a API oficial e o número pode ser bloqueado. E nunca faça disparo em massa.

---

## Passo 1 — Entrar na VPS

No seu computador, abra o **Terminal** (Windows: "PowerShell") e digite, trocando pelo IP que a empresa da VPS te mandou:

```
ssh root@<IP-da-VPS>
```

Na primeira vez ele pergunta se confia: digite `yes` e Enter. Depois a senha (ela não aparece enquanto você digita — é normal).

## Passo 2 — Apontar o domínio para a VPS

No painel onde está o seu domínio, crie um registro:

- **Tipo:** `A`
- **Nome:** o subdomínio (ex.: `atende`) — vira `atende.sualoja.com.br`
- **Valor / destino:** o IP da VPS
- Se for Cloudflare: deixe a nuvem **cinza** (só DNS)

Espere uns 5 minutos.

## Passo 3 — Criar o bot e o grupo do Telegram

1. No Telegram, procure **@BotFather**, mande `/newbot`, escolha um nome e um usuário terminado em `bot`. Ele te dá um **token** (algo como `123456:ABC...`). Guarde.
2. Crie um **grupo** da equipe, adicione o bot e torne-o **administrador** (para ele fixar o painel).
3. Para descobrir o **ID do grupo**: adicione também o bot **@RawDataBot** no grupo; ele mostra um número começando com `-100…`. Anote e depois remova o @RawDataBot.

## Passo 4 — Instalar (um comando por vez)

De volta ao terminal da VPS:

```
curl -fsSL https://get.docker.com | sh
```
(instala o Docker — demora 1 a 2 minutos)

```
apt-get install -y git nginx certbot python3-certbot-nginx
```

```
git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads
```

```
./instalar-vps.sh
```

O instalador faz perguntas. Responda assim:

| Pergunta | O que responder |
|---|---|
| Nome do negócio | o nome que o cliente vai ver (ex.: `Viva Pilates`) |
| Domínio público | o endereço do passo 2, sem `https://` (ex.: `atende.sualoja.com.br`) |
| Token do bot | o token do passo 3 |
| ID do grupo | o número `-100…` do passo 3 |
| Modo do Telegram | `webhook` (Enter) |
| Subir a Evolution junto? | `1` (Enter) |
| Nome da instância | `loja` (Enter) |

No fim ele mostra o **token do gestor** e os **códigos da equipe**. **Copie e guarde num lugar seguro** (um gerenciador de senhas).

## Passo 5 — Ligar o endereço com cadeado (HTTPS)

Copie, troque o domínio nas **duas** linhas onde aparece e cole:

```
cat > /etc/nginx/sites-available/atende <<'EOF'
server {
  listen 80;
  server_name <seu-dominio>;
  location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }
}
EOF
ln -sf /etc/nginx/sites-available/atende /etc/nginx/sites-enabled/atende && nginx -t && systemctl reload nginx
certbot --nginx -d <seu-dominio> --non-interactive --agree-tos -m <seu-email> --redirect
```

Teste no navegador: `https://<seu-dominio>/` deve abrir o chat. 🎉

## Passo 6 — Avisar o Telegram onde está o sistema

Troque o token, o domínio e o segredo (o segredo está no arquivo `.env`: rode `grep TELEGRAM_SEGREDO /opt/atende-leads/.env` para ver):

```
curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<seu-dominio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"
```

Deve responder `"ok":true`.

## Passo 7 — Conectar o WhatsApp (ler o QR Code)

O painel da Evolution fica fechado para a internet (por segurança). Para abrir, **no seu computador** (não na VPS), rode:

```
ssh -L 8081:127.0.0.1:8081 root@<IP-da-VPS>
```

Deixe essa janela aberta e, no navegador do seu computador, abra **http://localhost:8081/manager**.

1. Ele pede a **chave da API**: na VPS rode `grep EVOLUTION_API_KEY /opt/atende-leads/.env` e cole.
2. Crie a instância com o nome **`loja`** (o mesmo do instalador).
3. Clique para conectar: aparece um **QR Code**.
4. No celular do número do atendimento: WhatsApp → ⋮ → **Aparelhos conectados** → **Conectar aparelho** → aponte para o QR.

Pronto: mande "oi" de outro celular para esse número e veja o agente responder.

## Passo 8 — Entrar como equipe e como gestor

- **Cada colaborador:** abre o bot no Telegram (privado), manda `/entrar <código dele>` e toca **🟢 Livre**.
- **Painel da equipe:** `https://<seu-dominio>/equipe` (com o código).
- **Painel do gestor:** `https://<seu-dominio>/gestor` (com o token do gestor). Em **Base de conhecimento**, preencha horário, endereço, formas de pagamento e as perguntas frequentes — é o que o agente usa para responder.

## Passo 9 (opcional) — Ligar a IA

1. No painel do gestor → **Base de conhecimento** → **Cérebro**: escolha, por exemplo, *Anthropic* com modelo `claude-sonnet-5-5` e esforço `low`.
2. Na VPS, coloque a chave no `.env` e reinicie:
```
nano /opt/atende-leads/.env        # preencha a linha CEREBRO_API_KEY=...  (Ctrl+O, Enter, Ctrl+X)
cd /opt/atende-leads && docker compose --profile evolution up -d
```

---

## Dia a dia

| Quero… | Comando (na VPS, dentro de `/opt/atende-leads`) |
|---|---|
| Ver se está tudo rodando | `docker compose --profile evolution ps` |
| Ver os últimos registros | `docker compose logs --tail 50 atende` |
| Reiniciar | `docker compose --profile evolution restart` |
| Atualizar para a versão nova | `git pull && docker compose --profile evolution up -d --build` |
| Fazer backup agora | `docker compose exec -T atende ./atende backup --dados /dados --saida /dados/backup.tar.gz` |

O instalador já deixa um **backup diário** automático em `/opt/atende-leads-backups` (guardado por 30 dias).

## Deu problema?

| Sintoma | O que fazer |
|---|---|
| O site não abre | `docker compose ps` — o `atende` precisa estar `healthy`. Se não, veja os logs. |
| O bot não responde no Telegram | Refaça o passo 6 e confira se o bot é admin do grupo. |
| O WhatsApp parou | Abra o painel da Evolution (passo 7) e veja se a instância está "open"; senão, leia o QR de novo. |
| Esqueci o token do gestor | `grep token_gestor /opt/atende-leads/dados/negocio.json` |
| "Recusa subir com segredos de exemplo" | Rode `./instalar-vps.sh` de novo: ele gera segredos novos e mantém os que já existiam. |
