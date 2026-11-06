"""Seção 4a: base de conhecimento (info), respostas automáticas e o 'Testar' sem gravar nada; §2 validação."""
from conftest import TEL, ok
from falsos import cfg_cerebro

INFO = {"horario_atendimento": "", "endereco": "Rua das Flores, 50, Centro", "pagamento": "Pix, cartão em até 10x e boleto",
        "entrega": "", "garantia": "", "site": "https://loja.exemplo.test", "observacoes": "Estacionamento grátis"}


def com_info(api, **campos):
    info = dict(INFO, **campos)
    return cfg_cerebro(api, {"tipo": "regras"}, info=info)


def chamados(api, lead_id):
    return api.chamados_do_lead(lead_id)


def test_hora_atendimento_humano_responde_horario_sem_abrir_chamado(api):
    """O caso que falhou no teste do dono: contém 'humano' mas é pergunta de horário."""
    r = api.msg_full(TEL, "que hora tem atendimento humano?")
    txt = r["respostas"][0]
    assert "seg a sex 08:00–18:00" in txt and "sáb 09:00–13:00" in txt, txt
    assert "Agora estamos atendendo." in txt
    assert "vou chamar" not in txt.lower()
    assert chamados(api, r["lead"]["id"]) == []


def test_tem_alguem_ai_fora_do_horario(api):
    api.relogio("2026-11-09T20:00")
    txt = api.msg(TEL, "tem alguém aí agora?")
    assert "fora do horário" in txt and "10/11 às 08:00" in txt, txt


def test_horario_do_info_vence_o_gerado(api):
    com_info(api, horario_atendimento="Atendimento humano de seg a sex, 9h às 17h.")
    txt = api.msg(TEL, "até que horas vocês atendem?")
    assert txt.startswith("Atendimento humano de seg a sex, 9h às 17h.") and "Agora estamos atendendo." in txt


def test_faq_de_horario_continua_exato(api):
    assert api.msg_full(TEL, "qual o horario de atendimento")["respostas"] == \
        ["Atendemos de segunda a sexta, das 8h às 18h."]


def test_pedido_de_humano_continua_abrindo_chamado(api):
    r = api.msg_full(TEL, "quero falar com um atendente agora", nome="Maria Souza")
    assert "vou chamar" in "\n".join(r["respostas"]).lower()
    assert chamados(api, r["lead"]["id"])


def test_endereco_pagamento_site(api):
    com_info(api)
    assert api.msg(TEL, "qual o endereço de vocês?") == "Endereço: Rua das Flores, 50, Centro"
    assert api.msg(TEL, "aceita pix?") == "Formas de pagamento: Pix, cartão em até 10x e boleto"
    assert api.msg(TEL, "vocês tem site?") == "Site: https://loja.exemplo.test"


def test_forma_de_pagamento_continua_venda_com_prefixo(api):
    com_info(api)
    r = api.msg_full(TEL, "qual a forma de pagamento?", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert txt.startswith("Formas de pagamento: Pix, cartão em até 10x e boleto. ") and "vou chamar" in txt.lower()
    assert any(c["motivo"] == "venda" for c in chamados(api, r["lead"]["id"]))


def test_campo_vazio_nao_inventa(api):
    com_info(api)  # entrega e garantia vazios
    api.msg(TEL, "qual o horario de atendimento")
    assert "não entendi" in api.msg(TEL, "vocês entregam em Curitiba?").lower()
    assert "Entrega:" not in api.msg(TEL, "tem frete?")


def test_sem_info_nada_de_endereco_inventado(api):
    # sem `info`, "qual o endereço" segue o fluxo normal (o FAQ do fixture tem "onde fica a loja")
    api.msg(TEL, "qual o horario de atendimento")
    assert "Endereço:" not in api.msg(TEL, "qual o endereço?")
    assert api.msg(TEL, "onde fica a loja?") == "Ficamos na Rua Exemplo, 100, Centro."


def test_testar_nao_grava_nada(api):
    antes_leads = api.get("/api/gestor/leads")[1]
    st, r = api.post("/api/gestor/testar", {"texto": "quero falar com um atendente"})
    assert st == 200, r
    assert "vou chamar" in "\n".join(r["respostas"]).lower() and r["chamado"] == "pediu_humano"
    st, r2 = api.post("/api/gestor/testar", {"texto": "que hora tem atendimento humano?"})
    assert st == 200 and "seg a sex" in r2["respostas"][0] and r2["chamado"] is None
    assert api.get("/api/gestor/leads")[1] == antes_leads
    assert api.fila() == [] and api.saida() == []
    st, h = api.get("/api/gestor/hoje")
    assert h["leads_novos"] == 0 and h["chamados_abertos"] == 0


def test_testar_exige_gestor_e_texto(api):
    assert api.post("/api/gestor/testar", {"texto": "oi"}, token=None)[0] == 401
    assert api.post("/api/gestor/testar", {"texto": "  "})[0] == 422


def test_testar_responde_faq(api):
    st, r = api.post("/api/gestor/testar", {"texto": "onde fica a loja?"})
    assert st == 200 and r["respostas"] == ["Ficamos na Rua Exemplo, 100, Centro."]


def test_config_valida_info_aprendizado_cerebro(api):
    st, cfg = api.get("/api/gestor/config")
    for ruim in ({"info": {"cor": "azul"}}, {"info": {"endereco": 12}}, {"info": "x"},
                 {"aprendizado": {"periodo": "mensal"}},
                 {"cerebro": {"tipo": "anthropic", "modelo": "m", "api_key": "sk"}},
                 {"cerebro": {"tipo": "anthropic", "modelo": "--rm -rf"}},
                 {"cerebro": {"tipo": "anthropic", "modelo": "m", "esforco": "turbo"}},
                 {"cerebro": {"tipo": "gpt"}}):
        st, r = api.put("/api/gestor/config", dict(cfg, **ruim))
        assert st == 422, (ruim, st, r)
    for bom in ({"cerebro": {"tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low"}},
                {"cerebro": {"tipo": "openrouter", "modelo": "anthropic/claude-sonnet-5.5"}},
                {"cerebro": {"tipo": "claude_cli", "modelo": "sonnet"}},
                {"cerebro": {"tipo": "codex_cli", "modelo": "gpt-6-luna"}},
                {"aprendizado": {"periodo": "diario"}}, {"info": INFO}):
        st, r = api.put("/api/gestor/config", dict(cfg, **bom))
        assert ok(st), (bom, st, r)


def test_saude_cerebro_ok_em_regras(api):
    s = api.get("/api/saude")[1]
    assert s["cerebro"] == "regras" and s["cerebro_ok"] is True


def test_info_vale_no_meio_da_qualificacao(api):
    com_info(api)
    r = api.msg_full(TEL, "oi")
    assert "nome" in r["respostas"][0].lower()
    assert api.msg(TEL, "qual o endereço?") == "Endereço: Rua das Flores, 50, Centro"
    assert "Prazer" in api.msg(TEL, "Maria")  # a etapa do nome continua
