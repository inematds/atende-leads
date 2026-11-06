# CLAUDE.md — atende-leads

Atendimento de leads pelo WhatsApp (Evolution) com agente por regras e roteamento ao colaborador livre pelo Telegram. Contrato em `docs/ESPECIFICACAO.md`; testes em `tests/`.

- Conta/autor: `inematds <inematds@gmail.com>`; repo público `inematds/atende-leads`.
- Python 3 só biblioteca padrão. Nada de `pip install`.
- Nenhuma API real em teste ou desenvolvimento; cérebro padrão = regras.
- Commit que toca `.github/workflows/` → push por SSH (token inematds sem escopo workflow).
- Guia em `guia/` (PT) + `guia/en/` + `guia/es/`.

## Self-learning

When I correct you, or you catch yourself making a mistake: before continuing, add the lesson as a one-line rule at the TOP of the Lessons section below.

## Lessons
- Antes de desempacotar o retorno de uma função do próprio projeto, conferir quantos valores ela devolve (`consolidada.horario_do_texto` devolve 3). (06/11/2026)
- Antes de criar ou usar um `id` no HTML, `grep` o arquivo: id duplicado faz `getElementById` pegar o campo errado em silêncio (`c-url`). (06/11/2026)
