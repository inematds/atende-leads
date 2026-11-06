# atende-leads

[![Atende Leads](guia/assets/banner-es.jpg)](https://inematds.github.io/atende-leads/guia/es/)

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## Qué es

Un sistema de código abierto que atiende a los leads que llegan por WhatsApp (y por el chat del sitio): un agente responde, los califica y, cuando es momento de que intervenga una persona, asigna el lead al colaborador que lleva más tiempo disponible por Telegram, con todos los datos y un botón para llamar. Funciona en una VPS con Docker, sin costo de API, y los datos se quedan en tu servidor.

## 📖 Guía de uso

Guía completa (landing + paso a paso): **https://inematds.github.io/atende-leads/guia/es/**

🎬 Video explicativo (2 min 37 s, en portugués): **https://inematds.github.io/atende-leads/videos/** · [YouTube](https://www.youtube.com/watch?v=-6VKlGAYwKY)

Atención de **leads por WhatsApp** con un agente que responde, califica y asigna el lead al **colaborador disponible** por Telegram, con todos los datos y un botón para llamar. Python 3 solo con la biblioteca estándar, estado en SQLite, Docker para VPS. Código abierto, versión `1.5.6`.

## Qué hace

- **Agente en WhatsApp** (Evolution API): responde las preguntas frecuentes, muestra precios solo de lo que está registrado, califica (nombre → qué busca → para cuándo) y asigna una nota al lead (caliente / tibio / frío).
- **Llama a una persona en 3 casos:** el lead lo pide, el agente detecta que hace falta (reclamo, problema, 2× «no entendí») o ve **posibilidad de venta** (precio, «quiero comprar», pago).
- **Ofrece el lead al colaborador que lleva más tiempo disponible**, por mensaje privado en Telegram: nombre, teléfono, nota, interés, resumen y últimos mensajes, con los botones **✅ Aceptar · ↪️ Pasar · 📞 Llamar · 💬 WhatsApp**.
- **Si no responde en 2 min** → se lo pasa al siguiente. Si un lead caliente no tiene responsable en 2 min (5 normalmente) o no hay nadie disponible → **alerta 🚨 en el grupo**, y el primero que toque Aceptar se lo lleva.
- **Panel fijo en el grupo** (`EQUIPE AGORA`): quién está disponible, atendiendo, ocupado o fuera, y la fila de leads en espera. Se actualiza con cada cambio.
- **Cierre con los botones:** Vendido (valor) · Retomar contacto (fecha) · En negociación · Sin interés (motivo) · Inválido, con una nota de texto o audio (transcripción local opcional). El colaborador vuelve al final de la fila de disponibles.
- **Retomadas de contacto programadas**, recordatorio de atención detenida (30 min), aviso de fin de jornada y mensaje fuera de horario con la próxima hora de inicio.
- **Tres interfaces web:** lead (chat, burbuja para el sitio y página «mi atención»), equipo (`/equipe`) y gerente (`/gestor`: en vivo, hoy, leads, registros, CSV).
- **LGPD:** `PARAR`, `apagar meus dados`, y el grupo nunca recibe el teléfono ni el texto del lead.
- **Base de conocimiento** (`/gestor` → Base de conocimiento): información del negocio (horario de atención humana, dirección, pagos, entregas, garantía, sitio web, observaciones) y preguntas frecuentes en un formulario, con la opción **Probar** («¿qué respondería el agente?»). «¿A qué hora hay atención humana?» responde con el horario y si está abierto en ese momento; un campo vacío nunca genera una respuesta inventada.
- **Sugerencia de respuesta para el equipo:** cuando un lead escribe durante una atención, el dueño recibe `💡 Sugerencia` en Telegram con **✅ Enviar / ✏️ Editar** (y en el panel, ya en el cuadro de respuesta). Cada respuesta se convierte en un registro de **aprendizaje** (se usó sin editar, se editó o se ignoró), y la pestaña **Aprendizaje** genera **propuestas para la base** (diarias, semanales o en el momento) para que el gestor las incorpore o descarte.
- **Cerebro:** reglas por defecto (sin costo, sin API). Opcional: **Anthropic (Claude)**, **OpenRouter**, Ollama local, un endpoint compatible con OpenAI o el CLI de tu suscripción (`claude`/`codex`, solo para pruebas locales), con retorno automático a las reglas si falla.

Contrato completo: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md).

## El proceso, de principio a fin

Quién hace qué: 🧠 el dueño/gerente · ⚙️ el sistema · 🤖 el agente.

1. 🧠 **Instalar en la VPS:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads && ./instalar-vps.sh` (pregunta el nombre, dominio y Telegram; genera secretos, `.env` y `dados/negocio.json`; inicia Docker).
2. 🧠 **Conectar WhatsApp:** crear el túnel `ssh -L 8081:127.0.0.1:8081 usuario@vps`, abrir `http://localhost:8081/manager`, crear la instancia y escanear el código QR con el número de atención (usa un número solo para esto).
3. 🧠 **Registrar** en `/gestor` → Registros: equipo (nombre, teléfono, código), productos con palabras y precio, horarios y plazos; → **Base de conocimiento**: información del negocio, preguntas frecuentes y el cerebro (y **Probar** preguntas como si fueras un cliente).
4. 🧠 **El equipo entra al bot:** cada colaborador envía `/entrar <código>` al chat privado del bot y toca 🟢 Disponible.
5. ⚙️ **Llega un lead** por WhatsApp o por la burbuja del sitio.
6. 🤖 **El agente atiende:** preguntas frecuentes, precio registrado, calificación y nota.
7. ⚙️ **Se activa un disparador** (pidió a una persona / hace falta / posibilidad de venta) → abre el caso y envía una línea breve al grupo.
8. ⚙️ **Se ofrece** al colaborador que lleva más tiempo disponible, en privado, con datos y botones; si no responde en 2 min → pasa al siguiente.
9. ⚙️ **Alerta 🚨** en el grupo cuando vence el plazo o no hay nadie disponible.
10. 🧠 **El colaborador se hace cargo**, llama (📞) o responde por WhatsApp (💬) o con una respuesta en el propio bot; ⚙️ con cada mensaje del lead llega una `💡 Sugerencia` (✅ Enviar / ✏️ Editar) y cada respuesta se incorpora al aprendizaje.
11. 🧠 **Cierra** con el resultado; ⚙️ el sistema guarda el historial, programa el próximo contacto y devuelve al colaborador a la fila.
12. 🧠 **El gestor hace seguimiento** en `/gestor` (en vivo, hoy, leads, exportar CSV) y, en la pestaña **Aprendizaje**, incorpora o descarta las propuestas para la base (⚙️ se generan cada semana, de forma predeterminada).
13. ⚙️ **Respaldo diario** mediante el único cron que instala `instalar-vps.sh` (`docker compose exec -T atende ./atende backup ...` → `/opt/atende-leads-backups/`).

> Puedes realizar los pasos 2 a 12 **en tu máquina**, sin dominio ni HTTPS, antes de pasar a la VPS: consulta [Probar en tu máquina (sin dominio)](#probar-en-tu-máquina-sin-dominio) (Telegram en `TELEGRAM_MODO=polling`).

## Ejecutar localmente

```bash
./atende serve --porta 8080 --dados dados
# chat do lead: http://localhost:8080/   equipe: /equipe   gestor: /gestor (token em dados/negocio.json)
python3 -m pytest -q tests/        # contrato (320 testes; build e container Docker só com TESTAR_DOCKER=1)
```

Reloj fijo para probar: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` y `POST /api/tarefas/rodar`.

## Probar en tu máquina (sin dominio)

Para ver todo el sistema funcionando (WhatsApp real + bot de Telegram) en una computadora con Docker, sin dominio público ni HTTPS. Telegram queda en **modo polling**: el servidor busca los mensajes del bot por su cuenta (`getUpdates`), así que no necesita `setWebhook` ni `TELEGRAM_SEGREDO`.

```bash
git clone https://github.com/inematds/atende-leads && cd atende-leads
# genera .env y dados/negocio.json con secretos nuevos; responde: dominio localhost:8080, modo de Telegram polling
INSTALAR_SO_GERAR=1 ./instalar-vps.sh
sudo chown -R 1000:1000 dados
docker compose --profile evolution up -d --build
```

Sin preguntas: `NEGOCIO_NOME="Minha Loja" DOMINIO=localhost:8080 TELEGRAM_TOKEN=<token do BotFather> TELEGRAM_GRUPO_ID=<id do grupo> TELEGRAM_MODO=polling COM_EVOLUTION=1 INSTALAR_SO_GERAR=1 ./instalar-vps.sh --sem-perguntas`. Si ya existe un `.env`, basta con añadir `TELEGRAM_MODO=polling` y ejecutar `docker compose up -d`.

1. **WhatsApp:** abre el manager de Evolution en <http://localhost:8081/manager> (API Key global = `EVOLUTION_API_KEY` de `.env`), crea la instancia con el nombre de `.env` (`EVOLUTION_INSTANCIA`) y escanea el código QR con el celular del número de prueba.
2. **Telegram:** añade el bot al grupo del equipo; cada colaborador envía `/entrar <código>` por privado al bot (el instalador imprimió los códigos y están en `dados/negocio.json`). `GET http://localhost:8080/api/saude` muestra `"telegram_modo": "polling"`.
3. **Paneles:** chat del lead en <http://localhost:8080/>, equipo en <http://localhost:8080/equipe>, gestor en <http://localhost:8080/gestor> (token en `dados/negocio.json`).

El bot solo habla con **un** servidor: al iniciarse en polling, desactiva el webhook del bot. Al pasar a la VPS, vuelve a `TELEGRAM_MODO=webhook` y ejecuta `setWebhook` (paso 3 del instalador).

## Implementar en la VPS

Todos los comandos de abajo usan la ruta **`/opt/atende-leads`** (también el cron de respaldo). Si instalas en otro lugar, cambia la ruta en todos ellos.

0. **Descargar:** `git clone https://github.com/inematds/atende-leads /opt/atende-leads && cd /opt/atende-leads`
1. **Iniciar:** `cd /opt/atende-leads && ./instalar-vps.sh`. Genera `.env` y `dados/negocio.json` con permisos solo para el dueño (`umask 077`), el token del gerente y los **códigos del equipo** (aleatorios, `secrets.token_urlsafe`), asigna la carpeta `dados/` al uid 1000 (el contenedor **no se ejecuta como root**; si no eres root, intenta `sudo -n chown -R 1000:1000 dados`, y si no lo consigue **se detiene antes de iniciar** y muestra el comando), inicia compose e imprime todo al final. La aplicación escucha solo en `127.0.0.1:8080` y Evolution en `127.0.0.1:8081`.
   - **Volver a ejecutarlo** (cambiar el dominio, conectar Telegram) **no cambia los secretos**: se reutilizan los valores de `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY` y `EVOLUTION_DB_SENHA` que ya están en `.env` (la salida indica cuáles); solo se generan los que faltan (o todavía contienen `troque`). Cambiar la contraseña de Postgres con el volumen ya creado dejaría Evolution fuera de servicio, y un `TELEGRAM_SEGREDO` nuevo haría que el webhook de Telegram devolviera 401. También se conservan el token del gerente y los códigos del equipo.
   - **Sin el instalador** (`docker compose up -d`, o `docker compose --profile evolution up -d` con Evolution en el mismo servidor): `cd /opt/atende-leads && cp .env.exemplo .env && mkdir -p dados && cp exemplos/negocio.json dados/` y **cambia** `token_gestor` y los códigos del equipo en `dados/negocio.json` (códigos de 12+ caracteres), además de `WEBHOOK_SEGREDO`, `TELEGRAM_SEGREDO`, `EVOLUTION_API_KEY` y `EVOLUTION_DB_SENHA` en `.env`; con el perfil `evolution`, agrega también `EVOLUTION_URL=http://evolution-api:8080` (la URL interna; vacía = WhatsApp desactivado); después ejecuta `sudo chown -R 1000:1000 /opt/atende-leads/dados`. Si queda algún secreto de ejemplo, el contenedor se niega a iniciar (punto 2).
   - **Evolution externa** (ya funciona en otro servidor; no uses el perfil `evolution`): en `.env`, configura `EVOLUTION_URL=https://<sua-evolution>`, `EVOLUTION_API_KEY=<API key dela>`, `EVOLUTION_INSTANCIA=<instância>`; y, en su manager, el webhook `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (punto 5). Inicia solo con `docker compose up -d`.
   - **Actualizar una instalación anterior:** `cd /opt/atende-leads && git pull && sudo chown -R 1000:1000 dados && docker compose up -d --build` (si es anterior a la versión 1.0.2, `chown` es obligatorio; con el cerebro `openai` y una clave, agrega `CEREBRO_HOSTS_PERMITIDOS` a `.env`).
2. **Los secretos de ejemplo impiden exponerse a la red:** si `negocio.json` aún tiene `token_gestor` = `TROQUE-ESTE-TOKEN` o algún código igual a los de `exemplos/negocio.json`, o si una integración está activa con `WEBHOOK_SEGREDO`/`TELEGRAM_SEGREDO` vacío, con menos de 16 caracteres o que contenga `troque` (o Evolution está activa con `EVOLUTION_API_KEY` que contenga `troque`), el servidor solo acepta iniciar en `127.0.0.1`/`localhost`. En `0.0.0.0` (como en Docker), **se niega a iniciar** con el mensaje «ejecuta ./instalar-vps.sh o cambia los secretos». `.env.exemplo` viene con `EVOLUTION_URL=` y `TELEGRAM_TOKEN=` vacíos: las integraciones quedan desactivadas hasta que los completes. Solo para pruebas/demostraciones: `ATENDE_PERMITIR_EXEMPLO=1` en el entorno (nunca en producción).
3. **HTTPS:** configura un proxy inverso (Caddy o Nginx) desde tu dominio a `127.0.0.1:8080`. Ejemplo con Caddy: `leads.tudominio.com { reverse_proxy 127.0.0.1:8080 }`. Ajusta `url_publica` en `negocio.json`. Los límites por IP (5 contraseñas incorrectas por minuto → las incorrectas reciben 429, la correcta siempre pasa; 5 conversaciones nuevas del chat web en 10 min; 3 solicitudes de atención por web por hora) usan la IP de `X-Forwarded-For` cuando la conexión viene de un proxy confiable: `ATENDE_PROXY_CONFIAVEL` (CIDR; predeterminado `127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16`, que incluye Caddy en el host cuando llega por el puente de Docker). Vacío = nunca confiar en `X-Forwarded-For`. El chat web es público: además de esos límites, el total de conversaciones nuevas también tiene un tope, y solo puede aceptar un lead el colaborador a quien se le ofreció o, en una alerta 🚨, quien toque Aceptar primero.
4. **WhatsApp (código QR):** el puerto de Evolution solo escucha en `127.0.0.1`, así que abre un túnel desde tu computadora:
   ```bash
   ssh -L 8081:127.0.0.1:8081 usuario@vps
   ```
   Con el túnel abierto, accede a `http://localhost:8081/manager`. Inicia sesión con la API Key global (`EVOLUTION_API_KEY` de `.env`), haz clic en **Instance +**, usa el nombre de `EVOLUTION_INSTANCIA` (predeterminado `loja`), canal **Baileys**, guarda, abre la instancia y escanea el **código QR** con el WhatsApp del celular (Dispositivos vinculados → Vincular un dispositivo). Sin el manager, usa la API en la VPS: `curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY>" -H 'Content-Type: application/json' -d '{"instanceName":"loja","integration":"WHATSAPP-BAILEYS","qrcode":true}'`.
5. **Webhook de Evolution:** evento `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (con el perfil `evolution`, compose ya apunta por la red interna). Los mensajes con `remoteJid` `@lid` usan el teléfono de `remoteJidAlt`/`senderPn`; si no está, aparecen en **descartes** en `/gestor`.
6. **Webhook de Telegram:** crea el bot con @BotFather, agrégalo al grupo del equipo como administrador (para fijar el panel) y registra:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
7. **Respaldo diario — un solo cron** (`instalar-vps.sh` lo instala en el crontab de root). Se ejecuta dentro del contenedor y copia los datos **fuera** del volumen de datos, a una carpeta `700` con archivos `600` (el respaldo contiene datos personales):
   ```cron
   0 3 * * * cd /opt/atende-leads && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && install -d -m 700 /opt/atende-leads-backups && f=/opt/atende-leads-backups/leads-$(date +\%F).tar.gz && mv /opt/atende-leads/dados/.backup-cron.tar.gz $f && chmod 600 $f && find /opt/atende-leads-backups -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup
   ```
8. **Restaurar:** detén el servicio antes (el comando `restaurar` se niega a ejecutarse si el servidor está activo):
   ```bash
   cd /opt/atende-leads
   docker compose stop atende
   docker compose run --rm -v /opt/atende-leads-backups:/backups atende \
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz
   docker compose start atende
   ```

Variables en [`.env.exemplo`](.env.exemplo) (incluye `ATENDE_PROXY_CONFIAVEL`, `ATENDE_MAX_CONEXOES` — conexiones simultáneas, predeterminado 64; por encima de ese límite devuelve 503, pero `/api/saude` sigue respondiendo aunque esté lleno —, `CEREBRO_HOSTS_PERMITIDOS` y `ATENDE_PERMITIR_EXEMPLO`, solo para demostraciones). Si no configuras las variables de una integración, esta queda desactivada y el resto funciona (paneles web). Los envíos a Telegram y WhatsApp salen por una bandeja de salida en segundo plano: si una API se bloquea, la atención y `/api/saude` siguen respondiendo.

## Cerebro con IA (opcional)

Sin ninguna configuración, todo funciona con **reglas** (costo cero). Para que el agente responda preguntas fuera de las preguntas frecuentes, resuma el caso, sugiera respuestas al equipo y proponga elementos para la base, activa un cerebro en `/gestor` → **Base de conocimiento** → Cerebro (o en `negocio.json`). La clave se guarda **solo** en `.env` (`CEREBRO_API_KEY`), nunca en el JSON ni en la pantalla. Si falta la clave, el modelo la rechaza, da error o tarda demasiado (20 s), la respuesta vuelve a las reglas; el estado de salud (`/api/saude`) muestra `cerebro_ok` y el motivo.

**Anthropic (Claude), recomendado:**

```json
"cerebro": { "tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low" }
```

```bash
# .env
CEREBRO_API_KEY=sk-ant-...   # clave de la API de Anthropic
```

Luego ejecuta `docker compose up -d` (o reinicia `./atende serve`). `esforco` = `low` (predeterminado, más barato), `medium`, `high`, `xhigh` o `max`. Las respuestas son breves (hasta 1024 tokens) y la base se envía con caché del prompt, por lo que el costo por respuesta breve es bajo (aún menor con `low`). Instrucción fija: portugués de Brasil, breve y cordial, solo la base; nunca inventa precios, plazos ni condiciones; si no sabe, dice que llamará a alguien.

**Otros tipos:**

| tipo | qué necesita | observación |
|---|---|---|
| `openrouter` | `modelo` (p. ej., `anthropic/claude-sonnet-5.5`, `z-ai/glm-5`) + `CEREBRO_API_KEY` de OpenRouter | URL fija `openrouter.ai` |
| `openai` | `url` + `modelo` (+ clave y `CEREBRO_HOSTS_PERMITIDOS`) | cualquier endpoint `/v1/chat/completions` |
| `ollama` | `url` + `modelo` | local, sin clave |
| `claude_cli` | CLI `claude` con sesión iniciada (`modelo`, predeterminado `sonnet`) | suscripción personal |
| `codex_cli` | CLI `codex` con sesión iniciada + `modelo` | suscripción personal |

> ⚠️ **`claude_cli` / `codex_cli` usan tu suscripción personal mediante el CLI** (`claude -p` / `codex exec`, prompt por stdin, 60 s). Sirven solo para que **el dueño haga pruebas** al ejecutar `./atende serve` directamente en la máquina con el CLI con sesión iniciada (`CEREBRO_CLI_BIN` si el binario no está en el PATH). **El binario no existe dentro de Docker**: el estado de salud muestra `cerebro_ok: false` y todo vuelve a las reglas. Para clientes en producción, usa una API (`anthropic`, `openrouter`, `openai`) u Ollama.

## Precauciones

- Evolution no es la API oficial de WhatsApp: usa un número dedicado y no envíes mensajes masivos a quienes no te hayan escrito.
- Los datos de los leads quedan en tu servidor (`dados/`). El respaldo contiene datos personales: guárdalo con acceso restringido.
- Evolution del compose **no guarda** copias de mensajes, contactos ni conversaciones (`DATABASE_SAVE_*` = `false`, por la LGPD): los datos que necesita la atención quedan en `dados/leads.db`, y la opción «apagar meus dados» los elimina.
- **Quien tenga el token del gerente puede cambiar `cerebro.url`** en `/gestor`. Por eso, `CEREBRO_API_KEY` solo se envía a un host incluido en `CEREBRO_HOSTS_PERMITIDOS` en `.env` (por ejemplo: `CEREBRO_HOSTS_PERMITIDOS=api.seuprovedor.com`); vacío = la clave no se envía a nadie. El token nuevo del gerente, creado desde `/gestor`, debe tener al menos 16 caracteres y no puede ser el de ejemplo.

## Próximamente (fuera de la v1)

Agente de voz automático · responder WhatsApp desde el panel · embudo arrastrable · CRM externo por webhook · metas y clasificación · varios números · API oficial de Meta · encuesta de satisfacción.

## Licencia

MIT. Contenido abierto y gratuito de [INEMA.CLUB](https://inema.club).
