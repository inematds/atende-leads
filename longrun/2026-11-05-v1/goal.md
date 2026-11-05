# Goal — v1

- **Início:** 2026-11-05 19:31 · **Agente:** Claude (sessão wifi) + 2 subagentes (testes / implementação)
- **Tetos:** tempo 6 h · memória 4 G por processo de teste

## Resultado
Sistema atende-leads v1 (WhatsApp/Evolution → agente por regras → chamado → colaborador livre pelo Telegram → fechamento), com painéis lead/equipe/gestor, Docker para VPS, guia PT/EN/ES, portal, INEMA.VIBE e explicavideo.

## Critérios de pronto (verificáveis)

**Função**
- [ ] `python3 -m pytest -q tests/` → `N passed`, N ≥ 80, 0 failed, 0 error
- [ ] `./atende serve --porta 0 --dados $(mktemp -d)` → 1ª linha `PORTA=<n>` e `GET /api/saude` → `"ok": true`
- [ ] `INSTALAR_SO_GERAR=1 ./instalar-vps.sh --sem-perguntas` → gera `.env` e `dados/negocio.json` válidos
- [ ] `docker compose config -q` e `docker compose --profile evolution config -q` → saída vazia, rc 0

**Regressão**
- [ ] testes de `tests/` não editados depois do fechamento da suíte, salvo correção registrada em `failures.md` com o trecho do contrato

**Limite**
- [ ] `grep -rnE "api\.openai|anthropic|openrouter" src/` → vazio (nenhum provedor fixo)
- [ ] nenhuma chamada de rede real nos testes (servidores falsos locais)
- [ ] revisão independente (Agent general-purpose novo, runbook revisor-independente) sem bloqueante aberto

**Teste rápido por ciclo:** `python3 -m pytest -q -x tests/`
**Teste completo no final:** `python3 -m pytest -q tests/ && TESTAR_DOCKER=1 python3 -m pytest -q tests/test_docker.py`
