# Canal — v1 (só acrescentar; nunca reescrever)

Conhecimento do projeto que a compactação perde: fatos descobertos, aprendizados, glossário, armadilhas, onde estão as coisas.
Não é estado da tarefa (isso vai em state/plan/progress). Preencha cedo — o hook avisa na faixa 1 (~50% do contexto).

Formato: `- AAAA-MM-DD HH:MM · fato|aprendizado|glossário|armadilha · texto`

- 2026-11-05 20:10 · fato · Implementação v1 em src/ (core, server, conversa, chamados, equipe, horario, tarefas, bot, telegram, evolution, rede, cerebro, gestao, paginas, backup); testes do implementador em tests_dev/ (19 casos, Telegram/Evolution/LLM falsos locais).
- 2026-11-05 20:10 · armadilha · urllib capitaliza headers (`apikey` → `Apikey`); rede.py usa http.client para manter a grafia.
- 2026-11-05 20:10 · armadilha · Telegram real erra "message is not modified" ao editar com o mesmo texto; painel guarda o último texto e trata esse erro como sucesso.
- 2026-11-05 20:10 · fato · Evolution v2: imagem oficial evoapicloud/evolution-api (repo evolution-foundation/evolution-api), v2.3.7 estável; latest = 2.4.0-rc. sendText v2 = {number, text} no topo; webhook global por env WEBHOOK_GLOBAL_URL.
- 2026-11-05 20:10 · armadilha · docker-compose.yml usa `env_file: .env` literal (contrato §17): `docker compose config` falha sem .env — gerar com instalar-vps.sh ou copiar .env.exemplo antes.
