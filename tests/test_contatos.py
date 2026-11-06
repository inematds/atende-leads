"""Seções 12 e 13 (1.3.4): meus contatos, ordem por nível, novas/vistos, tempos do lead, aba Hoje e faixas."""
from conftest import AGORA, CODIGOS, equipe_pronta, mais, ok


def fone(n):
    return f"(41) 99100-{n:04d}"


def contatos(api, cid, status=None):
    rota = "/api/equipe/contatos" + (f"?status={status}" if status else "")
    st, r = api.get(rota, codigo=CODIGOS[cid])
    assert st == 200, (st, r)
    assert isinstance(r, list), r
    return r


def novo_chamado(api, n, nome, texto="quero falar com um atendente"):
    r = api.msg_full(fone(n), texto, nome=nome)
    return r["lead"]["id"], api.chamado_aberto(r["lead"]["id"])["id"]


def atende_e_fecha(api, cid, n, nome, corpo):
    lead, ch = novo_chamado(api, n, nome)
    st, r = api.assumir(cid, ch)
    assert ok(st), (st, r)
    if corpo == "devolver":
        st, r = api.post(f"/api/equipe/chamados/{ch}/devolver", codigo=CODIGOS[cid])
    else:
        st, r = api.fechar(cid, ch, corpo)
    assert ok(st), (st, r)
    api.relogio(mais(api.agora, 1))
    return lead


def cenario_niveis(api):
    """Só a Ana na equipe; um lead por nível (e dois perdidos para o desempate por ultimo_contato)."""
    equipe_pronta(api, quem=("ana",))
    L = {}
    L["ret2"] = atende_e_fecha(api, "ana", 2, "Bia Dois", {"resultado": "retornar", "retornar_em": mais(AGORA, dias=2)})
    L["ret1"] = atende_e_fecha(api, "ana", 3, "Caio Tres", {"resultado": "retornar", "retornar_em": mais(AGORA, dias=1)})
    L["neg"] = atende_e_fecha(api, "ana", 4, "Davi Quatro", {"resultado": "negociando"})
    L["dev"] = atende_e_fecha(api, "ana", 6, "Eva Seis", "devolver")
    L["ganho"] = atende_e_fecha(api, "ana", 7, "Fabio Sete", {"resultado": "vendeu", "valor": 10})
    L["perd_a"] = atende_e_fecha(api, "ana", 8, "Gil Oito", {"resultado": "sem_interesse", "motivo": "preco"})
    L["inv"] = atende_e_fecha(api, "ana", 9, "Hugo Nove", {"resultado": "invalido", "motivo": "spam"})
    L["perd_b"] = atende_e_fecha(api, "ana", 10, "Iris Dez", {"resultado": "sem_interesse", "motivo": "curioso"})
    # novo com chamado ofertado à Ana (ainda não assumido) e, depois, um em atendimento
    L["novo_ab"], _ = novo_chamado(api, 5, "Joao Cinco")
    api.relogio(mais(api.agora, 1))
    L["atend"], ch = novo_chamado(api, 1, "Lia Um")
    st, r = api.assumir("ana", ch)
    assert ok(st), (st, r)
    ordem = ["atend", "ret1", "ret2", "neg", "novo_ab", "dev", "ganho", "perd_b", "perd_a", "inv"]
    return [L[k] for k in ordem], L


def test_contatos_ordem_por_nivel_e_campos(api):
    esperado, L = cenario_niveis(api)
    cs = contatos(api, "ana")
    assert [c["id"] for c in cs] == esperado
    por = {c["id"]: c for c in cs}
    campos = {"id", "nome", "telefone", "status", "nota", "interesse", "ultimo_contato", "ultima_mensagem", "novas",
              "retornar_em", "chamado_aberto", "minutos_conversa", "dias_contato", "dia_anterior"}
    for c in cs:
        assert campos <= set(c), c
    assert por[L["ret1"]]["retornar_em"] == mais(AGORA, dias=1)
    assert por[L["neg"]]["retornar_em"] is None
    assert por[L["novo_ab"]]["status"] == "novo" and por[L["novo_ab"]]["chamado_aberto"]
    assert por[L["dev"]]["status"] == "novo" and por[L["dev"]]["chamado_aberto"] is None
    assert por[L["atend"]]["chamado_aberto"]
    assert por[L["neg"]]["ultima_mensagem"] == "quero falar com um atendente"
    assert all(c["novas"] == 0 for c in cs)


def test_contatos_filtro_status(api):
    _, L = cenario_niveis(api)
    cs = contatos(api, "ana", "perdido")
    assert [c["id"] for c in cs] == [L["perd_b"], L["perd_a"]]
    assert [c["id"] for c in contatos(api, "ana", "retornar")] == [L["ret1"], L["ret2"]]


def test_gestor_leads_na_ordem_por_nivel(api):
    esperado, L = cenario_niveis(api)
    st, ls = api.get("/api/gestor/leads")
    assert st == 200
    assert [x["id"] for x in ls] == esperado
    st, ls = api.get("/api/gestor/leads?status=perdido")
    assert [x["id"] for x in ls] == [L["perd_b"], L["perd_a"]]
    st, ls = api.get("/api/gestor/leads?colaborador=ana&status=retornar")
    assert [x["id"] for x in ls] == [L["ret1"], L["ret2"]]
    assert {"minutos_conversa", "dias_contato", "dia_anterior", "retornar_em", "chamado_aberto"} <= set(ls[0])


def test_devolvido_escreve_aparece_com_nova_e_ficha_zera(api):
    """O caso do dono: devolveu ao bot, a lead escreveu no MESMO minuto e nada aparecia."""
    equipe_pronta(api, quem=("ana", "bruno"))
    lead, ch = api.atendendo("ana", telefone=fone(20), nome="Maria Souza")
    lead = lead["id"]
    st, _ = api.post(f"/api/equipe/chamados/{ch}/devolver", codigo=CODIGOS["ana"])
    assert ok(st)
    assert contatos(api, "ana")[0]["novas"] == 0
    api.msg(fone(20), "oi, voltei com uma dúvida")          # mesmo minuto do devolver
    c = next(x for x in contatos(api, "ana") if x["id"] == lead)
    assert c["novas"] == 1 and c["status"] == "novo"
    assert c["ultima_mensagem"] == "oi, voltei com uma dúvida"
    # o painel "eu" não tem chamado aberto: só a lista de contatos mostra o lead
    assert api.eu("ana")["chamados"] == []
    st, f = api.get(f"/api/equipe/leads/{lead}", codigo=CODIGOS["ana"])
    assert st == 200
    assert any(m["texto"] == "oi, voltei com uma dúvida" for m in f["mensagens"])
    assert next(x for x in contatos(api, "ana") if x["id"] == lead)["novas"] == 0
    # o gestor abrir a ficha não zera as novas da Ana
    api.msg(fone(20), "alguém aí?")
    api.ficha(lead)
    assert next(x for x in contatos(api, "ana") if x["id"] == lead)["novas"] == 1


def test_lead_devolvido_que_pede_humano_volta_ao_antigo_dono(api):
    equipe_pronta(api, quem=("ana", "bruno"))
    lead, ch = api.atendendo("ana", telefone=fone(21), nome="Maria Souza")
    api.relogio(mais(api.agora, 5))
    st, _ = api.post(f"/api/equipe/chamados/{ch}/devolver", codigo=CODIGOS["ana"])
    assert ok(st)
    # Ana voltou a livre agora: Bruno é o primeiro da vez, mas o lead volta para a Ana
    assert api.colab("bruno")["proximo"]
    api.relogio(mais(api.agora, 1))
    api.msg(fone(21), "quero falar com um atendente")
    novo = api.chamado_aberto(lead["id"])
    assert novo["id"] != ch and novo["ofertado_a"] == "ana"
    c = next(x for x in contatos(api, "ana") if x["id"] == lead["id"])
    assert c["chamado_aberto"] == novo["id"] and c["novas"] == 1


def test_colaborador_nao_ve_contatos_de_outro(api):
    equipe_pronta(api, quem=("ana", "bruno"))
    la, _ = api.atendendo("ana", telefone=fone(30), nome="Ana Lead")
    lb, _ = api.atendendo("bruno", telefone=fone(31), nome="Bruno Lead")
    assert [c["id"] for c in contatos(api, "ana")] == [la["id"]]
    assert [c["id"] for c in contatos(api, "bruno")] == [lb["id"]]
    assert contatos(api, "carla") == []


def test_apagado_some_dos_contatos(api):
    equipe_pronta(api, quem=("ana",))
    lead, ch = api.atendendo("ana", telefone=fone(40), nome="Maria Souza")
    st, _ = api.post(f"/api/equipe/chamados/{ch}/devolver", codigo=CODIGOS["ana"])
    assert ok(st)
    assert [c["id"] for c in contatos(api, "ana")] == [lead["id"]]
    api.msg(fone(40), "apagar meus dados")
    assert contatos(api, "ana") == []


def test_tempos_conversa_desde_contato_e_outro_dia(api):
    equipe_pronta(api, quem=("ana",))
    api.relogio("2026-11-09T09:00")
    lead, ch = api.atendendo("ana", telefone=fone(50), nome="Maria Souza")
    api.relogio("2026-11-09T09:30")
    st, _ = api.fechar("ana", ch, {"resultado": "negociando"})
    assert ok(st)
    c = contatos(api, "ana")[0]
    assert c["minutos_conversa"] == 30 and c["dias_contato"] == 1 and c["dia_anterior"] is None
    # outro dia: a lead volta, pede atendente, Ana assume e está há 15 min com ela
    api.relogio("2026-11-10T10:00")
    api.status("ana", "livre")
    api.msg(fone(50), "quero falar com um atendente")
    st, _ = api.assumir("ana", api.chamado_aberto(lead["id"])["id"])
    assert ok(st)
    api.relogio("2026-11-10T10:15")
    c = contatos(api, "ana")[0]
    assert c["minutos_conversa"] == 45
    assert c["dias_contato"] == 2 and c["dia_anterior"] == "2026-11-09"
    assert c["minutos_desde_contato"] == 15
    api.relogio("2026-11-10T11:45")
    c = contatos(api, "ana")[0]
    assert c["minutos_desde_contato"] == 105 and c["minutos_conversa"] == 135
    # a ficha (equipe e gestor) traz os mesmos tempos
    st, f = api.get(f"/api/equipe/leads/{lead['id']}", codigo=CODIGOS["ana"])
    assert (f["lead"]["minutos_conversa"], f["lead"]["dias_contato"], f["lead"]["dia_anterior"]) == (135, 2, "2026-11-09")
    g = api.ficha(lead["id"])["lead"]
    assert (g["minutos_conversa"], g["dias_contato"], g["dia_anterior"]) == (135, 2, "2026-11-09")
    st, ls = api.get("/api/gestor/leads")
    assert (ls[0]["minutos_conversa"], ls[0]["dias_contato"], ls[0]["dia_anterior"]) == (135, 2, "2026-11-09")


# ---------------------------------------------------------------- aba Hoje

def _assume_depois(api, n, nome, espera):
    lead, ch = novo_chamado(api, n, nome)
    api.relogio(mais(api.agora, espera))
    st, r = api.assumir("ana", ch)
    assert ok(st), (st, r)
    st, r = api.fechar("ana", ch, {"resultado": "negociando"})
    assert ok(st), (st, r)
    return lead


def test_hoje_faixas_do_tempo_para_assumir(api):
    equipe_pronta(api, quem=("ana",))
    _assume_depois(api, 60, "Ana Imediata", 0)
    _assume_depois(api, 61, "Beto Imediato", 1)
    _assume_depois(api, 62, "Caio Medio", 5)
    _assume_depois(api, 63, "Duda Media", 10)
    _assume_depois(api, 64, "Eli Extremo", 15)
    st, h = api.get("/api/gestor/hoje")
    assert st == 200
    a = h["assumir"]
    assert (a["imediatos"], a["medios"], a["extremos"], a["maior_min"]) == (2, 2, 1, 15)
    assert a["media_min"] == h["tempo_medio_assumir_min"] == round((0 + 1 + 5 + 10 + 15) / 5, 1)
    ana = next(p for p in h["por_colaborador"] if p["id"] == "ana")
    assert (ana["assumir"]["imediatos"], ana["assumir"]["medios"], ana["assumir"]["extremos"]) == (2, 2, 1)
    bruno = next(p for p in h["por_colaborador"] if p["id"] == "bruno")
    assert bruno["assumir"]["maior_min"] == 0 and bruno["assumir"]["imediatos"] == 0
    # limites configuráveis: 5 e 12 → imediatos 0,1,5; médios 10; extremos 15
    st, cfg = api.get("/api/gestor/config")
    cfg["prazos"] = dict(cfg["prazos"], assumir_imediato_min=5, assumir_extremo_min=12)
    st, r = api.put("/api/gestor/config", cfg)
    assert st == 200, r
    a = api.get("/api/gestor/hoje")[1]["assumir"]
    assert (a["imediatos"], a["medios"], a["extremos"]) == (3, 1, 1)


def test_prazos_das_faixas_validados(api):
    st, base = api.get("/api/gestor/config")
    for ruim in ({"assumir_imediato_min": 10, "assumir_extremo_min": 5},
                 {"assumir_imediato_min": 10, "assumir_extremo_min": 10},
                 {"assumir_imediato_min": 0},
                 {"assumir_extremo_min": "10"},
                 {"assumir_imediato_min": 1.5},
                 {"assumir_imediato_min": 12}):        # maior que o extremo padrão (10)
        cfg = dict(base, prazos=dict(base["prazos"], **ruim))
        st, r = api.put("/api/gestor/config", cfg)
        assert st == 422, (ruim, st, r)
    assert api.get("/api/gestor/config")[1]["prazos"] == base["prazos"]
    cfg = dict(base, prazos=dict(base["prazos"], assumir_imediato_min=2, assumir_extremo_min=20))
    st, r = api.put("/api/gestor/config", cfg)
    assert st == 200, r
    a = api.get("/api/gestor/hoje")[1]["assumir"]
    assert (a["imediato_min"], a["extremo_min"]) == (2, 20)


def test_hoje_lista_abertos_agora_e_leads_de_hoje(api):
    # ontem (domingo): dois leads; só o Yuri volta hoje
    api.relogio("2026-11-08T10:00")
    y = api.msg_full(fone(70), "oi", nome="Yuri Ontem")["lead"]["id"]
    z = api.msg_full(fone(71), "oi", nome="Zeca Ontem")["lead"]["id"]
    api.relogio(AGORA)
    equipe_pronta(api, quem=("ana", "bruno"))
    api.msg(fone(70), "oi de novo")
    _, ch_at = api.atendendo("ana", telefone=fone(72), nome="Lia Atendida")
    api.relogio(mais(api.agora, 3))
    l_ag, ch_ag = novo_chamado(api, 73, "Rui Aguardando")       # ofertado ao Bruno
    st, h = api.get("/api/gestor/hoje")
    assert st == 200
    assert h["abertos_agora"] == 2
    ab = {c["id"]: c for c in h["chamados_abertos_agora"]}
    assert set(ab) == {ch_at, ch_ag}
    assert ab[ch_at]["status"] == "atendendo" and ab[ch_at]["dono"] == "ana" and ab[ch_at]["lead_nome"] == "Lia Atendida"
    assert ab[ch_ag]["status"] == "aguardando" and ab[ch_ag]["ofertado_a"] == "bruno"
    assert "nota" in ab[ch_ag] and "minutos" in ab[ch_ag]
    ids = [x["id"] for x in h["leads_hoje"]]
    assert y in ids and z not in ids and l_ag in ids
    # ordem por nível: em atendimento → novo com chamado aberto → novo sem
    assert ids.index(l_ag) < ids.index(y)
    assert h["leads_hoje"][0]["status"] == "em_atendimento"
    assert h["leads_novos"] == 2  # Lia e Rui (Yuri é de ontem)
