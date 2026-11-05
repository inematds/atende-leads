# atende-leads

**🇧🇷 [Português](README.md) · 🇺🇸 [English](README.en.md) · 🇪🇸 [Español](README.es.md)**

## 📖 Guia de uso

Guia completo (landing + passo a passo): **https://inematds.github.io/atende-leads/guia/**

Atendimento de **leads pelo WhatsApp** com um agente que responde, qualifica e passa o lead para o **colaborador livre** pelo Telegram, com todos os dados e um botão para ligar. Python 3 só com biblioteca padrão, estado em SQLite, Docker para VPS. Código aberto, versão `1.0.0`.

## O que faz

- **Agente no WhatsApp** (Evolution API): responde o FAQ, mostra preço só do que está cadastrado, qualifica (nome → o que procura → para quando) e dá a nota do lead (quente / morno / frio).
- **Chama um humano em 3 casos:** o lead pede, o agente percebe que precisa (reclamação, problema, 2× "não entendi") ou vê **chance de venda** (preço, "quero comprar", pagamento).
- **Oferece ao colaborador livre há mais tempo**, no privado do Telegram: nome, telefone, nota, interesse, resumo e últimas mensagens, com os botões **✅ Assumir · ↪️ Passar · 📞 Ligar · 💬 WhatsApp**.
- **Sem resposta em 2 min** → passa ao próximo. Lead quente sem dono em 2 min (normal em 5) ou ninguém livre → **alerta 🚨 no grupo**, e o primeiro que tocar em Assumir leva.
- **Painel fixo no grupo** (`EQUIPE AGORA`): quem está livre, atendendo, ocupado ou fora, e a fila de leads esperando. Editado a cada mudança.
- **Fechamento** pelos botões: Vendeu (valor) · Retornar (data) · Negociando · Sem interesse (motivo) · Inválido, com nota em texto ou áudio (transcrição local opcional). O colaborador volta ao fim da fila de livres.
- **Retornos agendados**, lembrete de atendimento parado (30 min), aviso de fim do expediente, fora do horário com o próximo início.
- **Três interfaces web:** lead (chat, bolha para o site e página "meu atendimento"), equipe (`/equipe`) e gestor (`/gestor`: ao vivo, hoje, leads, cadastros, CSV).
- **LGPD:** `PARAR`, `apagar meus dados`, e o grupo nunca recebe telefone nem texto do lead.
- **Cérebro:** regras por padrão (sem custo, sem API). Opcional: Ollama local ou um endpoint compatível com OpenAI configurado pelo próprio negócio, com volta automática às regras se falhar.

Contrato completo: [`docs/ESPECIFICACAO.md`](docs/ESPECIFICACAO.md).

## O processo, do início ao fim

Quem faz: 🧠 o dono/gestor · ⚙️ o sistema · 🤖 o agente.

1. 🧠 **Instalar na VPS:** `./instalar-vps.sh` (pergunta nome, domínio, Telegram; gera segredos, `.env` e `dados/negocio.json`; sobe o Docker).
2. 🧠 **Conectar o WhatsApp:** abrir o painel da Evolution e ler o QR Code com o número do atendimento (use um número só para isso).
3. 🧠 **Cadastrar** em `/gestor` → Cadastros: equipe (nome, telefone, código), produtos com palavras e preço, FAQ, horários e prazos.
4. 🧠 **Equipe entra no bot:** cada colaborador manda `/entrar <código>` no privado do bot e toca 🟢 Livre.
5. ⚙️ **Lead chega** pelo WhatsApp ou pela bolha do site.
6. 🤖 **Agente atende:** FAQ, preço cadastrado, qualificação e nota.
7. ⚙️ **Gatilho** (pediu humano / precisa / chance de venda) → abre o chamado e manda a linha curta ao grupo.
8. ⚙️ **Oferta** ao livre há mais tempo, no privado, com dados e botões; 2 min sem resposta → próximo.
9. ⚙️ **Alerta 🚨** no grupo quando estoura o prazo ou não há ninguém livre.
10. 🧠 **Colaborador assume**, liga (📞) ou responde pelo WhatsApp (💬) ou em resposta no próprio bot.
11. 🧠 **Fecha** com o resultado; ⚙️ grava o histórico, agenda o retorno e devolve o colaborador à fila.
12. 🧠 **Gestor acompanha** em `/gestor` (ao vivo, hoje, leads, exportar CSV).
13. ⚙️ **Backup diário** pelo cron: `./atende backup --dados dados --saida backups/leads-$(date +%F).tar.gz`.

## Rodar local

```bash
./atende serve --porta 8080 --dados dados
# chat do lead: http://localhost:8080/   equipe: /equipe   gestor: /gestor (token em dados/negocio.json)
python3 -m pytest -q tests/        # contrato (257 testes; build Docker só com TESTAR_DOCKER=1)
```

Relógio fixo para testar: `ATENDE_AGORA=2026-11-09T10:00 ./atende serve ...` e `POST /api/tarefas/rodar`.

## Deploy na VPS

1. **Subir:** `./instalar-vps.sh` (ou `docker compose up -d`; com a Evolution no mesmo servidor: `docker compose --profile evolution up -d`). A aplicação escuta só em `127.0.0.1:8080` e a Evolution em `127.0.0.1:8081`.
2. **HTTPS:** proxy reverso (Caddy ou Nginx) do seu domínio para `127.0.0.1:8080`. Ex. Caddy: `leads.seudominio.com { reverse_proxy 127.0.0.1:8080 }`. Ajuste `url_publica` no `negocio.json`.
3. **Webhook da Evolution:** evento `MESSAGES_UPSERT` para `https://<domínio>/webhook/evolution/<WEBHOOK_SEGREDO>` (com o perfil `evolution` o compose já aponta pela rede interna).
4. **Webhook do Telegram:** crie o bot no @BotFather, ponha no grupo da equipe como admin (para fixar o painel) e registre:
   `curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<domínio>/webhook/telegram&secret_token=<TELEGRAM_SEGREDO>"`
5. **Backup diário** no cron: `0 3 * * * cd /opt/atende-leads && ./atende backup --dados dados --saida backups/leads-$(date +\%F).tar.gz`.
6. **Restaurar:** `./atende restaurar --dados dados --arquivo backups/leads-AAAA-MM-DD.tar.gz`.

Variáveis em [`.env.exemplo`](.env.exemplo). Sem as de uma integração, ela fica desligada e o resto funciona (painéis web).

## Cuidados

- A Evolution não é a API oficial do WhatsApp: use um número dedicado e não faça disparo em massa para quem não falou com você.
- Os dados de leads ficam no seu servidor (`dados/`). O backup contém dados pessoais: guarde com acesso restrito.

## Roteiro (fora da v1)

Agente de voz automático · responder o WhatsApp pelo painel · funil arrastável · CRM externo por webhook · metas e ranking · vários números · API oficial da Meta · pesquisa de satisfação.

## Licença

MIT. Conteúdo aberto e gratuito do [INEMA.CLUB](https://inema.club).
