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

## Testes alterados/novos na correção da segunda revisão independente (1.0.2)

| data | teste | trecho do contrato | motivo |
|---|---|---|---|
| 2026-11-05 | tests/fixtures/negocio.json + tests/conftest.py `CODIGOS` (helper) | §13 códigos com 12+ caracteres | códigos de teste `ana-1234` etc. viraram `ana-1234-teste` etc. (o PUT da config passou a recusar < 12) |
| 2026-11-05 | tests/test_interfaces.py `_invalidos` (helper) | §13 códigos únicos | código duplicado acompanha o novo código da Ana |
| 2026-11-05 | tests/test_seguranca.py::test_recusa_codigo_de_exemplo_e_aceita_segredos_proprios | §1 segredos de exemplo | dependia de o fixture usar o código do exemplo; agora põe o código do `exemplos/negocio.json` explicitamente |
| 2026-11-05 | tests_dev/*.py (códigos `ana-1234` → `ana-1234-dev01` etc.; `davi-1` → `davi-1-codigo-dev`) | §13 códigos com 12+ caracteres | mesmo motivo do fixture |
| 2026-11-05 | tests/conftest.py `Externo.respostas` (helper) | §8 painel; §16 erros do Telegram | falso devolve (status, json) roteirizados por método (429 com retry_after, 500, 400 qualquer) |
| 2026-11-05 | tests/test_seguranca.py::test_codigo_errado_5_vezes_429 (invertido) | §3 "credencial certa sempre passa" | 6º errado → 429; o código certo → 200 (antes: 429 mesmo com o certo) |
| 2026-11-05 | tests/test_seguranca.py::test_token_gestor_errado_5_vezes_429 (invertido) | §3 idem | 6º token errado → 429; o certo → 200 |
| 2026-11-05 | tests/test_seguranca.py::test_limite_por_ip_do_proxy_confiavel (novo) | §3 `ATENDE_PROXY_CONFIAVEL`, X-Forwarded-For | item 1: IPs diferentes atrás do proxy têm baldes próprios; valor forjado à esquerda não muda o balde; token certo passa do IP bloqueado |
| 2026-11-05 | tests/test_seguranca.py::test_proxy_nao_confiavel_ignora_x_forwarded_for (novo) | §3 proxy fora da lista | item 1: com a lista sem 127.0.0.1, XFF é ignorado e tudo cai no balde da conexão |
| 2026-11-05 | tests/test_seguranca.py::test_web_limita_leads_novos_por_ip (novo) | §4 limites do chat web | item 2: 6º lead web novo do mesmo IP em 10 min → 429; sessão existente e outro IP seguem |
| 2026-11-05 | tests/test_seguranca.py::test_web_teto_global_de_leads_novos (novo) | §4 30 leads web novos/min | item 2: 31º lead web no minuto (IPs variados) → 429 |
| 2026-11-05 | tests/test_seguranca.py::test_web_limita_chamados_por_ip (novo) | §4 3 chamados/h/IP | item 2: 4º chamado pelo web e pelo /meu/falar do mesmo IP → 429 e a fila não cresce |
| 2026-11-05 | tests/test_seguranca.py::test_segredo_de_webhook_fraco_recusa_em_0000 (novo) | §1 segredo de webhook fraco | item 4: vazio, < 16 e `troque` recusam em 0.0.0.0 com a integração ligada; ATENDE_PERMITIR_EXEMPLO=1 libera; fortes ou integração desligada sobem |
| 2026-11-05 | tests/test_painel.py::test_painel_erro_transitorio_nao_envia_painel_novo (novo) | §8 só 400 "não existe" reenvia | item 3: 500 e 429 (retry_after) → edita de novo, um painel só |
| 2026-11-05 | tests/test_painel.py::test_painel_erro_400_qualquer_nao_envia_painel_novo (novo) | §8 outro 4xx desiste da edição | item 3: 400 `chat not found` não cria painel novo |
| 2026-11-05 | tests/test_revisao2.py::test_nome_que_nao_parece_nome_pergunta_de_novo (novo) | §4 qualificação: parece nome | item 5: `não sei`, dígitos, verbos, 5+ palavras → `Pode me dizer só o seu nome?`; `meu nome é joana d'arc` aceito |
| 2026-11-05 | tests/test_revisao2.py::test_nome_com_digitos_nunca_vai_ao_grupo (novo) | §7 primeiro nome ou `lead` | item 5: nome com dígitos vira `lead` na linha do grupo |
| 2026-11-05 | tests/test_revisao2.py::test_apagar_com_chamado_em_atendimento (novo) | §4 regra 2 com chamado aberto | item 6: chamado `apagado`, colaborador livre, 🗑️ no grupo e no cartão, aviso ao dono, sem botões |
| 2026-11-05 | tests/test_revisao2.py::test_apagar_com_oferta_pendente (novo) | §4 regra 2 | item 6: oferta editada para 🗑️, fila vazia |
| 2026-11-05 | tests/test_revisao2.py::test_apagar_cancela_envios_pendentes_com_dados_do_lead (novo) | §4 regra 2 "envios pendentes cancelados" | item 6: oferta presa em backoff não sai depois do apagar (confirmado por mutação: sem o cancelamento o teste falha) |
| 2026-11-05 | tests/test_revisao2.py::test_fechar_solto_nao_e_chance_de_venda (novo) | §4 regra 6 | item 8: `vou fechar a loja` não abre chamado |
| 2026-11-05 | tests/test_revisao2.py::test_quero_fechar_abre_venda (novo) | §4 regra 6 | item 8: `quero fechar`, `fechar negócio` abrem venda |
| 2026-11-05 | tests/test_revisao2.py::test_assumir_so_quem_recebeu_a_oferta (novo) | §7 assumir restrito | item 8: [E] não ofertado → 403; ofertado → 200 |
| 2026-11-05 | tests/test_revisao2.py::test_assumir_em_alerta_qualquer_um (novo) | §7 assumir em alerta | item 8: em `alerta` qualquer colaborador (não fora) assume |
| 2026-11-05 | tests/test_revisao2.py::test_gestor_transfere_chamado_ofertado_a_outro (novo) | §7/§13 transferir | item 8: gestor passa o chamado a quem não recebeu a oferta |
| 2026-11-05 | tests/test_revisao2.py::test_assumir_pelo_telegram_sem_oferta_recusa (novo) | §7 botão `as:` restrito | item 8: botão de chamado alheio → `não foi oferecido a você` |
| 2026-11-05 | tests/test_revisao2.py::test_minutos_ate_assumir_conta_da_abertura_do_expediente (novo) | §9 minutos_ate_assumir; §13 hoje | item 8: chamado das 07:00, expediente 08:00, assumido 08:03 → 3 (e tempo médio 3) |

Fora de escopo, mantido de propósito: `/entrar` do Telegram continua barrando até o código certo depois de 5 erros (balde por `from.id`, não por IP — não sofre do problema do proxy). `assumir_retorno` (botão `ra:`) e `transferir` chamam `assumir` sem a restrição (o retorno já é do colaborador; o gestor transfere).

## Testes alterados/novos na correção da 3ª revisão independente (1.0.3)

| data | teste | trecho do contrato | motivo |
|---|---|---|---|
| 2026-11-05 | tests/test_revisao3.py::test_instalador_reaproveita_segredos_do_env (novo) | §17 instalar-vps.sh reaproveita os segredos | rodar de novo trocava EVOLUTION_DB_SENHA/TELEGRAM_SEGREDO (Evolution parava, webhook do Telegram 401) |
| 2026-11-05 | tests/test_revisao3.py::test_instalador_aborta_se_dados_nao_for_do_uid_1000 (novo, estático) | §17 chown ou aborta antes de subir | uid ≠ 1000 deixava dados/ 0700 de outro dono e subia mesmo assim |
| 2026-11-05 | tests/test_revisao3.py::test_backup_pasta_700_arquivo_600 (novo, estático) | §17 backups 700/600 | backup com dados pessoais legível por outros |
| 2026-11-05 | tests/test_revisao3.py::test_compose_evolution_nao_guarda_mensagens_nem_contatos (novo, arquivo) | §17 DATABASE_SAVE_* false (LGPD) | Evolution guardava cópia das mensagens que o "apagar" não limpa |
| 2026-11-05 | tests/test_revisao3.py::test_saude_responde_com_servidor_lotado (novo) | §1 limite de conexões, exceto /api/saude | healthcheck dava 503 com 64 conexões presas |
| 2026-11-05 | tests/test_revisao3.py::test_nome_invalido_do_chat_web_e_ignorado (novo) | §4 `nome` validado | nome do formulário entrava sem validação |
| 2026-11-05 | tests/test_revisao3.py::test_avisos_vem_marcados_no_chat_web (novo) | §4 `tipo: aviso` em GET /api/web | lead web não via "Ana vai te atender agora." |
| 2026-11-05 | tests/test_revisao3.py::test_telefone_estrangeiro_do_remotejid_sem_55 (novo) | §15 remoteJid sem 55 | número estrangeiro de 10–11 dígitos ganhava 55 |
| 2026-11-05 | tests/test_revisao3.py::test_apagar_edita_mensagens_do_lead_no_privado (novo) | §4 regra 2 (💬/📅/Ainda com) | dados do lead ficavam no privado do dono |
| 2026-11-05 | tests/test_revisao3.py::test_config_token_gestor_forte_e_arquivo_600 (novo) | §13 PUT config token 16+, arquivo 600 | token fraco aceito; negocio.json regravado 644 |
| 2026-11-05 | tests/test_revisao3.py::test_webhook_que_quebra_vai_para_descartes (novo) | §13 descartes de webhook que desistiu | falha só ia ao log |
| 2026-11-05 | tests/test_seguranca.py::test_csv_sem_injecao_de_formula (alterado) | §4 nome validado; §13 CSV prefixa `'` | a fórmula no `nome` agora é recusada; o escape do CSV passa a ser provado pelo id do colaborador |
| 2026-11-05 | tests_dev/test_cerebro.py::test_openai_resumo_e_chave (alterado) + test_chave_so_vai_a_host_permitido (novo) | §14 CEREBRO_HOSTS_PERMITIDOS | chave só vai a host permitido |

## Testes novos do modo polling do Telegram (1.1.3)

| data | teste | trecho do contrato | motivo |
|---|---|---|---|
| 2026-11-05 | tests/test_polling.py::test_saude_modo_padrao_webhook (novo) | §18 `telegram_modo` | sem TELEGRAM_MODO o padrão é webhook |
| 2026-11-05 | tests/test_polling.py::test_polling_entrar_vincula (novo) | §16 modo polling: deleteWebhook sem apagar pendentes, getUpdates (timeout, allowed_updates), /entrar | /entrar por getUpdates vincula sem TELEGRAM_SEGREDO; webhook HTTP segue 401 |
| 2026-11-05 | tests/test_polling.py::test_polling_callback_assume (novo) | §16 polling + botão `as:`; §1 ATENDE_AGORA | callback por polling assume e recebe answerCallbackQuery |
| 2026-11-05 | tests/test_polling.py::test_polling_offset_nao_reprocessa_ao_reiniciar (novo) | §16 offset no SQLite | reiniciar não reprocessa (Telegram falso devolve tudo sem offset; mutação sem offset falha) |
| 2026-11-05 | tests/test_polling.py::test_polling_erro_500_nao_derruba (novo) | §16 backoff 1, 2, 4… 30 s | 500 no getUpdates não derruba (saúde ok) e retoma |
| 2026-11-05 | tests/test_polling.py::test_polling_409_chama_deletewebhook_de_novo (novo) | §16 409 Conflict | 409 → deleteWebhook de novo e retoma |
| 2026-11-05 | tests/test_polling.py::test_polling_nao_exige_segredo_em_0000 (novo) | §1 trava de 0.0.0.0; §16 polling sem TELEGRAM_SEGREDO | webhook sem segredo recusa em 0.0.0.0; polling sobe |
| 2026-11-05 | tests/conftest.py Externo (alterado) | §16 | Telegram falso responde getUpdates (fila `injetar`, offset, [] após o timeout ≤ 2 s) e deleteWebhook; `trava` virou Condition |
