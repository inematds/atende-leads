#!/usr/bin/env bash
# Instala o atende-leads numa VPS com Docker.
#   ./instalar-vps.sh                 → pergunta tudo
#   ./instalar-vps.sh --sem-perguntas → lê do ambiente:
#       NEGOCIO_NOME, DOMINIO, TELEGRAM_TOKEN, TELEGRAM_GRUPO_ID, COM_EVOLUTION (0|1),
#       EVOLUTION_INSTANCIA (padrão "loja"), INSTALAR_SO_GERAR=1 (só gera .env e dados/negocio.json, não sobe nada)
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

SEM_PERGUNTAS=0
for arg in "$@"; do
  case "$arg" in
    --sem-perguntas) SEM_PERGUNTAS=1 ;;
    -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
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
perguntar COM_EVOLUTION "Subir a Evolution API (WhatsApp) junto? 1=sim 0=não" "1"
perguntar EVOLUTION_INSTANCIA "Nome da instância do WhatsApp na Evolution" "loja"

case "$DOMINIO" in
  http://*|https://*) URL_PUBLICA="$DOMINIO" ;;
  localhost*|127.*) URL_PUBLICA="http://$DOMINIO" ;;
  *) URL_PUBLICA="https://$DOMINIO" ;;
esac

TOKEN_GESTOR="$(segredo 24)"
WEBHOOK_SEGREDO="$(segredo 24)"
TELEGRAM_SEGREDO="$(python3 -c "import secrets; print(secrets.token_hex(24))")"
EVOLUTION_API_KEY="$(segredo 32)"
EVOLUTION_DB_SENHA="$(segredo 24)"

if [ -f .env ]; then
  cp .env ".env.bak-$(date +%Y%m%d%H%M%S)"
  echo "Já existia um .env: cópia guardada em .env.bak-*." >&2
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
CEREBRO_API_KEY=
WHISPER_CMD=
TZ=America/Sao_Paulo
EOF
umask 022

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
for m in cfg.get('equipe', []):
    if m.get('codigo') in (None, '', 'ana-1234'):
        m['codigo'] = f"{m['id']}-{secrets.randbelow(9000) + 1000}"
tmp = 'dados/negocio.json.tmp'
with open(tmp, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, ensure_ascii=False, indent=2)
os.replace(tmp, 'dados/negocio.json')
PY

echo "Gerado: .env e dados/negocio.json"
echo "Token do gestor: $TOKEN_GESTOR   (guarde; também está em dados/negocio.json)"

if [ "$SO_GERAR" = "1" ]; then
  echo "INSTALAR_SO_GERAR=1: nada foi subido."
  exit 0
fi

if [ "$COM_EVOLUTION" = "1" ]; then
  docker compose --profile evolution up -d --build
else
  docker compose up -d --build
fi

cat <<EOF

Pronto. Próximos passos:
1. Proxy HTTPS na frente da porta 127.0.0.1:8080 (Caddy é o mais simples):
     $DOMINIO {
       reverse_proxy 127.0.0.1:8080
     }
2. WhatsApp (Evolution, se subiu): crie a instância e leia o QR Code:
     curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY do .env>" \\
       -H 'Content-Type: application/json' -d '{"instanceName":"$EVOLUTION_INSTANCIA","integration":"WHATSAPP-BAILEYS","qrcode":true}'
   O webhook global já aponta para http://atende:8080/webhook/evolution/<WEBHOOK_SEGREDO> (rede interna).
3. Telegram: aponte o webhook do bot para o seu domínio:
     curl "https://api.telegram.org/bot<TELEGRAM_TOKEN>/setWebhook" \\
       -d "url=$URL_PUBLICA/webhook/telegram" -d "secret_token=<TELEGRAM_SEGREDO do .env>"
   Ponha o bot no grupo da equipe; cada colaborador manda /entrar <código> no privado do bot.
4. Backup diário (cron do root):
     0 3 * * * cd $DIR && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/backup-\$(date +\\%u).tar.gz
5. Painéis: $URL_PUBLICA/gestor (token acima) · $URL_PUBLICA/equipe (código de cada um) · chat em $URL_PUBLICA/
EOF
