# Falhas (uma linha por falha, mais recente no topo)

| data | o que quebrou | menor correção | prompt \| infra |
|---|---|---|---|
| 2026-11-05 | Evolution guardava cópia das mensagens/contatos no Postgres (fora do "apagar meus dados") | `DATABASE_SAVE_*` = `false` no compose, exceto INSTANCE | infra |
| 2026-11-05 | instalar-vps.sh com uid ≠ 1000 subia com `dados/` 0700 de outro dono (container sem acesso) | `sudo -n chown`; se `dados/` não for do uid 1000, abortar antes de subir | infra |
| 2026-11-05 | instalar-vps.sh rodado de novo trocava todos os segredos (Evolution sem autenticar no Postgres, webhook do Telegram 401) | reaproveitar do `.env` os segredos que já existem; gerar só os que faltam | infra |
