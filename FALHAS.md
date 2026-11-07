# Falhas (uma linha por falha, mais recente no topo)

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-11-07 | 1.9.8 (antes de publicar): métrica "robô interagindo" contava frase pronta e silêncio como conversa | frases prontas fora; três faixas (sem resposta, robô, silêncio); pedido de abertura não conta | prompt |
| 2026-11-07 | Cadastros → "+ Produto" (e remover) quebrava com `palavras.join is not a function` depois de ler o formulário | aceitar palavras como texto ou lista ao redesenhar a linha | prompt |
| 2026-11-07 | Ao vivo 1.8.8 (antes de publicar): atendimento assumido sem nenhuma resposta aparecia como "respondido" | sem resposta da equipe no chamado → contar do assumir; teste com cliente calado | prompt |
| 2026-11-06 | "que hora tem atendimento humano?" abria chamado `pediu_humano` em vez de dizer o horário | detector de pergunta de horário (sem verbo de pedido) antes das regras 5–7 | prompt |
| 2026-11-05 | Evolution guardava cópia das mensagens/contatos no Postgres (fora do "apagar meus dados") | `DATABASE_SAVE_*` = `false` no compose, exceto INSTANCE | infra |
| 2026-11-05 | instalar-vps.sh com uid ≠ 1000 subia com `dados/` 0700 de outro dono (container sem acesso) | `sudo -n chown`; se `dados/` não for do uid 1000, abortar antes de subir | infra |
| 2026-11-05 | instalar-vps.sh rodado de novo trocava todos os segredos (Evolution sem autenticar no Postgres, webhook do Telegram 401) | reaproveitar do `.env` os segredos que já existem; gerar só os que faltam | infra |
