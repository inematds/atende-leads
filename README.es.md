# atende-leads

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## 📖 Guía de uso

Guía completa (landing + paso a paso): **https://inematds.github.io/atende-leads/guia/es/**

Atención de **leads por WhatsApp** con un agente que responde, califica y deriva el lead al **colaborador disponible** por Telegram, con todos los datos y un botón para llamar. Python 3 solo con la biblioteca estándar, estado en SQLite y Docker para VPS. Código abierto, versión `1.0.1`.

## Qué hace

- **Agente en WhatsApp** (Evolution API): responde las preguntas frecuentes, muestra el precio solo de lo que está registrado, califica (nombre → qué busca → para cuándo) y asigna una puntuación al lead (caliente / tibio / frío).
- **Llama a una persona en 3 casos:** el lead lo pide, el agente detecta que hace falta (queja, problema, 2 veces «no entendí») o ve una **posibilidad de venta** (precio, «quiero comprar», pago).
- **Se lo ofrece al colaborador que lleva más tiempo disponible**, por privado en Telegram: nombre, teléfono, puntuación, interés, resumen y últimos mensajes, con los botones **✅ Assumir (Tomar) · ↪️ Passar (Derivar) · 📞 Ligar (Llamar) · 💬 WhatsApp**.
- **Si no responde en 2 min** → pasa al siguiente. Si un lead caliente sigue sin responsable después de 2 min (5 en condiciones normales) o no hay nadie disponible → **alerta 🚨 en el grupo**, y quien toque primero Assumir (Tomar) se lo queda.
- **Panel fijo en el grupo** (`EQUIPE AGORA` (EQUIPO AHORA)): quién está disponible, atendiendo, ocupado o ausente, y la fila de leads en espera. Se actualiza con cada cambio.
- **Cierre** con los botones: Vendeu (Vendió) (valor) · Retornar (Contactar de nuevo) (fecha) · Negociando (En negociación) · Sem interesse (Sin interés) (motivo) · Inválido (No válido), con una nota de texto o audio (transcripción local opcional). El colaborador vuelve al final de la fila de disponibles.
- **Seguimientos programados**, recordatorio de atención inactiva (30 min), aviso de fin de la jornada, mensaje fuera del horario con el próximo horario de inicio.
- **Tres interfaces web:** lead (chat, burbuja para el sitio y página «mi atención»), equipo (`/equipe`) y responsable (`/gestor`: en vivo, hoy, leads, registros, CSV).
- **LGPD:** `PARAR` (DETENER), `apagar meus dados` (borrar mis datos), y el grupo nunca recibe el teléfono ni el texto del lead.
- **Cerebro:** reglas por defecto (sin costo, sin API). Opcional: Ollama local o un endpoint compatible con OpenAI configurado por el propio negocio, con vuelta automática a las reglas si falla.

Contrato completo: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md) (en portugués).

## El proceso, de principio a fin

Quién hace qué: 🧠 el dueño/responsable · ⚙️ el sistema · 🤖 el agente.

1. 🧠 **Instalar en la VPS:** `./instalar-vps.sh` (pregunta el nombre, dominio y Telegram; genera secretos, `.env` y `dados/negocio.json`; inicia Docker).
2. 🧠 **Conectar WhatsApp:** túnel `ssh -L 8081:127.0.0.1:8081 usuario@vps`, abrir `http://localhost:8081/manager`, crear la instancia y escanear el código QR con el número de atención (usa un número solo para esto).
3. 🧠 **Registrar** en `/gestor` → Cadastros: equipo (nombre, teléfono, código), productos con palabras y precio, preguntas frecuentes, horarios y plazos.
4. 🧠 **El equipo entra al bot:** cada colaborador envía `/entrar` (/entrar) `<código>` por privado al bot y toca 🟢 Livre (Disponible).
5. ⚙️ **Llega un lead** por WhatsApp o por la burbuja del sitio.
6. 🤖 **El agente atiende:** preguntas frecuentes, precios registrados, calificación y puntuación.
7. ⚙️ **Se activa un disparador** (pidió a una persona / hace falta / posibilidad de venta) → abre el caso y envía una línea breve al grupo.
8. ⚙️ **Se ofrece** al colaborador que lleva más tiempo disponible, por privado, con datos y botones; si no responde en 2 min → pasa al siguiente.
9. ⚙️ **Alerta 🚨** en el grupo cuando se vence el plazo o no hay nadie disponible.
10. 🧠 **El colaborador lo toma**, llama (📞), responde por WhatsApp (💬) o contesta directamente en el bot.
11. 🧠 **Cierra** con el resultado; ⚙️ el sistema guarda el historial, programa el seguimiento y devuelve al colaborador a la fila.
12. 🧠 **El responsable supervisa** en `/gestor` (en vivo, hoy, leads, exportar CSV).
13. ⚙️ **Copia de seguridad diaria** mediante el único cron que instala `instalar-vps.sh` (`docker compose exec -T atende ./atende backup ...` → `/opt/atende-leads-backups/`).

## Ejecutar localmente

```bash
./atende serve --porta 8080 --dados dados
# chat del lead: http://localhost:8080/   equipo: /equipe   responsable: /gestor (token en dados/negocio.json)
python3 -m pytest -q tests/        # contrato (282 pruebas; build y contenedor Docker solo con TESTAR_DOCKER=1)
```

Fija el reloj para hacer pruebas: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` y `POST /api/tarefas/rodar`.

## Desplegar en la VPS

1. **Iniciar:** `./instalar-vps.sh` (o `docker compose up -d`; con Evolution en el mismo servidor: `docker compose --profile evolution up -d`). La aplicación escucha solo en `127.0.0.1:8080` y Evolution en `127.0.0.1:8081`. El instalador genera el token del responsable y los **códigos del equipo** (aleatorios, `secrets.token_urlsafe`) y los muestra todos al final.
2. **Los secretos de ejemplo no se exponen en la red:** si `negocio.json` todavía tiene `token_gestor` = `TROQUE-ESTE-TOKEN` o algún código igual al de `exemplos/negocio.json`, el servidor solo acepta iniciar en `127.0.0.1`/`localhost`. En `0.0.0.0` (como en Docker) **rechaza el inicio** con el mensaje «ejecuta ./instalar-vps.sh o cambia los secretos». Solo para pruebas o demostraciones: `ATENDE_PERMITIR_EXEMPLO=1` en el entorno (nunca en producción).
3. **HTTPS:** proxy inverso (Caddy o Nginx) desde tu dominio a `127.0.0.1:8080`. Ej. con Caddy: `leads.tudominio.com { reverse_proxy 127.0.0.1:8080 }`. Ajusta `url_publica` en `negocio.json`. El límite de intentos (5 contraseñas incorrectas por minuto → 429) usa la IP de `X-Forwarded-For` solo cuando la conexión viene del proxy local.
4. **WhatsApp (código QR):** el puerto de Evolution solo escucha en `127.0.0.1`, así que abre un túnel desde tu computadora:
   ```bash
   ssh -L 8081:127.0.0.1:8081 usuario@vps
   ```
   con el túnel abierto, accede a `http://localhost:8081/manager`. Ingresa con la API Key global (`EVOLUTION_API_KEY` de `.env`), haz clic en **Instance +**, asigna el nombre de `EVOLUTION_INSTANCIA` (por defecto `loja`), elige el canal **Baileys**, guarda, abre la instancia y escanea el **código QR** con WhatsApp en el celular (Dispositivos vinculados → Vincular dispositivo). Sin el manager, mediante la API en la VPS: `curl -X POST http://127.0.0.1:8081/instance/create -H "apikey: <EVOLUTION_API_KEY>" -H 'Content-Type: application/json' -d '{"instanceName":"loja","integration":"WHATSAPP-BAILEYS","qrcode":true}'`.
5. **Webhook de Evolution:** evento `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (con el perfil `evolution`, compose ya lo dirige por la red interna). Los mensajes con `remoteJid` `@lid` usan el teléfono de `remoteJidAlt`/`senderPn`; si no lo tienen, aparecen en **descartes** en `/gestor`.
6. **Webhook de Telegram:** crea el bot en @BotFather, agrégalo como administrador al grupo del equipo (para fijar el panel) y regístralo:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
7. **Copia de seguridad diaria: un solo cron** (`instalar-vps.sh` lo instala en el crontab de root). Se ejecuta dentro del contenedor y copia **fuera** del volumen de datos:
   ```cron
   0 3 * * * cd /opt/atende-leads && docker compose exec -T atende ./atende backup --dados /dados --saida /dados/.backup-cron.tar.gz && mkdir -p /opt/atende-leads-backups && mv /opt/atende-leads/dados/.backup-cron.tar.gz /opt/atende-leads-backups/leads-$(date +\%F).tar.gz && find /opt/atende-leads-backups -name 'leads-*.tar.gz' -mtime +30 -delete # atende-leads-backup
   ```
8. **Restaurar:** detén el servicio antes (el comando `restaurar` rechaza ejecutarse si el servidor está en marcha):
   ```bash
   docker compose stop atende
   docker compose run --rm -v /opt/atende-leads-backups:/backups atende \
     ./atende restaurar --dados /dados --arquivo /backups/leads-AAAA-MM-DD.tar.gz
   docker compose start atende
   ```

Variables en [`.env.exemplo`](.env.exemplo) (en portugués; incluye `ATENDE_PERMITIR_EXEMPLO`, solo para demostraciones). Sin las variables de una integración, esa integración queda desactivada y el resto funciona (paneles web). Los envíos a Telegram y WhatsApp pasan por una cola en segundo plano: si una API se bloquea, la atención y `/api/saude` siguen respondiendo.

## Precauciones

- Evolution no es la API oficial de WhatsApp: usa un número dedicado y no envíes mensajes masivos a quienes no te contactaron.
- Los datos de los leads quedan en tu servidor (`dados/`). La copia de seguridad contiene datos personales: guárdala con acceso restringido.

## Hoja de ruta (fuera de la v1)

Agente de voz automático · responder WhatsApp desde el panel · embudo arrastrable · CRM externo por webhook · metas y clasificación · varios números · API oficial de Meta · encuesta de satisfacción.

## Licencia

MIT. Contenido abierto y gratuito de [INEMA.CLUB](https://inema.club).