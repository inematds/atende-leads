"""1.8.8: Ao vivo/Hoje em quatro grupos (robô, espera, atendimento, encerrados), resposta atrasada e filtros da lista."""
from conftest import CODIGOS, TEL, ok

TEL_B = "(41) 99999-0002"
TEL_C = "(41) 99999-0003"


def vivo(api):
    st, r = api.get("/api/gestor/ao-vivo")
    assert st == 200, (st, r)
    return r


def responder(api, cid, ch, texto="Oi, tudo bem?"):
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": texto}, codigo=CODIGOS[cid])
    assert ok(st), (st, r)


def test_quatro_grupos_no_ao_vivo(api):
    api.status("ana", "livre")
    api.msg(TEL_B, "oi, qual o horário?", nome="Bia")          # só o robô
    _, ch = api.atendendo("ana", TEL, "Maria Souza")            # em atendimento
    api.abrir(TEL_C, "Caio Lima")                                # na espera (ana já está atendendo)
    r = vivo(api)
    assert {"robo", "espera", "atendendo", "encerrados", "sem_resposta"} <= set(r)
    assert [x["nome"] for x in r["robo"]] == ["Bia"]
    assert r["robo"][0]["telefone"] and "lead_id" in r["robo"][0]
    assert [x["lead_nome"] for x in r["atendendo"]] == ["Maria Souza"]
    assert [x["lead_nome"] for x in r["espera"]] == ["Caio Lima"]
    assert r["fila"][0]["telefone"] and r["fila"][0]["lead_nome"] == "Caio Lima"
    assert r["encerrados"] == []
    st, _ = api.fechar("ana", ch, {"resultado": "negociando"})
    assert ok(st)
    r = vivo(api)
    assert [x["id"] for x in r["encerrados"]] == [ch] and r["encerrados"][0]["resultado"] == "negociando"
    assert "Maria Souza" not in [x["nome"] for x in r["robo"]]   # fechou e ela não falou de novo


def test_encerrado_volta_para_o_robo_e_ele_responde(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    api.avancar(5)
    resp = api.msg(TEL, "qual o horário de vocês?")
    assert resp.strip()                                          # o agente voltou a responder
    r = vivo(api)
    assert lead["id"] in [x["lead_id"] for x in r["robo"]]


def test_robo_some_depois_de_24h(api):
    api.msg(TEL_B, "oi", nome="Bia")
    assert vivo(api)["robo"]
    api.avancar(24 * 60 + 1)
    assert vivo(api)["robo"] == []
    st, cfg = api.get("/api/gestor/config")
    cfg["prazos"]["conversa_ativa_h"] = 48
    assert ok(api.put("/api/gestor/config", cfg)[0])
    assert [x["nome"] for x in vivo(api)["robo"]] == ["Bia"]


def test_sem_resposta_no_atendimento(api):
    api.status("ana", "livre")
    _, ch = api.atendendo("ana")
    responder(api, "ana", ch)
    assert vivo(api)["atendendo"][0]["sem_resposta_min"] is None
    api.avancar(1)
    api.msg(TEL, "e o preço?")
    api.avancar(4)
    api.msg(TEL, "alô?")
    r = vivo(api)
    assert r["atendendo"][0]["sem_resposta_min"] == 4             # conta da 1ª sem resposta
    assert r["sem_resposta"] == []                                 # extremo padrão = 10 min
    api.avancar(7)
    r = vivo(api)
    assert [x["id"] for x in r["sem_resposta"]] == [ch] and r["sem_resposta"][0]["sem_resposta_min"] == 11
    st, h = api.get("/api/gestor/hoje")
    assert [x["id"] for x in h["grupos"]["sem_resposta"]] == [ch]
    responder(api, "ana", ch, "Desculpa a demora!")
    r = vivo(api)
    assert r["sem_resposta"] == [] and r["atendendo"][0]["sem_resposta_min"] is None


def test_hoje_tem_os_grupos(api):
    api.status("ana", "livre")
    api.msg(TEL_B, "oi", nome="Bia")
    api.atendendo("ana")
    st, h = api.get("/api/gestor/hoje")
    g = h["grupos"]
    assert len(g["robo"]) == 1 and len(g["atendendo"]) == 1 and g["espera"] == [] and g["encerrados"] == []


def test_leads_situacao_e_filtros(api):
    api.status("ana", "livre")
    api.msg(TEL_B, "oi", nome="Bia")
    api.atendendo("ana")
    api.abrir(TEL_C, "Caio Lima")
    st, ls = api.get("/api/gestor/leads")
    sit = {x["nome"]: x["situacao"] for x in ls}
    assert sit == {"Bia": "robo", "Maria Souza": "atendendo", "Caio Lima": "espera"}
    st, ls = api.get("/api/gestor/leads?situacao=espera")
    assert [x["nome"] for x in ls] == ["Caio Lima"]
    assert all(x["minutos_desde_contato"] is not None for x in ls)
    api.avancar(90)
    api.msg(TEL_B, "ainda estou aqui")
    st, ls = api.get("/api/gestor/leads?contato=1h")
    assert [x["nome"] for x in ls] == ["Bia"]
    st, ls = api.get("/api/gestor/leads?contato=24h")
    assert len(ls) == 3
    api.avancar(dias=3)
    st, ls = api.get("/api/gestor/leads?contato=1a7d")
    assert len(ls) == 3
    st, ls = api.get("/api/gestor/leads?contato=mais7d")
    assert ls == []
    st, ls = api.get("/api/gestor/leads?situacao=robo")
    assert ls == []                                              # passou de 24 h: Bia saiu da conversa ativa


# ---- achados do revisor independente (1.8.8)

def test_assumido_sem_nenhuma_resposta_conta_do_assumir(api):
    api.status("ana", "livre")
    _, ch = api.abrir()
    api.avancar(2)
    assert ok(api.assumir("ana", ch)[0])
    api.avancar(15)                                              # ninguém escreveu nada, cliente calado
    r = vivo(api)
    assert r["atendendo"][0]["sem_resposta_min"] == 15
    assert [x["id"] for x in r["sem_resposta"]] == [ch]


def test_lead_apagado_nao_mostra_telefone_nem_fica_no_robo(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.msg(TEL, "apagar meus dados")
    r = vivo(api)
    assert r["atendendo"] == [] and r["robo"] == []
    assert all(not str(x["telefone"]).startswith("55") for x in r["encerrados"])


def test_reaberto_sai_de_encerradas_e_volta_para_espera(api):
    api.status("ana", "livre")
    _, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    assert [x["id"] for x in vivo(api)["encerrados"]] == [ch]
    assert ok(api.post(f"/api/gestor/chamados/{ch}/reabrir")[0])
    r = vivo(api)
    assert r["encerrados"] == [] and [x["id"] for x in r["espera"]] == [ch]


def test_lead_escreve_no_mesmo_minuto_do_fechamento(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    api.msg(TEL, "ah, mais uma coisa: qual o horário?")       # mesmo minuto do fechamento
    assert lead["id"] in [x["lead_id"] for x in vivo(api)["robo"]]


def test_painel_da_equipe_continua_sem_telefone(api):
    api.status("ana", "livre")
    api.abrir()
    st, p = api.get("/api/painel", codigo=CODIGOS["carla"])
    assert st == 200 and p["fila"]
    assert all("telefone" not in f for f in p["fila"])
    assert "robo" not in p and "encerrados" not in p
