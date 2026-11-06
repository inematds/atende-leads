# Falhas (só acrescentar; ao fim, a menor correção vira linha no FALHAS.md do projeto)

| data | o que quebrou | tentativa | resultado | prompt \| infra |
|---|---|---|---|---|

## Testes alterados/novos na correção da revisão independente (1.0.1)

| data | teste | trecho do contrato | motivo |
|---|---|---|---|
| 2026-11-05 | tests/conftest.py `Cliente.msg_full` (helper) | §4 "`canal: whatsapp` por esta rota é a simulação … exige [G]" | rota pública com canal whatsapp era o caminho de injeção; helper manda X-Token quando canal=whatsapp |
| 2026-11-05 | tests/conftest.py `Externo.pendurar`/`solta` (helper) | §1 "Rede fora do lock" | servidor falso que aceita e não responde, para o teste de API pendurada |
| 2026-11-05 | tests/test_interfaces.py::test_meu_apagar | §11 "`/apagar` com `{"confirmar": true}` … sem a confirmação → 422" | apagar pela página passou a exigir confirmação |
| 2026-11-05 | tests/test_docker.py::test_docker_build_e_compose_config | §1 "Segredos de exemplo" + §17 HEALTHCHECK | container com o exemplo recusa em 0.0.0.0; com ATENDE_PERMITIR_EXEMPLO=1 o /api/saude responde |
| 2026-11-05 | tests_dev/apoio_dev.py `Servidor.msg` (helper) | §4 canal whatsapp exige [G] | mesmo motivo do msg_full |
| 2026-11-05 | tests_dev/test_fluxo.py::test_saude_e_porta | §18 `versao` = VERSION | versão estava fixa em 1.0.0; agora lê o arquivo VERSION |
| 2026-11-05 | tests/test_seguranca.py::test_saude_responde_rapido_com_telegram_pendurado (novo) | §1 "Rede fora do lock" | Telegram pendurado não trava /api/saude (< 1 s) nem o painel |
| 2026-11-05 | tests/test_seguranca.py::test_web_cria_sessao_propria (novo) | §3 sessão; §4 canal web | 1ª msg web cria lead e sessão ≥ 24; seguintes pela sessão; sessão inexistente 404; GET /api/web |
| 2026-11-05 | tests/test_seguranca.py::test_whatsapp_pela_api_exige_gestor (novo) | §4 canal whatsapp [G] | sem token → 401 |
| 2026-11-05 | tests/test_seguranca.py::test_token_do_lead_whatsapp_nao_vaza_pelo_web (novo) | §3 "token só é entregue ao próprio lead" | telefone digitado no web não devolve o token do lead do WhatsApp |
| 2026-11-05 | tests/test_seguranca.py::test_api_meu_nao_devolve_mensagens (novo) | §11 `/api/meu` só 4 campos | link /meu repassado não expõe a conversa |
| 2026-11-05 | tests/test_seguranca.py::test_injecao_web_nao_chega_ao_lead_do_whatsapp (novo) | §4 "nunca se mistura com o lead do WhatsApp" | web com o telefone de um lead em atendimento não chega ao colaborador |
| 2026-11-05 | tests/test_seguranca.py::test_codigo_errado_5_vezes_429 (novo) | §3 limite de tentativas | 5 X-Codigo errados → 429 mesmo com o certo |
| 2026-11-05 | tests/test_seguranca.py::test_token_gestor_errado_5_vezes_429 (novo) | §3 limite de tentativas | idem para X-Token |
| 2026-11-05 | tests/test_seguranca.py::test_entrar_limite_por_from_id (novo) | §16 `/entrar` 5 erros → `Muitas tentativas, aguarde.` | força bruta pelo bot |
| 2026-11-05 | tests/test_seguranca.py::test_entrar_de_outra_conta_avisa_a_anterior (novo) | §16 vínculo anterior recebe aviso `outra conta` | código vazado é percebido |
| 2026-11-05 | tests/test_seguranca.py::test_status_em_outro_grupo_ignorado (novo) | §8/§16 `/status` só no TELEGRAM_GRUPO_ID | painel não vaza em grupo alheio |
| 2026-11-05 | tests/test_seguranca.py::test_csv_sem_injecao_de_formula (novo) | §13 CSV prefixa `'` | nome `=HYPERLINK(...)` |
| 2026-11-05 | tests/test_seguranca.py::test_lid_usa_telefone_alternativo[remoteJidAlt/senderPn/data.senderPn] (novo) | §15 `@lid` | lead pelo telefone alternativo |
| 2026-11-05 | tests/test_seguranca.py::test_lid_sem_telefone_vai_para_descartes (novo) | §13 `descartes`; §15 `@lid` | descarte visível no ao-vivo |
| 2026-11-05 | tests/test_seguranca.py::test_problema_negado_nao_abre_chamado[3 casos] (novo) | §4 regra 7 negação | `sem/nenhum/não tem problema` não abre chamado |
| 2026-11-05 | tests/test_seguranca.py::test_problema_de_verdade_abre_chamado (novo) | §4 regra 7 palavra inteira + plural | `problemas` ainda abre |
| 2026-11-05 | tests/test_seguranca.py::test_reenvio_nao_vai_para_quem_pediu_parar (novo) | §4.1 + §15 `cancelado` | reenvio não vai a lead com nao_contatar |
| 2026-11-05 | tests/test_seguranca.py::test_recusa_segredos_de_exemplo_em_0000 (novo) | §1 segredos de exemplo | recusa em 0.0.0.0, sobe em 127.0.0.1 e com ATENDE_PERMITIR_EXEMPLO=1 |
| 2026-11-05 | tests/test_seguranca.py::test_recusa_codigo_de_exemplo_e_aceita_segredos_proprios (novo) | §1 segredos de exemplo | só o código do exemplo já recusa; segredos próprios sobem em 0.0.0.0 |
| 2026-11-05 | tests/test_seguranca.py::test_restaurar_recusa_com_servidor_rodando (novo) | §1 `restaurar` recusa | stderr com `docker compose stop atende` |
