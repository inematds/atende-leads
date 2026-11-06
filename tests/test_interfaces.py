"""Seções 11–13: páginas, /meu do lead, painel da equipe e painel do gestor."""
import copy
import json

import pytest

from conftest import CODIGOS, TEL, TEL2, TOKEN, URL_PUBLICA, equipe_pronta, lista, mais, ok

CABECALHO = "lead_id,nome,telefone,status,nota,interesse,colaborador,resultado,valor,criado_em,ultimo_contato"


# ------------------------------------------------------------ páginas públicas

@pytest.mark.parametrize("rota", ["/", "/equipe", "/gestor"])
def test_paginas_html(api, rota):
    st, html = api.get(rota, token=None)
    assert st == 200
    assert "text/html" in api.ultimo_tipo
    assert "<html" in html.lower()


def test_widget_js(api):
    st, js = api.get("/widget.js", token=None)
    assert st == 200
    assert "javascript" in api.ultimo_tipo
    assert "widget=1" in js and "iframe" in js.lower()


# ------------------------------------------------------------ lead: /meu

def test_pagina_meu(api):
    lead = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    st, html = api.get(f"/meu/{lead['token']}", token=None)
    assert st == 200 and "text/html" in api.ultimo_tipo
    for trecho in ("Loja Teste", "Quero falar agora", "Apagar meus dados"):
        assert trecho in html


def test_pagina_meu_status_em_texto(api):
    api.status("ana", "livre")
    lead, ch = api.abrir()
    _, html = api.get(f"/meu/{lead['token']}", token=None)
    assert "Alguém da equipe vai falar com você" in html
    assert ok(api.assumir("ana", ch)[0])
    _, html = api.get(f"/meu/{lead['token']}", token=None)
    assert "Ana está te atendendo" in html
    assert ok(api.fechar("ana", ch, {"resultado": "retornar", "retornar_em": "2026-11-10T09:00"})[0])
    _, html = api.get(f"/meu/{lead['token']}", token=None)
    assert "Retorno marcado para 10/11 às 09:00" in html


def test_api_meu(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    st, r = api.get(f"/api/meu/{lead['token']}", token=None)
    assert st == 200
    assert set(r) >= {"nome", "status", "colaborador", "retornar_em"}
    assert r["nome"] == "Maria Souza"
    assert "Ana" in str(r["colaborador"]) or r["colaborador"] == "ana"


def test_meu_falar_abre_pediu_humano_uma_vez(api):
    lead = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    assert ok(api.post(f"/api/meu/{lead['token']}/falar", token=None)[0])
    cs = api.chamados_do_lead(lead["id"])
    assert [c["motivo"] for c in cs] == ["pediu_humano"]
    api.post(f"/api/meu/{lead['token']}/falar", token=None)
    assert len(api.chamados_do_lead(lead["id"])) == 1


def test_meu_apagar(api):
    lead = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    assert api.post(f"/api/meu/{lead['token']}/apagar", token=None)[0] == 422  # §11: exige confirmação
    assert api.lead_csv(lead["id"])["nome"] == "Maria Souza"
    assert ok(api.post(f"/api/meu/{lead['token']}/apagar", {"confirmar": True}, token=None)[0])
    assert api.lead_csv(lead["id"])["nome"] == "apagado"
    assert api.lead_csv(lead["id"])["telefone"] == f"apagado-{lead['id']}"


def test_meu_rotas_token_inexistente_404(api):
    for metodo, rota in (("POST", "/api/meu/inexistente000000000/falar"), ("POST", "/api/meu/inexistente000000000/apagar")):
        assert api.req(metodo, rota, {}, token=None)[0] == 404


def test_link_acompanhe_desligado_por_padrao(api):
    # 05/11/2026 (Nei): o lead já está na conversa; o link "meu atendimento" não vai por padrão.
    r = api.msg_full(TEL, "quero falar com um atendente", nome="Maria Souza")
    assert "Acompanhe aqui" not in "\n".join(r["respostas"])


# ------------------------------------------------------------ gestor

def test_gestor_hoje(api):
    equipe_pronta(api, quem=("ana",))
    api.msg_full(TEL2, "oi")
    lead, ch = api.abrir()
    api.relogio(mais(api.agora, 2))
    assert ok(api.assumir("ana", ch)[0])
    assert ok(api.fechar("ana", ch, {"resultado": "vendeu", "valor": 1200.0})[0])
    st, h = api.get("/api/gestor/hoje")
    assert st == 200
    assert h["leads_novos"] == 2
    assert h["chamados_abertos"] == 1 and h["assumidos"] == 1
    assert h["vendas"] == 1 and float(h["valor_vendido"]) == 1200.0
    assert float(h["tempo_medio_assumir_min"]) == 2
    ana = next(c for c in h["por_colaborador"] if c["id"] == "ana")
    assert ana["assumidos"] == 1 and ana["vendas"] == 1 and float(ana["valor"]) == 1200.0


def test_gestor_hoje_e_do_dia_do_relogio(api):
    api.msg_full(TEL, "oi")
    api.relogio("2026-11-10T09:00")
    assert api.get("/api/gestor/hoje")[1]["leads_novos"] == 0


def test_gestor_leads_lista_e_filtro(api):
    api.status("ana", "livre")
    lead1, ch = api.atendendo("ana")
    lead2 = api.msg_full(TEL2, "oi")["lead"]
    st, r = api.get("/api/gestor/leads")
    assert st == 200
    ids = {str(l["id"]) for l in lista(r, "leads")}
    assert {str(lead1["id"]), str(lead2["id"])} <= ids
    st, r = api.get("/api/gestor/leads?status=em_atendimento")
    assert {str(l["id"]) for l in lista(r, "leads")} == {str(lead1["id"])}
    st, r = api.get("/api/gestor/leads?colaborador=ana")
    assert str(lead1["id"]) in {str(l["id"]) for l in lista(r, "leads")}
    assert str(lead2["id"]) not in {str(l["id"]) for l in lista(r, "leads")}


def test_gestor_ficha_completa(api):
    lead = api.msg_full(TEL, "mensagem-da-ficha", nome="Maria Souza")["lead"]
    f = api.ficha(lead["id"])
    assert "mensagem-da-ficha" in json.dumps(f, ensure_ascii=False)
    assert api.get("/api/gestor/leads/999999")[0] == 404


def test_transferir_assumido(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.status("bruno", "livre")
    st, _ = api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "bruno"})
    assert ok(st)
    assert [str(c["id"]) for c in api.eu("bruno")["chamados"]] == [str(ch)]
    assert api.eu("bruno")["status"] == "atendendo"
    assert api.eu("ana")["status"] == "livre" and api.eu("ana")["chamados"] == []


def test_transferir_nao_assumido(api):
    lead, ch = api.abrir()
    api.status("carla", "ocupado")
    st, _ = api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "carla"})
    assert ok(st)
    c = next(c for c in api.chamados_do_lead(lead["id"]) if str(c["id"]) == str(ch))
    assert c["status"] == "atendendo" and c["dono"] == "carla"


def test_transferir_exige_gestor(api):
    lead, ch = api.abrir()
    st, _ = api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "carla"}, token=None,
                     codigo=CODIGOS["ana"])
    assert st == 401


def test_reabrir_chamado_fechado(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    st, _ = api.post(f"/api/gestor/chamados/{ch}/reabrir")
    assert ok(st)
    f = next(f for f in api.fila() if str(f["id"]) == str(ch))
    assert f["status"] in ("aguardando", "alerta")


def test_config_get_esconde_token(api):
    st, cfg = api.get("/api/gestor/config")
    assert st == 200
    assert cfg["token_gestor"] == "***"
    assert cfg["nome"] == "Loja Teste" and len(cfg["equipe"]) == 3


def _cfg(api):
    return api.get("/api/gestor/config")[1]


def _invalidos(base):
    a = copy.deepcopy(base); a["equipe"][1]["id"] = "ana"
    b = copy.deepcopy(base); b["equipe"][1]["codigo"] = "ana-1234-teste"
    c = copy.deepcopy(base); c["horarios"]["seg"] = [["8h", "18:00"]]
    d = copy.deepcopy(base); d["prazos"]["oferta_min"] = 0
    e = copy.deepcopy(base); e["prazos"]["lembrete_min"] = "trinta"
    f = copy.deepcopy(base); f["produtos"].append(dict(base["produtos"][0]))
    return [a, b, c, d, e, f]


@pytest.mark.parametrize("i", range(6))
def test_config_put_invalido_422_nada_muda(api, dados, i):
    base = _cfg(api)
    arquivo_antes = (dados / "negocio.json").read_text()
    ruim = _invalidos(base)[i]
    ruim["nome"] = "Nome Que Nao Pode Entrar"
    st, _ = api.put("/api/gestor/config", ruim)
    assert st == 422
    assert _cfg(api) == base
    assert (dados / "negocio.json").read_text() == arquivo_antes


def test_config_put_valido_mantem_token_com_asteriscos(api, dados):
    cfg = _cfg(api)
    cfg["nome"] = "Loja Nova"
    st, _ = api.put("/api/gestor/config", cfg)
    assert ok(st)
    assert _cfg(api)["nome"] == "Loja Nova"
    assert api.get("/api/gestor/config", token=TOKEN)[0] == 200  # token antigo continua valendo
    disco = json.loads((dados / "negocio.json").read_text())
    assert disco["nome"] == "Loja Nova" and disco["token_gestor"] == TOKEN


def test_exportar_csv(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.fechar("ana", ch, {"resultado": "vendeu", "valor": 1200.0, "produto": "plano-anual"})
    st, b = api.get("/api/gestor/exportar.csv", bruto=True)
    assert st == 200
    texto = b.decode("utf-8").lstrip("﻿")
    assert texto.splitlines()[0].strip() == CABECALHO
    linha = api.lead_csv(lead["id"])
    assert linha["nome"] == "Maria Souza" and linha["status"] == "ganho" and linha["colaborador"] == "ana"
    assert linha["telefone"] == "5541999990001" and linha["resultado"] == "vendeu"
