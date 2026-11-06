#!/usr/bin/env bash
# Instala o atende-leads numa VPS com Docker.
#   ./instalar-vps.sh                 → pergunta tudo
#   ./instalar-vps.sh --sem-perguntas → lê do ambiente:
#       NEGOCIO_NOME, DOMINIO, TELEGRAM_TOKEN, TELEGRAM_GRUPO_ID, TELEGRAM_MODO (webhook|polling, padrão webhook),
#       COM_EVOLUTION (0|1), EVOLUTION_INSTANCIA (padrão "loja"), INSTALAR_SO_GERAR=1 (só gera .env e dados/negocio.json, não sobe nada)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

SEM_PERGUNTAS=0
for arg in "$@"; do
  case "$arg" in
    --sem-perguntas) SEM_PERGUNTAS=1 ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done
SO_GERAR="${INSTALAR_SO_GERAR:-0}"

perguntar() { # perguntar VAR "texto" "padrão"
  local var="$1" texto="$2" padrao="${3:-}" valor="${!1:-}"
  if [ "$SEM_PERGUNTAS" = "1" ]; then
    printf -v "$var" '%s' "${valor:-$padrao}"
    return
  fi
  read -r -p "$texto${padrao:+ [$padrao]}: " valor || true
  printf -v "$var" '%s' "${valor:-$padrao}"
}

segredo() { python3 -c "import secrets; print(secrets.token_urlsafe(${1:-24}))"; }

command -v python3 >/dev/null || { echo "Precisa de python3 para gerar os arquivos." >&2; exit 1; }

if [ "$SO_GERAR" != "1" ]; then
  if ! command -v docker >/dev/null || ! docker compose version >/dev/null 2>&1; then
    echo "Docker com o plugin compose não encontrado. Instale: curl -fsSL https://get.docker.com | sh" >&2
    exit 1
  fi
else
  command -v docker >/dev/null || echo "Aviso: Docker não encontrado (ok com INSTALAR_SO_GERAR=1)." >&2
fi

perguntar NEGOCIO_NOME "Nome do negócio" "Loja Exemplo"
perguntar DOMINIO "Domínio público (ex.: atende.sualoja.com.br)" "localhost:8080"
perguntar TELEGRAM_TOKEN "Token do bot do Telegram (BotFather; vazio = sem Telegram)" ""
perguntar TELEGRAM_GRUPO_ID "ID do grupo da equipe no Telegram (ex.: -100123...)" ""
perguntar TELEGRAM_MODO "Modo do Telegram: webhook (domínio com HTTPS) ou polling (sem domínio, teste local)" "webhook"
case "$TELEGRAM_MODO" in
  polling|webhook) ;;
  *) echo "TELEGRAM_MODO inválido: $TELEGRAM_MODO (use webhook ou polling)" >&2; exit 2 ;;
esac
perguntar COM_EVOLUTION "Subir a Evolution API (WhatsApp) junto? 1=sim 0=não" "1"
perguntar EVOLUTION_INSTANCIA "Nome da instância do WhatsApp na Evolution" "loja"

case "$DOMINIO" in
  http://*|https://*) URL_PUBLICA="$DOMINIO" ;;
  localhost*|127.*) URL_PUBLICA="http://$DOMINIO" ;;
  *) URL_PUBLICA="https://$DOMINIO" ;;
esac

TOKEN_GESTOR="$(segredo 24)"

# Valor de VAR no .env atual (sem `source`: o .env não é executado).
do_env() { [ -f .env ] && grep -E "^$1=" .env | head -n 1 | cut -d= -f2- || true; }

# Rodar de novo NÃO troca os segredos: com o volume do Postgres já criado, uma EVOLUTION_DB_SENHA nova
# derruba a Evolution, e um TELEGRAM_SEGREDO novo faz o webhook do Telegram dar 401. Só gera o que falta.
REAPROVEITADOS=""
reaproveitar() { # reaproveitar VAR "comando que gera"
  local atual
  atual="$(do_env "$1")"
  if [ -n "$atual" ] && ! printf '%s' "$atual" | grep -qi 'troque'; then
    printf -v "$1" '%s' "$atual"
    REAPROVEITADOS="$REAPROVEITADOS $1"
  else
    printf -v "$1" '%s' "$(eval "$2")"
  fi
}
reaproveitar WEBHOOK_SEGREDO 'segredo 24'
reaproveitar TELEGRAM_SEGREDO 'python3 -c "import secrets; print(secrets.token_hex(24))"'
reaproveitar EVOLUTION_API_KEY 'segredo 32'
reaproveitar EVOLUTION_DB_SENHA 'segredo 24'
CEREBRO_API_KEY="$(do_env CEREBRO_API_KEY)"
CEREBRO_HOSTS_PERMITIDOS="$(do_env CEREBRO_HOSTS_PERMITIDOS)"
WHISPER_CMD="$(do_env WHISPER_CMD)"

if [ -f .env ]; then
  cp .env ".env.bak-$(date +%Y%m%d%H%M%S)"
  echo "Já existia um .env: cópia guardada em .env.bak-*." >&2
  if [ -n "$REAPROVEITADOS" ]; then
    echo "Segredos reaproveitados do .env atual (não foram trocados):$REAPROVEITADOS" >&2
  fi
fi

if [ "$COM_EVOLUTION" = "1" ]; then EVO_URL="http://evolution-api:8080"; else EVO_URL=""; fi
if [ -n "$TELEGRAM_TOKEN" ]; then TG_URL="https://api.telegram.org"; else TG_URL=""; fi

umask 077
cat > .env <<EOF
# Gerado por instalar-vps.sh em $(date -Iseconds). Não versionar.
EVOLUTION_URL=$EVO_URL
EVOLUTION_API_KEY=$EVOLUTION_API_KEY
EVOLUTION_INSTANCIA=$EVOLUTION_INSTANCIA
WEBHOOK_SEGREDO=$WEBHOOK_SEGREDO
EVOLUTION_SERVER_URL=http://localhost:8081
EVOLUTION_DB_SENHA=$EVOLUTION_DB_SENHA
TELEGRAM_API_URL=$TG_URL
TELEGRAM_TOKEN=$TELEGRAM_TOKEN
TELEGRAM_GRUPO_ID=$TELEGRAM_GRUPO_ID
TELEGRAM_SEGREDO=$TELEGRAM_SEGREDO
TELEGRAM_MODO=$TELEGRAM_MODO
CEREBRO_API_KEY=$CEREBRO_API_KEY
CEREBRO_HOSTS_PERMITIDOS=$CEREBRO_HOSTS_PERMITIDOS
WHISPER_CMD=$WHISPER_CMD
TZ=America/Sao_Paulo
EOF

# Continua com umask 077: dados/negocio.json (token do gestor e códigos da equipe) só para o dono.
mkdir -p dados
if [ -f dados/negocio.json ]; then
  cp dados/negocio.json "dados/negocio.json.bak-$(date +%Y%m%d%H%M%S)"
  echo "Já existia dados/negocio.json: mantive a configuração (e o token do gestor) e troquei só nome e URL." >&2
  BASE=dados/negocio.json
  TOKEN_GESTOR="$(python3 -c "import json; print(json.load(open('dados/negocio.json', encoding='utf-8')).get('token_gestor') or '')")"
  [ -n "$TOKEN_GESTOR" ] && [ "$TOKEN_GESTOR" != "TROQUE-ESTE-TOKEN" ] || TOKEN_GESTOR="$(segredo 24)"
else
  BASE=exemplos/negocio.json
fi
NEGOCIO_NOME="$NEGOCIO_NOME" URL_PUBLICA="$URL_PUBLICA" TOKEN_GESTOR="$TOKEN_GESTOR" BASE="$BASE" python3 - <<'PY'
import json, os, secrets
cfg = json.load(open(os.environ['BASE'], encoding='utf-8'))
cfg['nome'] = os.environ['NEGOCIO_NOME']
cfg['url_publica'] = os.environ['URL_PUBLICA']
cfg['token_gestor'] = os.environ['TOKEN_GESTOR']
exemplo = json.load(open('exemplos/negocio.json', encoding='utf-8'))
fracos = {'', None} | {m.get('codigo') for m in exemplo.get('equipe', [])}
for m in cfg.get('equipe', []):
    cod = m.get('codigo')
    # código curto ou do exemplo é adivinhável: troca por um aleatório (>= 12 caracteres)
    if cod in fracos or len(str(cod)) < 12:
        m['codigo'] = f"{m['id']}-{secrets.token_urlsafe(9)}"
tmp = 'dados/negocio.json.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
os.replace(tmp, 'dados/negocio.json')
PY
chmod 600 .env dados/negocio.json
umask 022

# O container roda como uid 1000 (não root): a pasta de dados montada em /dados tem de ser dele
# (está 0700 pelo umask; de outro dono, o container não entra).
if [ "$(id -u)" = "0" ]; then
  chown -R 1000:1000 dados || true
elif [ "$(id -u)" != "1000" ] && command -v sudo >/dev/null; then
  sudo -n chown -R 1000:1000 dados 2>/dev/null || true
fi
DONO_DADOS="$(stat -c %u dados 2>/dev/null || echo '?')"
if [ "$DONO_DADOS" != "1000" ]; then
  if [ "$SO_GERAR" = "1" ]; then
    echo "Aviso: dados/ é do uid $DONO_DADOS; antes de subir rode: sudo chown -R 1000:1000 $DIR/dados" >&2
  else
    echo "ERRO: dados/ é do uid $DONO_DADOS e o container roda como uid 1000 (não entraria na pasta)." >&2
    echo "Rode:  sudo chown -R 1000:1000 $DIR/dados   e depois ./instalar-vps.sh de novo." >&2
    echo "(Os segredos do .env são reaproveitados na próxima execução.)" >&2
    exit 1
  fi
fi

echo "Gerado: .env e dados/negocio.json"
echo "Token do gestor: $TOKEN_GESTOR   (guarde; também está em dados/negocio.json)"
echo "Códigos da equipe (cada um usa o seu no /equipe e no /entrar do bot):"
python3 -c "import json; [print(f\"  {m['nome']} ({m['id']}): {m['codigo']}\") for m in json.load(open('dados/negocio.json', encoding='utf-8')).get('equipe', [])]"

# Backup: um único cron, rodando DENTRO do container e copiando para fora do volume de dados.
BACKUPS=/opt/atende-leads-backups
# Backup tem dados pessoais: pasta 700 e arquivo 600 (só o root lê).
CRON_LINHA="0 3 * * * cd $DIR && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && install -d -m 700 $BACKUPS && f=$BACKUPS/leads-\$(date +\\%F).tar.gz && mv $DIR/dados/.backup-cron.tar.gz \$f && chmod 600 \$f && find $BACKUPS -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup"

if [ "$SO_GERAR" = "1" ]; then
  echo "INSTALAR_SO_GERAR=1: nada foi subido."
  exit 0
fi

if [ "$COM_EVOLUTION" = "1" ]; then
  docker compose --profile evolution up -d --build
else
  docker compose up -d --build
fi

if [ "$(id -u)" = "0" ] && command -v crontab >/dev/null; then
  # troca qualquer linha antiga do atende-leads pela única linha de backup
  ( crontab -l 2>/dev/null | grep -v 'atende-leads-backup' | grep -v 'atende backup' ; echo "$CRON_LINHA" ) | crontab -
  CRON_MSG="instalado no crontab do root (crontab -l para ver)"
else
  CRON_MSG="rode como root ou ponha à mão no crontab do root"
fi

if [ "$TELEGRAM_MODO" = "polling" ]; then
  TG_PASSO="3. Telegram (modo polling): nada a configurar no BotFather. O servidor busca as mensagens sozinho
   (getUpdates) e desliga qualquer webhook antigo do bot ao subir."
else
  TG_PASSO="3. Telegram: aponte o webhook do bot para o seu domínio:
     curl \"https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook\" \\
       -d \"url=$URL_PUBLICA/webhook/telegram\" -d \"secret_token=<TELEGRAM_SEGREDO do .env>\""
fi

cat <<EOF

Pronto. Próximos passos:
1. Proxy HTTPS na frente da porta 127.0.0.1:8080 (Caddy é o mais simples):
     $DOMINIO {
       reverse_proxy 127.0.0.1:8080
     }
2. WhatsApp (Evolution, se subiu): a porta 8081 só escuta em 127.0.0.1. Do SEU computador, abra um túnel:
     ssh -L 8081:127.0.0.1:8081 usuario@sua-vps
   e acesse http://localhost:8081/manager (API Key global = EVOLUTION_API_KEY do .env).
   Crie a instância "$EVOLUTION_INSTANCIA" (Baileys) e leia o QR Code com o celular do número do atendimento.
   Ou pela API, na VPS:
     curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY do .env>" \\
       -H 'Content-Type: application/json' -d '{"instanceName":"$EVOLUTION_INSTANCIA","integration":"WHATSAPP-BAILEYS","qrcode":true}'
   O webhook global já aponta para http://atende:8080/webhook/evolution/<WEBHOOK_SEGREDO> (rede interna).
$TG_PASSO
   Ponha o bot no grupo da equipe; cada colaborador manda /entrar <código> no privado do bot.
4. Backup diário às 03:00, $CRON_MSG:
     $CRON_LINHA
   Os arquivos ficam em $BACKUPS (fora de dados/; pasta 700, arquivos 600), 30 dias.
   Restaurar: docker compose stop atende && docker compose run --rm -v $BACKUPS:/backups atende \\
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz && docker compose start atende
5. Painéis: $URL_PUBLICA/gestor (token acima) · $URL_PUBLICA/equipe (código de cada um) · chat em $URL_PUBLICA/
   Os códigos da equipe foram impressos acima (também em dados/negocio.json).
EOF
