# Especificação v1 — atende-leads (contrato)

> Testes em `tests/` verificam exatamente o que está aqui. Implementação e testes são escritos a partir deste arquivo, sem combinar detalhes fora dele. Mudança de contrato = editar aqui primeiro.

## 0. O que é

Atendimento de **leads pelo WhatsApp** para um negócio (loja, imobiliária, escola, serviço). Um **agente** responde, tira dúvidas, qualifica o lead e dá uma nota. Quando o lead **pede um humano**, quando o agente **detecta necessidade** ou quando vê **chance de venda**, o sistema abre um **chamado** e oferece o lead ao **colaborador livre há mais tempo**, pelo **Telegram** (privado), com todos os dados e botões **Assumir / Passar / Ligar / WhatsApp**. Ninguém assume no prazo → **alerta 🚨 no grupo** da equipe. O colaborador **fecha** o atendimento com o resultado e volta a ficar livre.

Três interfaces web: **lead** (chat + página "meu atendimento"), **equipe** (painel do colaborador) e **gestor** (painel do negócio). Entrega em **Docker** para VPS, com a Evolution API opcional no mesmo compose.

Python 3, **somente biblioteca padrão** (sem `pip install`), estado em SQLite.

## 1. Execução

- Ponto de entrada: arquivo executável `./atende` na raiz.
- `./atende serve --porta N --dados DIR [--host H]`
  - `--porta 0` = porta livre. A **primeira linha** do stdout é `PORTA=<n>` (flush), impressa quando já aceita conexões.
  - Host padrão `127.0.0.1` (Docker passa `0.0.0.0` pelo comando, nunca no código).
  - `DIR/negocio.json` = configuração (seção 2). Se não existir, copiar `exemplos/negocio.json`.
  - Todo o estado persiste em `DIR/leads.db`. Reiniciar com o mesmo `DIR` mantém tudo.
- **Relógio:** `ATENDE_AGORA` (`AAAA-MM-DDTHH:MM`, hora local) fixa o "agora" no início do processo. `POST /api/relogio {"agora": "AAAA-MM-DDTHH:MM"}` [G] muda o relógio em execução **somente se** `ATENDE_AGORA` estava definida no início (senão 403). Sem ela, relógio real.
- **Tarefas de tempo** (ofertas vencidas, alertas, lembretes, retornos, abertura do expediente): `POST /api/tarefas/rodar` [G] roda uma vez e devolve `{"ok": true, "acoes": n}`. Fora do modo `ATENDE_AGORA`, o servidor também roda isso sozinho a cada 30 s.
- `./atende backup --dados DIR --saida ARQ` (cópia consistente do SQLite + `negocio.json` num `.tar.gz`) e `./atende restaurar --dados DIR --arquivo ARQ`.
- Integrações externas **só** por variáveis de ambiente (seções 15–17). Sem elas, nenhuma chamada de rede sai do processo. Nenhuma URL, chave ou token real no código.

## 2. `negocio.json`

```json
{
  "nome": "Loja Exemplo",
  "token_gestor": "TROQUE-ESTE-TOKEN",
  "url_publica": "http://localhost:8080",
  "horarios": { "seg": [["08:00","18:00"]], "ter": [["08:00","18:00"]], "qua": [["08:00","18:00"]],
                "qui": [["08:00","18:00"]], "sex": [["08:00","18:00"]], "sab": [["09:00","13:00"]], "dom": [] },
  "prazos": { "oferta_min": 2, "alerta_quente_min": 2, "alerta_normal_min": 5, "lembrete_min": 30 },
  "equipe": [ { "id": "ana", "nome": "Ana", "telefone": "5541999990010", "codigo": "ana-1234" } ],
  "produtos": [ { "id": "plano-anual", "nome": "Plano anual", "palavras": ["anual", "plano anual"], "preco": "R$ 1.200" } ],
  "faq": [ { "id": "horario", "perguntas": ["qual o horario de atendimento"], "resposta": "Atendemos de segunda a sexta, das 8h às 18h." } ],
  "cerebro": { "tipo": "regras" }
}
```

- `codigo`: senha pessoal do colaborador no painel da equipe e no `/entrar` do Telegram. Únicos.
- `preco` é opcional; o agente só fala preço que estiver aqui.
- `cerebro.tipo`: `regras` (padrão) | `ollama` | `openai` (seção 14).
- Todos os textos de "nome" podem ter acento; telefones são só dígitos.

## 3. Autenticação

- **[G] gestor:** header `X-Token` = `token_gestor`. Errado/ausente → 401.
- **[E] equipe:** header `X-Codigo` = `codigo` de um colaborador → age como esse colaborador. Errado → 401. [G] também passa nas rotas [E] informando `"colaborador": "<id>"` no corpo quando precisa.
- **Lead:** página `/meu/<token_lead>` e rotas `/api/meu/<token_lead>...`; token aleatório ≥ 16 caracteres gerado na criação do lead. Token inexistente → 404.
- Públicas: `/`, `/widget.js`, `/equipe`, `/gestor` (páginas; os dados vêm de rotas protegidas), `/api/saude`, `POST /api/mensagens`, `/ligar/<token_chamado>`.
- Webhooks com segredo próprio (seções 15–16).

## 4. Lead e conversa (`POST /api/mensagens`)

Corpo: `{"telefone": "...", "texto": "...", "nome": "opcional", "canal": "web|whatsapp"}`. Telefone normalizado: só dígitos; com 10 ou 11 dígitos ganha `55` na frente; resultado com menos de 12 ou mais de 13 dígitos → 422. Resposta: `{"lead": {id, token, status, nota}, "respostas": ["..."]}` (lista de textos que o agente manda ao lead, na ordem; pode ser vazia).

Lead criado no primeiro contato com `status: "novo"`, `nota: "frio"`. O texto é **normalizado** (minúsculas, sem acento, sem pontuação) para decidir. Ordem de decisão:

1. **Parar** — texto igual a `parar`, `sair` ou `pare`: lead `nao_contatar = true`; resposta contém `não vai mais receber`. Nenhuma mensagem automática (retorno, aviso de prazo) vai mais para ele. Mensagens novas dele continuam sendo recebidas (e tiram o `nao_contatar`, com resposta normal a partir daí).
2. **Apagar** — texto igual a `apagar meus dados`: anonimiza o lead (nome → `apagado`, telefone → `apagado-<id>`, mensagens e notas apagadas, chamados mantidos só com resultado e valores); resposta contém `apagados`.
3. **Em atendimento humano** — se o lead tem chamado `atendendo`: o agente **não responde** (`respostas: []`); a mensagem vai ao colaborador dono, no privado do Telegram, como `💬 <nome ou telefone>: <texto>` (seção 16).
4. **Chamado aguardando** (`aguardando` ou `alerta`): o agente não abre outro; responde texto que contém `já avisei` e a mensagem entra no histórico do chamado.
5. **Pediu humano** — contém `atendente`, `humano`, `falar com alguem`, `falar com uma pessoa`, `vendedor`, `me liga`, `me ligue` ou `ligacao`: abre chamado `motivo: "pediu_humano"`. Resposta contém `vou chamar`.
6. **Chance de venda** — contém `quero comprar`, `quero contratar`, `como faco para comprar`, `como faco para contratar`, `fechar`, `quanto custa`, `qual o valor`, `qual o preco`, `forma de pagamento`, `parcela`, `orcamento`: o lead fica `nota: "quente"`. Se casar um produto (seção 5) com `preco`, a resposta inclui o preço (`<nome>: <preco>`). Abre chamado `motivo: "venda"`. Resposta contém `vou chamar`.
7. **Necessidade** — contém `reclamacao`, `reclamar`, `problema`, `nao funciona`, `defeito`, `cancelar`, `reembolso`, `absurdo`, `pessimo`, `procon`: abre chamado `motivo: "precisa"`. Resposta contém `vou chamar`.
8. **Qualificação em andamento** consome a mensagem (abaixo).
9. **FAQ** — palavras significativas (≥ 3 letras, fora de artigos/preposições/pronomes comuns) de alguma pergunta: se ≥ 60 % aparecem no texto, responde **exatamente** a `resposta` (uma mensagem). Mais de um casa → maior %; empate → primeiro.
10. **Interesse em produto** — casa algum produto (seção 5): lead `nota: "morno"` (se não for `quente`), `interesse = <id do produto>`; se o lead ainda não tem nome, inicia a qualificação; senão responde texto que contém o nome do produto e pergunta `Quer que eu chame alguém para te atender?`; um `sim`/`quero`/`pode` na mensagem seguinte abre chamado `motivo: "venda"`.
11. **Primeiro contato** sem nada casado → saudação com o nome do negócio e inicia a qualificação.
12. **Não entendi** — resposta contém `não entendi` e oferece `atendente`. Na **segunda seguida** sem entender, abre chamado `motivo: "precisa"`.

**Qualificação** (estado por lead, persistido): pergunta o **nome** (resposta contém `nome`) se o lead não tem nome → depois **o que procura** (lista os produtos numerados `1 - <nome>`, e `0 - Outro assunto`) → depois **para quando** (`1 - Hoje / esta semana`, `2 - Este mês`, `3 - Só pesquisando`). Ao fim: urgência 1 → `quente` e abre chamado `venda`; 2 → `morno`, resposta pergunta se quer falar com alguém (como na regra 10); 3 → `frio`, resposta contém `qualquer dúvida` e não abre chamado. Número inválido repete as opções. As regras 1–7 valem também no meio da qualificação.

- Abrir chamado não depende de qualificação completa: os dados que houver vão no aviso.
- Se o lead mandou `nome` no corpo e ainda não tem nome, usa esse.
- O agente **nunca** inventa preço, prazo de entrega ou condição: só o que está em `negocio.json`.
- **Status do lead:** `novo` → `em_atendimento` (chamado assumido) → `negociando` | `retornar` | `ganho` | `perdido` | `invalido` (pelo fechamento, seção 9). Lead com chamado aberto e ainda não assumido continua no status anterior.

## 5. Produtos

Um produto casa se alguma de suas `palavras` (normalizada) aparece no texto normalizado, ou se o nome normalizado aparece. Mais de um → o primeiro na ordem do `negocio.json`.

## 6. Equipe e status

- Status do colaborador: `livre` | `ocupado` | `fora` | `atendendo`. Começa `fora`.
- `livre_desde`: momento em que ficou `livre` pela última vez. **Ordem de vez** = livres ordenados por `livre_desde` crescente (empate: ordem do `negocio.json`).
- O colaborador muda para `livre`, `ocupado` ou `fora` pelo painel, pelo Telegram (botões ou `/livre`, `/ocupado`, `/fora`) ou o gestor muda por ele. `atendendo` só vem de assumir chamado.
- Colaborador com 1+ chamado `atendendo` fica `atendendo`. Ao fechar o último, volta a `livre` com `livre_desde = agora` (fim da fila).
- Mudar para `fora` com chamados `atendendo` → 409.

## 7. Chamados e roteamento

Chamado: `{id, lead_id, motivo: pediu_humano|venda|precisa, prioridade: quente|normal, status: aguardando|alerta|atendendo|fechado, ofertado_a, recusaram: [], dono, aberto_em, assumido_em, fechado_em, resultado}`. Prioridade `quente` se `motivo = venda` ou lead `quente`; senão `normal`.

- **Abrir:** no horário de atendimento (seção 10). Grava o chamado `aguardando` e:
  1. manda ao **grupo** uma linha curta: começa com `🔥` (quente) ou `🙋` (normal), contém `#<id>`, o primeiro nome do lead (ou `lead`), o motivo legível (`pediu humano` / `chance de venda` / `precisa de atenção`) e, se ofertado, `→ <nome do colaborador>`. **Sem telefone** no grupo.
  2. **oferta** ao primeiro da ordem de vez que não esteja em `recusaram`: mensagem **privada** (seção 16) com `#<id>`, nome, telefone formatado `+55 (41) 99999-0001`, nota, motivo, interesse (nome do produto), resumo (seção 14) e as últimas 5 mensagens do lead; botões **✅ Assumir**, **↪️ Passar**, **📞 Ligar**, **💬 WhatsApp**. `ofertado_a = <id>`, `ofertado_em = agora`.
  3. ninguém livre → nenhuma oferta; vai direto ao **alerta** (abaixo).
- **Oferta vencida:** passados `prazos.oferta_min` desde `ofertado_em` sem assumir → conta como recusa e oferece ao próximo (mesma mensagem). O aviso antigo é editado para `⌛ #<id> passou para o próximo` (sem botões).
- **Passar:** o ofertado toca **↪️ Passar** → recusa imediata, vai ao próximo.
- **Alerta 🚨:** chamado ainda não assumido depois de `alerta_quente_min` (quente) ou `alerta_normal_min` (normal) contados de `aberto_em`, **ou** sem ninguém livre que ainda não recusou → status `alerta` e mensagem ao **grupo** começando com `🚨`, contendo `#<id>`, nome, motivo, nota, interesse e há quantos minutos espera, com botão **✅ Assumir** (qualquer colaborador cadastrado). Telefone **não** vai no grupo. Um alerta por chamado; enquanto em `alerta` continua oferecendo a quem ficar livre.
- **Assumir** (botão no privado, botão do alerta, painel da equipe ou gestor transferindo): atômico — só o primeiro vence; os outros recebem 409 na API e no Telegram a resposta `já foi assumido por <nome>`. Ao assumir: `status: atendendo`, `dono`, `assumido_em`; colaborador `atendendo`; lead `em_atendimento`; mensagens do grupo do chamado (linha e alerta) editadas para `✅ <nome> assumiu #<id>` (sem botões); o dono recebe no privado o **cartão do atendimento** com os botões de fechamento (seção 9); o lead recebe `<nome do colaborador> vai te atender agora.` Colaborador `fora` não pode assumir (409); `ocupado` pode (vira `atendendo`).
- **Lead que volta:** se o lead teve chamado fechado nos últimos 30 dias com dono, a oferta do novo chamado vai **primeiro** a esse dono se ele estiver `livre`; senão segue a ordem de vez.
- **Mensagens do dono ao lead:** no privado, responder (reply) ao cartão ou a uma mensagem `💬` do lead → o texto vai ao lead (WhatsApp/caixa de saída `tipo: "humano"`). Também `POST /api/equipe/chamados/{id}/responder {texto}` [E].
- **Ligar:** `GET /ligar/<token_chamado>` → página HTML mínima que redireciona para `tel:+<telefone>` (meta refresh + link visível). O botão 📞 do Telegram é um botão de URL para `{url_publica}/ligar/<token_chamado>`. O telefone também vai em texto na mensagem. `token_chamado` aleatório ≥ 16; inexistente → 404.
- **WhatsApp:** botão de URL `https://wa.me/<telefone>`.

## 8. Painel fixo no grupo

- Uma mensagem no grupo com o título `EQUIPE AGORA`, a hora (`HH:MM`), uma linha por colaborador (`🟢 <nome> livre há N min`, a primeira da ordem de vez com `(próxima da vez)`; `🟡 <nome> atendendo <primeiro nome do lead> · N min`; `🔴 <nome> ocupado`; `⚫ <nome> fora`) e a seção `FILA` com os chamados `aguardando`/`alerta` (`🔥`/`🙋` `<primeiro nome> · esperando N min`, e `⚠️ sem dono` se em alerta).
- Criada na primeira mudança (status, chamado). Depois é **editada** (`editMessageText`) em cada mudança, nunca reenviada; se a edição falhar com erro do Telegram, envia uma nova e guarda o novo `message_id`. Tenta fixar (`pinChatMessage`) ao criar; falha ao fixar é ignorada.
- `/status` no grupo ou no privado → o bot manda o mesmo texto (mensagem nova).
- `GET /api/painel` [G] ou [E] → `{"equipe": [{id, nome, status, livre_desde, minutos, proximo}], "fila": [{id, lead, prioridade, status, minutos, ofertado_a}]}`.

## 9. Fechamento

`POST /api/equipe/chamados/{id}/fechar` [E] (só o dono; [G] pode fechar qualquer) com:
```json
{"resultado": "vendeu|retornar|negociando|sem_interesse|invalido",
 "valor": 1200.0, "produto": "plano-anual", "retornar_em": "AAAA-MM-DDTHH:MM",
 "motivo": "preco|ja_comprou|curioso|outro|numero_errado|spam|nao_e_lead", "nota": "texto livre"}
```
- Obrigatórios por resultado: `vendeu` → `valor` (≥ 0); `retornar` → `retornar_em` (no futuro); `sem_interesse` e `invalido` → `motivo` (valores da lista acima, `numero_errado|spam|nao_e_lead` só para `invalido`, os outros só para `sem_interesse`). Faltou/errado → 422. Não é dono → 403. Já fechado → 409.
- Efeito: chamado `fechado` com `resultado`; lead `status`: vendeu → `ganho`, retornar → `retornar`, negociando → `negociando`, sem_interesse → `perdido`, invalido → `invalido`. Colaborador volta a `livre` (seção 6) se não tiver outro chamado. Grava no **histórico do lead** um evento `{em, colaborador, resultado, valor, produto, motivo, nota, minutos_ate_assumir, minutos_atendimento}`.
- **Retorno:** `retornar` agenda; em `retornar_em` (tarefa de tempo) o mesmo colaborador recebe no privado `📅 Retorno: <nome> +55 (...)` com os botões Ligar/WhatsApp e um botão **✅ Assumir** que reabre um chamado `motivo: "venda"` já assumido por ele.
- **Pelo Telegram** (cartão do atendimento): botões `✅ Vendeu`, `📅 Retornar`, `🤔 Negociando`, `❌ Sem interesse`, `🚫 Inválido`, `↩️ Devolver ao bot`. Cada um conduz as perguntas pelo próprio bot no privado (botões para motivo e data — `Amanhã 09:00`, `Em 3 dias 09:00`, `Semana que vem 09:00` —, texto para valor e nota; a nota é opcional, botão `Pular`). Ao final chama o mesmo fechamento.
- **Áudio como nota:** mensagem de voz no privado durante o fechamento → se `WHISPER_CMD` estiver definida (comando local que recebe o caminho do arquivo e imprime o texto), transcreve e usa como nota; senão guarda `"[áudio]"` como nota. Nunca chama API externa para isso.
- **Devolver ao bot:** `POST /api/equipe/chamados/{id}/devolver` [E] → chamado `fechado` com `resultado: "devolvido"`, lead volta ao agente (status anterior a `em_atendimento`), colaborador livre como no fechamento.
- **Mensagem ao lead após fechar:** só em `retornar`: `Combinado! Vamos te procurar em DD/MM às HH:MM.`

## 10. Horário, fora do horário e lembretes

- Horário de atendimento = `horarios` do `negocio.json` (dias `seg ter qua qui sex sab dom`, janelas `[ini, fim)`).
- Fora do horário, um chamado é aberto em `aguardando` mas **não** é ofertado nem gera alerta; o lead recebe texto contendo `fora do horário` e o próximo início (`DD/MM às HH:MM`). Na abertura do expediente (tarefa de tempo), os chamados aguardando são ofertados na ordem em que foram abertos, e os prazos de alerta contam a partir da abertura do expediente.
- **Lembrete de atendimento parado:** chamado `atendendo` sem mensagem nova (do lead ou do dono) há `lembrete_min` → o dono recebe `Ainda com <nome>?` com botões **Sim, continuo** (zera a contagem) e **Terminei** (abre o fechamento). Um lembrete por período parado.
- **Fim do expediente:** no fim da última janela do dia (tarefa de tempo), cada dono com chamado `atendendo` recebe `Fim do expediente: feche seus atendimentos`, e o grupo recebe a lista dos ainda abertos.

## 11. Interface do lead

- `GET /` → chat web (a mesma conversa da seção 4, telefone e nome pedidos na tela), estilo INEMA.
- `GET /widget.js` → script que coloca uma bolha de chat em qualquer site e abre o chat num iframe para `{url_publica}/?widget=1`.
- `GET /meu/<token_lead>` → página "meu atendimento": nome do negócio, status do lead em texto (`Recebemos sua mensagem`, `Alguém da equipe vai falar com você`, `<nome> está te atendendo`, `Retorno marcado para DD/MM às HH:MM`, ...), nome do colaborador se houver, botão **Quero falar agora** e botão **Apagar meus dados**.
- `GET /api/meu/<token_lead>` → `{nome, status, colaborador, retornar_em}`. `POST /api/meu/<token_lead>/falar` → abre chamado `pediu_humano` (mesmas regras da seção 4 regra 4/5). `POST /api/meu/<token_lead>/apagar` → igual à regra 2.
- O link `/meu/<token>` é enviado ao lead quando abre chamado (`Acompanhe aqui: {url_publica}/meu/<token>`).

## 12. Painel da equipe (`/equipe`, rotas [E])

- `GET /api/equipe/eu` → `{id, nome, status, chamados: [abertos dele], retornos_hoje: [...]}`.
- `POST /api/equipe/status {"status": "livre|ocupado|fora"}`.
- `POST /api/equipe/chamados/{id}/assumir` · `/passar` · `/responder` · `/fechar` · `/devolver`.
- `GET /api/equipe/leads/{id}` → ficha: lead, mensagens, chamados, histórico. Colaborador só vê leads de chamados ofertados a ele, dele, ou em alerta; senão 403.
- Página `/equipe`: entra com o código (guardado só na memória da aba), mostra status com botões, chamados abertos, retornos de hoje, ficha com as mensagens e o formulário de fechamento.

## 13. Painel do gestor (`/gestor`, rotas [G])

- `GET /api/gestor/ao-vivo` → igual a `/api/painel` + alertas abertos.
- `GET /api/gestor/hoje` → `{leads_novos, chamados_abertos, assumidos, vendas, valor_vendido, tempo_medio_assumir_min, por_colaborador: [{id, nome, assumidos, vendas, valor}]}` do dia do relógio.
- `GET /api/gestor/leads?status=&colaborador=&de=&ate=` → lista. `GET /api/gestor/leads/{id}` → ficha completa.
- `POST /api/gestor/chamados/{id}/transferir {"colaborador": "<id>"}` → o chamado (aberto, assumido ou não) passa a ser do colaborador, como se ele tivesse assumido; o antigo dono volta a livre se ficar sem chamados. `POST /api/gestor/chamados/{id}/reabrir` → chamado fechado volta a `aguardando` (novo roteamento). `POST /api/gestor/equipe/{id}/status`.
- `GET /api/gestor/config` / `PUT /api/gestor/config` → lê e grava o `negocio.json` inteiro (valida: ids únicos, códigos únicos, horários `HH:MM`, prazos inteiros ≥ 1; inválido → 422 e nada muda). `token_gestor` nunca é devolvido no GET (vem `"***"`; `***` no PUT mantém o atual).
- `GET /api/gestor/exportar.csv` → CSV UTF-8 com cabeçalho `lead_id,nome,telefone,status,nota,interesse,colaborador,resultado,valor,criado_em,ultimo_contato`.
- Página `/gestor`: entra com o token; abas Ao vivo, Hoje, Leads, Cadastros (equipe, produtos, FAQ, horários, prazos), Exportar.

## 14. Cérebro do agente

- `regras` (padrão): tudo da seção 4. **Resumo** do chamado = até 3 linhas montadas por regra: `Quer: <produto ou assunto>`, `Urgência: <hoje/este mês/pesquisando>` (se respondeu), `Disse: "<última mensagem, até 120 caracteres>"`.
- `ollama` (`{"tipo": "ollama", "url": "...", "modelo": "..."}`) e `openai` (qualquer endpoint compatível com `/v1/chat/completions`; chave em `CEREBRO_API_KEY`, nunca no JSON): usados **só** para (a) escrever o resumo e (b) responder dúvidas que caíram em "não entendi", usando FAQ e produtos como base, com instrução de não inventar preço/prazo. Timeout de 15 s; erro, timeout ou resposta vazia → cai na regra. As decisões de abrir chamado continuam sendo as da seção 4 (podem ser acrescidas por uma classificação do cérebro com saída `pediu_humano|venda|precisa|nada`).
- Os testes rodam com `regras` e com um servidor falso local; nenhum teste chama serviço real.

## 15. WhatsApp pela Evolution API

Variáveis: `EVOLUTION_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCIA`, `WEBHOOK_SEGREDO`. Sem `EVOLUTION_URL` → canal simulado (só caixa de saída, `status: "simulado"`).

- **Entrada** `POST /webhook/evolution/{WEBHOOK_SEGREDO}` (segredo errado → 404). Formato Evolution v2: `{"event": "messages.upsert", "instance": "...", "data": {"key": {"remoteJid": "5541999990001@s.whatsapp.net", "fromMe": false, "id": "ABC"}, "pushName": "Maria", "message": {"conversation": "oi"}, "messageType": "conversation"}}`. Sempre 200. Ignora: outro `event`, `fromMe: true`, grupo (`@g.us`), `key.id` repetido. Texto = `message.conversation` ou `message.extendedTextMessage.text`; sem texto → responde `Por enquanto só consigo ler mensagens de texto.` `pushName` vira nome sugerido (usado como `nome` só se o lead não tiver nome **e** depois de confirmar na qualificação — a pergunta do nome passa a ser `Posso te chamar de <pushName>?`; `sim` aceita, outra resposta vira o nome).
- **Saída:** `POST {EVOLUTION_URL}/message/sendText/{EVOLUTION_INSTANCIA}`, header `apikey`, corpo `{"number": "<dígitos>", "text": "..."}`, na ordem.
- `GET /api/saida` [G] → caixa de saída `[{id, telefone, texto, tipo: agente|humano|aviso, status: enviado|pendente|simulado, em}]`. `pendente` (erro HTTP/conexão) é reenviado pela tarefa de tempo.

## 16. Telegram

Variáveis: `TELEGRAM_API_URL` (ex.: `https://api.telegram.org`), `TELEGRAM_TOKEN`, `TELEGRAM_GRUPO_ID`, `TELEGRAM_SEGREDO`. Sem elas, nada vai ao Telegram e o resto funciona (painéis web).

- Chamadas: `POST {TELEGRAM_API_URL}/bot{TOKEN}/<método>` com JSON: `sendMessage` (`chat_id`, `text`, opcional `reply_markup.inline_keyboard`, `reply_to_message_id`), `editMessageText` (`chat_id`, `message_id`, `text`, `reply_markup`), `answerCallbackQuery` (`callback_query_id`, `text`), `pinChatMessage`, `getFile` (áudio).
- `POST /webhook/telegram` exige header `X-Telegram-Bot-Api-Secret-Token: {TELEGRAM_SEGREDO}` (senão 401). Sempre 200 com segredo certo.
- **Vínculo:** no privado, `/entrar <codigo>` liga o `from.id` do Telegram ao colaborador (responde `Olá, <nome>!` e mostra os botões de status `🟢 Livre` / `🔴 Ocupado` / `⚫ Fora`). Código errado → `Código inválido.` Mensagens e botões de quem não está vinculado → `Envie /entrar <seu código>.` O vínculo persiste. Mensagens privadas vão ao `chat_id` = `from.id` vinculado; colaborador sem vínculo não recebe ofertas (é pulado na ordem de vez, sem contar como recusa) — exceto se o Telegram não estiver configurado, quando a oferta fica só no painel web.
- **Botões** (`callback_data`, até 64 bytes): `as:<id>` assumir, `pa:<id>` passar, `st:livre|ocupado|fora`, `fe:<id>:<resultado>` fechamento, `fm:<id>:<motivo>` motivo, `fr:<id>:<1|3|7>` retorno em N dias às 09:00, `fp:<id>` pular nota, `dv:<id>` devolver, `lc:<id>` continuo, `lt:<id>` terminei, `ra:<id>` assumir retorno. Toda `callback_query` recebe `answerCallbackQuery`.
- **Comandos** (privado do vinculado): `/livre`, `/ocupado`, `/fora`, `/status`, `/meus` (chamados dele), `/retornos` (retornos de hoje), `/lead <nome ou telefone>` (ficha curta, só de leads que ele pode ver), `/fechar <id> vendeu <valor>` | `/fechar <id> retornar <AAAA-MM-DDTHH:MM>` | `/fechar <id> negociando` | `/fechar <id> sem <motivo>` | `/fechar <id> invalido <motivo>`. No grupo: só `/status`.
- **Privacidade:** no grupo, nunca telefone nem texto das mensagens do lead; só primeiro nome, motivo, nota, interesse e tempos.

## 17. Docker / VPS

- `Dockerfile` (`python:3-slim` ou similar, sem `pip install`) rodando `./atende serve --host 0.0.0.0 --porta 8080 --dados /dados`, com `HEALTHCHECK` em `/api/saude`.
- `docker-compose.yml`: serviço `atende` (`build: .`, `restart: unless-stopped`, `env_file: .env`, volume `./dados:/dados`, porta `127.0.0.1:8080:8080`). Perfil `evolution` (`docker compose --profile evolution up -d`) com a Evolution API v2 e o que ela exige na versão atual (banco e cache), na mesma rede, porta só em `127.0.0.1`.
- `.env.exemplo` com todas as variáveis das seções 14–16 (exemplos, nenhum segredo real).
- `instalar-vps.sh`: confere Docker, pergunta nome do negócio, domínio, token do Telegram e grupo, gera segredos aleatórios, escreve `.env` e `dados/negocio.json`, sobe o compose (com ou sem Evolution) e imprime os próximos passos (proxy HTTPS, webhook da Evolution, `setWebhook` do Telegram, cron do backup). `--sem-perguntas` usa variáveis de ambiente (para teste).
- README com **Deploy na VPS** e **O processo, do início ao fim**.

## 18. Saúde

`GET /api/saude` → `{"ok": true, "versao": "<VERSION>", "evolution": bool, "telegram": bool, "cerebro": "regras|ollama|openai"}`.

## 19. Fora do v1 (roteiro)

Agente de voz automático; responder o WhatsApp pelo painel web; funil arrastável; CRM externo por webhook; metas e ranking; vários números de WhatsApp; API oficial da Meta (Cloud API); pesquisa de satisfação.
