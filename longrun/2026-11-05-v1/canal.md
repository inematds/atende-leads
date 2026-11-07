# Canal — v1 (só acrescentar; nunca reescrever)

Conhecimento do projeto que a compactação perde: fatos descobertos, aprendizados, glossário, armadilhas, onde estão as coisas.
Não é estado da tarefa (isso vai em state/plan/progress). Preencha cedo — o hook avisa na faixa 1 (~50% do contexto).

Formato: `- AAAA-MM-DD HH:MM · fato|aprendizado|glossário|armadilha · texto`

- 2026-11-05 20:10 · fato · Implementação v1 em src/ (core, server, conversa, chamados, equipe, horario, tarefas, bot, telegram, evolution, rede, cerebro, gestao, paginas, backup); testes do implementador em tests_dev/ (19 casos, Telegram/Evolution/LLM falsos locais).
- 2026-11-05 20:10 · armadilha · urllib capitaliza headers (`apikey` → `Apikey`); rede.py usa http.client para manter a grafia.
- 2026-11-05 20:10 · armadilha · Telegram real erra "message is not modified" ao editar com o mesmo texto; painel guarda o último texto e trata esse erro como sucesso.
- 2026-11-05 20:10 · fato · Evolution v2: imagem oficial evoapicloud/evolution-api (repo evolution-foundation/evolution-api), v2.3.7 estável; latest = 2.4.0-rc. sendText v2 = {number, text} no topo; webhook global por env WEBHOOK_GLOBAL_URL.
- 2026-11-05 20:10 · armadilha · docker-compose.yml usa `env_file: .env` literal (contrato §17): `docker compose config` falha sem .env — gerar com instalar-vps.sh ou copiar .env.exemplo antes.
- 06/11: no ar em https://atende-lead.inema.club (VPS4 /opt/atende-leads, ver ~/projetos/wifi/VPS.md). Local desligado. Deploy: git push aqui → ssh VPS4 git pull + docker compose --profile evolution up -d --build atende. Credenciais em /root/atende-lead-credenciais.txt na VPS4.

## 07/11/2026 — 1.8.8 e 1.8.9 no ar; 1.9.8 em andamento
- 1.8.8 (325bbb4): gestor Ao vivo/Hoje em 4 grupos (`gestao._grupos`), `sem_resposta_min` (sem resposta da equipe no chamado → conta do assumir), leads com `situacao` + filtros `situacao`/`contato` + ordenação no front. Revisor nota 7, achados corrigidos.
- 1.8.9 (65603f9): "+ Produto" quebrava (`palavras` lido como texto pelo `lerCadastros`). Reproduzido com cópia do negocio.json de produção em scratchpad (apagada depois).
- Armadilha: servidor de teste local que sobra segura o `dados/` ("Já há um servidor rodando") — matar o `atende serve` antes de repetir; `pkill -f <padrão>` mata o próprio shell se o padrão estiver no comando.
- `leads.nao_contatar` já existe: PARAR ('parar','sair','pare') liga; qualquer nova mensagem do lead desliga.
- 1.9.8 pedido (Nei, 07/11): equipe com Para assumir + Minhas conversas (abas), "Equipe" em menu à parte, Meus clientes, retomar contato encerrado (bloqueado se nao_contatar), avisos no navegador, robô cobre (gestor: assume após X min; atendente: "robô responde por mim"), tempos classificados, gestor transfere conversa do robô para atendente. 1.10.8: prospecção (só quem já conversou; gestor pode liberar todos) + análise por atendente.
