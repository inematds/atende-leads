# Decisões (só acrescentar)

| data | decisão | motivo | alternativa descartada |
|---|---|---|---|
| 2026-11-05 | Nome `atende-leads`, repo público inematds | padrão dos kits de atendimento | — |
| 2026-11-05 | Prazos: oferta 2 min, alerta 🚨 2 min quente / 5 min normal, lembrete 30 min | sugestão aceita pelo Nei ("pode fazer o projeto completo") | perguntar de novo |
| 2026-11-05 | Cérebro = regras por padrão; Ollama ou endpoint OpenAI-compatível do cliente opcionais e desligados | produto roda sozinho no cliente; regra dura de não usar API sem autorização | API fixa de um provedor |
| 2026-11-05 | WhatsApp pela Evolution na v1; Cloud API oficial no roteiro | pedido do Nei | Cloud API já na v1 |
| 2026-11-05 | Sem Chatwoot: tudo construído por nós, reaproveitando atende-clinica | pedido do Nei | Chatwoot como caixa de entrada |
| 2026-11-05 | Botão Ligar = URL para /ligar/<token> que redireciona para tel:, telefone também em texto | Telegram não aceita tel: em botão inline | botão tel: direto |
| 2026-11-05 | Grupo nunca recebe telefone nem texto do lead; dados completos só no privado | LGPD | tudo no grupo |
| 2026-11-05 | Escopo v1 completo; v2 (funil arrastável, responder pelo painel, CRM, metas) e voz automática = roteiro | evitar projeto sem fim | — |
| 2026-11-05 | Vídeo: explicavideo 16:9 no lives8 (canal dos kits de atendimento), tópico no INEMA.VIBE | pedido do Nei + padrão dos kits 19/10 | lives1 |
| 2026-11-05 | Termos das regras 5–7/produtos/FAQ casam como trecho (substring) do texto normalizado | §4 diz "contém"; leitura literal | casar só palavra inteira (perderia "parcelas") |
| 2026-11-05 | `GET /api/saida` e `GET /api/gestor/leads` devolvem array JSON no topo | §15 escreve `[{...}]`; §13 diz "→ lista" | objeto `{"mensagens": [...]}` como no atende-clinica |
| 2026-11-05 | `/api/painel` `fila[].lead` = primeiro nome do lead (string); `lead_id` vai junto como extra | §8 só nomeia o campo; o painel mostra o primeiro nome | objeto `{id,nome}` |
| 2026-11-05 | Qualquer colaborador cadastrado e não `fora` pode assumir pela API (não só o ofertado) | §7: "só o primeiro vence; os outros recebem 409" — corrida precisa dar 409, não 403 | restringir ao ofertado (daria 403) |
| 2026-11-05 | Oferta pendente de quem vira `ocupado`/`fora` fica até vencer (`oferta_min`) | §7 só prevê vencimento e Passar | re-rotear na hora |
| 2026-11-05 | Chamado aberto fora do horário: sem linha no grupo, sem oferta; na abertura do expediente manda linha + oferta (ou alerta), e `conta_desde` = início da janela | §10 "prazos de alerta contam a partir da abertura do expediente" | contar a partir da hora em que a tarefa rodou |
| 2026-11-05 | `tempo_medio_assumir_min` = 0 quando não houve assumidos no dia | §13 não define vazio | null |
| 2026-11-05 | `ra:<id>` usa o id do chamado fechado com `retornar` (um retorno por chamado) | §16 só diz `ra:<id>` | id próprio de retorno |
| 2026-11-05 | "Ordem de vez" é literal também com vários chamados: o 1º livre recebe todas as ofertas novas, mesmo já tendo uma pendente | §7 "primeiro da ordem de vez que não esteja em recusaram" | pular quem já tem oferta pendente |
| 2026-11-05 | `<nome> vai te atender agora.`, `Combinado!...` e lembretes ao lead respeitam `nao_contatar` (são automáticas); respostas do agente e do humano não | §4 regra 1 "nenhuma mensagem automática" | bloquear tudo |
| 2026-11-05 | Respostas do agente vão à caixa de saída/Evolution só quando `canal = whatsapp` (webhook ou corpo); avisos e mensagens do humano vão sempre | canal web já recebe na resposta HTTP; evita duplicar no WhatsApp | mandar tudo pelo WhatsApp |
| 2026-11-05 | Telegram "configurado" = `TELEGRAM_API_URL` + `TELEGRAM_TOKEN`; sem `TELEGRAM_GRUPO_ID` não manda ao grupo; sem `TELEGRAM_SEGREDO` o webhook responde 401 | §16 lista as 4; nenhuma URL padrão no código | exigir as 4 para tudo |
| 2026-11-05 | Primeiro contato e regra 10 respondem numa única mensagem (saudação + pergunta) | testes podem olhar `respostas[0]` ou a última | duas mensagens |
| 2026-11-05 | Abrir chamado responde `[texto com "vou chamar" (ou "fora do horário" + "vou chamar"), "Acompanhe aqui: {url}/meu/<token>"]`; preço da regra 6 entra no início do 1º texto | §4 regras 5–7 + §11 | link na mesma mensagem |
| 2026-11-05 | Fluxo `quer_falar` (regra 10/urgência 2): `sim/quero/pode` (sem "não") abre `venda`; "não" encerra com "qualquer dúvida"; outra coisa segue as regras 9–12 | §4 regra 10 | consumir qualquer resposta |
| 2026-11-05 | Qualificação: depois do nome sempre pergunta "o que procura", mesmo se o interesse já veio da regra 10 | §4 "nome → o que procura → para quando" literal | pular a etapa |
| 2026-11-05 | Na etapa do nome, saudações ("oi", "bom dia"...) não viram nome: repete a pergunta | evita lead chamado "Oi" | aceitar qualquer texto |
| 2026-11-05 | Pushname: "Posso te chamar de X?" → `sim` aceita; `não` pergunta o nome de novo; outro texto vira o nome | §15 | "não" virar nome |
| 2026-11-05 | Assumir já assumido no Telegram: `answerCallbackQuery` com `já foi assumido por <nome>` e também mensagem privada com o mesmo texto | §7 não diz qual dos dois | só o answerCallbackQuery |
| 2026-11-05 | Painel: não reedita se o texto não mudou; erro "message is not modified" conta como sucesso; outro erro → nova mensagem + pin | §8 + comportamento real do Telegram | reenviar sempre que a edição falhar |
| 2026-11-05 | Mudar para `livre`/`ocupado` com chamado `atendendo` responde 200 e mantém `atendendo` | §6 "com 1+ chamado atendendo fica atendendo" | 409 |
| 2026-11-05 | Fechamento: checa 404 → 403 (não dono) → 409 (já fechado) → 422 (corpo); [G] pode fechar chamado ainda não assumido | §9 | validar corpo antes |
| 2026-11-05 | `PUT /api/gestor/config` aceita objeto parcial: chaves ausentes ficam as atuais; valida o resultado inteiro | "grava o negocio.json inteiro" + validações listadas | exigir todas as chaves |
| 2026-11-05 | Horas gravadas como `AAAA-MM-DDTHH:MM` (minuto) em todo o estado; minutos = piso da diferença | mesmo formato de `ATENDE_AGORA` | gravar segundos |
| 2026-11-05 | Fim do expediente dispara uma vez por dia, na primeira tarefa depois do fim da última janela, só se houver chamado `atendendo` | §10 | disparar só no minuto exato |
| 2026-11-05 | Header `apikey` sai com grafia minúscula exata (http.client em vez de urllib, que capitaliza) | §15 "header `apikey`" | urllib |
| 2026-11-05 | No meio da qualificação, texto que casa o FAQ é respondido (e a etapa continua); produto citado na etapa do nome vira interesse e repete a pergunta do nome | evita tratar "qual o horário?" como nome; regra 8 literal faria isso | consumir sempre como nome/opção |
| 2026-11-05 | `/api/gestor/leads?colaborador=` casa dono atual de chamado OU colaborador gravado no histórico | transferência/reabertura apagam o dono do chamado | só dono atual |
| 2026-11-05 | `docker-compose.yml` mantém `env_file: .env` (curto, literal do §17); sem `.env` o `compose config` falha | contrato literal | `env_file: [{path: .env, required: false}]` |
