"""Seção 13a: aprendizado → base (lista, filtros, contadores, propostas por regras e por cérebro,
incorporar/descartar, período configurável)."""
import json

import pytest

from conftest import CODIGOS, Servidor, ok
from falsos import FalsoLLM, cfg_cerebro

RESP = "Entregamos em Curitiba e região metropolitana em até 2 dias."


def atendimento(api, tel, nome, pergunta, resposta, cid="ana"):
    """Lead abre chamado, `cid` assume pelo painel, lead pergunta, `cid` responde livre."""
    api.status(cid, "livre")
    lead, ch = api.atendendo(cid, telefone=tel, nome=nome)
    api.msg(tel, pergunta)
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": resposta}, codigo=CODIGOS[cid])
    assert ok(st), r
    st, r = api.fechar(cid, ch, {"resultado": "negociando"})
    assert ok(st), r
    return lead, ch


def dois_parecidos(api):
    atendimento(api, "41999990101", "Maria Souza", "vocês entregam em Curitiba?", RESP)
    atendimento(api, "41999990102", "João Lima", "fazem entrega em Curitiba?", RESP + "!")


def propostas(api, **q):
    st, r = api.get("/api/gestor/propostas" + (f"?status={q['status']}" if q.get("status") else ""))
    assert st == 200, (st, r)
    return r


def test_lista_filtros_e_contadores(api):
    dois_parecidos(api)
    api.status("ana", "ocupado")  # vez do bruno
    atendimento(api, "41999990103", "Ana Paula", "tem cor azul?", "Temos sim, azul e verde.", cid="bruno")
    st, r = api.get("/api/gestor/aprendizado")
    assert st == 200 and r["contadores"]["total"] == 3 and r["contadores"]["livre"] == 3
    assert r["periodo"] == "semanal"
    it = r["itens"][0]
    for k in ("em", "colaborador", "lead_id", "chamado_id", "msg_lead", "sugestao", "enviado", "origem", "distancia"):
        assert k in it, k
    assert len(api.get("/api/gestor/aprendizado?colaborador=bruno")[1]["itens"]) == 1
    assert len(api.get("/api/gestor/aprendizado?origem=sugestao_ok")[1]["itens"]) == 0
    assert api.get("/api/gestor/aprendizado?origem=xpto")[0] == 422
    assert len(api.get("/api/gestor/aprendizado?de=2026-11-10")[1]["itens"]) == 0
    assert api.get("/api/gestor/aprendizado", token=None)[0] == 401


def test_proposta_por_regras_incorporar(api):
    dois_parecidos(api)
    st, r = api.post("/api/gestor/propostas/gerar", {})
    assert st == 200 and r["criadas"] == 1, r
    p = r["propostas"][0]
    assert p["tipo"] == "faq" and p["origem"] == "regras" and p["status"] == "nova"
    assert p["resposta"] in (RESP, RESP + "!") and "vocês entregam em Curitiba?" in p["perguntas"]
    # gerar de novo não repete
    assert api.post("/api/gestor/propostas/gerar", {})[1]["criadas"] == 0
    st, r = api.post(f"/api/gestor/propostas/{p['id']}/incorporar", {"resposta": RESP})
    assert ok(st), r
    faq = api.get("/api/gestor/config")[1]["faq"]
    novo = next(f for f in faq if f["id"] == f"apr-{p['id']}")
    assert novo["resposta"] == RESP
    assert api.post(f"/api/gestor/propostas/{p['id']}/incorporar", {})[0] == 409
    assert propostas(api, status="incorporada")[0]["id"] == p["id"]
    # o agente passa a responder pelo FAQ novo
    api.msg("41999990109", "qual o horario de atendimento", nome="Rita")
    assert api.msg("41999990109", "vocês entregam em Curitiba?") == RESP


def test_descartar(api):
    dois_parecidos(api)
    p = api.post("/api/gestor/propostas/gerar", {})[1]["propostas"][0]
    assert ok(api.post(f"/api/gestor/propostas/{p['id']}/descartar", {})[0])
    assert propostas(api)[0]["status"] == "descartada"
    assert api.post(f"/api/gestor/propostas/{p['id']}/descartar", {})[0] == 409
    assert api.post("/api/gestor/propostas/999/incorporar", {})[0] == 404
    faq = api.get("/api/gestor/config")[1]["faq"]
    assert not any(f["id"].startswith("apr-") for f in faq)


def test_um_so_nao_gera_proposta(api):
    atendimento(api, "41999990101", "Maria Souza", "vocês entregam em Curitiba?", RESP)
    assert api.post("/api/gestor/propostas/gerar", {})[1]["criadas"] == 0


@pytest.mark.parametrize("periodo,dias,espera", [("diario", 1, True), ("semanal", 1, False), ("semanal", 7, True),
                                                  ("desligado", 8, False)])
def test_periodo_configuravel(api, periodo, dias, espera):
    st, cfg = api.get("/api/gestor/config")
    cfg["aprendizado"] = {"periodo": periodo}
    assert ok(api.put("/api/gestor/config", cfg)[0])
    dois_parecidos(api)
    api.rodar()
    assert propostas(api) == []  # ainda não venceu
    api.avancar(dias=dias)
    assert bool(propostas(api)) is espera, (periodo, dias)


def test_proposta_pelo_cerebro_info(dados):
    resp = json.dumps({"propostas": [
        {"tipo": "info", "campo": "entrega", "resposta": RESP, "perguntas": ["vocês entregam em Curitiba?"],
         "justificativa": "2 vendedores responderam igual", "exemplos": ["vocês entregam em Curitiba?"]},
        {"tipo": "correcao", "faq_id": "nao-existe", "resposta": "x"},  # inválida: descartada
        {"tipo": "faq", "perguntas": [], "resposta": "sem pergunta"}]})  # inválida
    llm = FalsoLLM(lambda corpo: resp if "propostas" in json.dumps(corpo) else "SEM_RESPOSTA")
    try:
        api = Servidor(dados, env={"CEREBRO_API_KEY": "sk-falsa", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"}).subir()
        cfg_cerebro(api, {"tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low"})
        dois_parecidos(api)
        st, r = api.post("/api/gestor/propostas/gerar", {"de": "2026-11-09", "ate": "2026-11-09"})
        assert st == 200 and r["criadas"] == 1, r
        p = r["propostas"][0]
        assert p["tipo"] == "info" and p["campo"] == "entrega" and p["origem"] == "cerebro"
        assert ok(api.post(f"/api/gestor/propostas/{p['id']}/incorporar", {})[0])
        assert api.get("/api/gestor/config")[1]["info"]["entrega"] == RESP
        api.msg("41999990109", "qual o horario de atendimento", nome="Rita")
        assert api.msg("41999990109", "vocês entregam em Curitiba?") == f"Entrega: {RESP}"
        pedido = [x for x in llm.lista() if "propostas" in json.dumps(x["json"])][-1]["json"]
        assert "vocês entregam em Curitiba?" in pedido["messages"][-1]["content"]
    finally:
        llm.fechar()


def test_cerebro_json_invalido_cai_nas_regras(dados):
    llm = FalsoLLM("isto não é JSON")
    try:
        api = Servidor(dados, env={"CEREBRO_API_KEY": "sk-falsa", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"}).subir()
        cfg_cerebro(api, {"tipo": "anthropic", "modelo": "claude-sonnet-5-5"})
        dois_parecidos(api)
        r = api.post("/api/gestor/propostas/gerar", {})[1]
        assert r["criadas"] == 1 and r["propostas"][0]["origem"] == "regras"
    finally:
        llm.fechar()


def test_periodico_com_cerebro_sai_pelo_trabalhador(dados):
    from conftest import esperar
    resp = json.dumps({"propostas": [{"tipo": "faq", "perguntas": ["vocês entregam em Curitiba?"], "resposta": RESP,
                                      "justificativa": "repetido", "exemplos": []}]})
    llm = FalsoLLM(lambda corpo: resp if "propostas" in json.dumps(corpo) else "SEM_RESPOSTA")
    try:
        api = Servidor(dados, env={"CEREBRO_API_KEY": "sk-falsa", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"}).subir()
        cfg_cerebro(api, {"tipo": "anthropic", "modelo": "claude-sonnet-5-5"}, extra={"aprendizado": {"periodo": "diario"}})
        dois_parecidos(api)
        api.avancar(dias=1)
        assert esperar(lambda: propostas(api), timeout=6)
        assert propostas(api)[0]["origem"] == "cerebro"
    finally:
        llm.fechar()
