# Falhas (uma linha por falha, mais recente no topo)

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-11-07 | 1.10.8 (antes de publicar): a IA podia prometer "vou chamar alguém" no chamado calado | uma linha no prompt do cérebro proibindo prometer contato | prompt |
| 2026-11-07 | 1.10.8: ficha dizia "cliente não sabe" depois de ele receber "X vai te atender" | limpar `silencioso` ao avisar o lead (assumir/transferir) | prompt |
| 2026-11-07 | 1.10.8: "obrigado" + "ok" viravam duas falhas e o robô avisava a equipe | resposta própria para agradecimento/confirmação (regra 8a) | prompt |
| 2026-11-07 | 1.10.8: página /meu mostrava "alguém vai falar com você" no chamado calado | ignorar chamado silencioso no status do lead | prompt |
| 2026-11-07 | 1.10.8: "só pesquisando" deixava o chamado calado na fila, cobrando a equipe | fechar como `devolvido` se ninguém assumiu | prompt |
| 2026-11-07 | 1.10.8: venda de lead morno ganhava prioridade/🔥 de quente; tela e Telegram discordavam | prioridade segue a nota do lead | prompt |
| 2026-11-07 | 1.10.8: PUT da config (outra aba, sem versão) desfazia cadastro aprovado | `_versao` da equipe obrigatória quando a equipe muda; Base/Aprendizado salvam sem a equipe | prompt |
| 2026-11-07 | 1.10.8: "é para alguém da família"/"tem alguém que entrega" tiravam o silêncio | detector de pedido de pessoa com a frase fechada, depois do horário | prompt |
| 2026-11-07 | 1.10.8: fora do horário, "já chamei alguém" sem dizer quando abre; aviso "equipe ocupada" repetido | `texto_chamei` com horário; `robo_assumiu` ao tirar o silêncio | prompt |
| 2026-11-07 | 1.10.8: telefone igual em dois atendentes passava na aprovação | telefone único (normalizado) em validar_config | prompt |
| 2026-11-07 | 1.10.8: diálogo "Meu cadastro" depois do `<script>` quebrava o painel da equipe | dialog antes dos scripts | prompt |
| 2026-11-07 | 1.9.8 (antes de publicar): métrica "robô interagindo" contava frase pronta e silêncio como conversa | frases prontas fora; três faixas (sem resposta, robô, silêncio); pedido de abertura não conta | prompt |
| 2026-11-07 | Cadastros → "+ Produto" (e remover) quebrava com `palavras.join is not a function` depois de ler o formulário | aceitar palavras como texto ou lista ao redesenhar a linha | prompt |
| 2026-11-07 | Ao vivo 1.8.8 (antes de publicar): atendimento assumido sem nenhuma resposta aparecia como "respondido" | sem resposta da equipe no chamado → contar do assumir; teste com cliente calado | prompt |
| 2026-11-06 | "que hora tem atendimento humano?" abria chamado `pediu_humano` em vez de dizer o horário | detector de pergunta de horário (sem verbo de pedido) antes das regras 5–7 | prompt |
| 2026-11-05 | Evolution guardava cópia das mensagens/contatos no Postgres (fora do "apagar meus dados") | `DATABASE_SAVE_*` = `false` no compose, exceto INSTANCE | infra |
| 2026-11-05 | instalar-vps.sh com uid ≠ 1000 subia com `dados/` 0700 de outro dono (container sem acesso) | `sudo -n chown`; se `dados/` não for do uid 1000, abortar antes de subir | infra |
| 2026-11-05 | instalar-vps.sh rodado de novo trocava todos os segredos (Evolution sem autenticar no Postgres, webhook do Telegram 401) | reaproveitar do `.env` os segredos que já existem; gerar só os que faltam | infra |
