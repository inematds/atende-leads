"""1.9.8: retomar contato, bloqueio "não quer contato", gestor passa conversa do robô, robô cobre, tempos classificados."""
from conftest import CODIGOS, TEL, ok

TEL_B = "(41) 99999-0002"


def eu(api, cid):
    st, r = api.get("/api/equipe/eu", codigo=CODIGOS[cid])
    assert st == 200, (st, r)
    return r


def responder(api, cid, ch, texto="Oi! Como posso ajudar?"):
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": texto}, codigo=CODIGOS[cid])
    assert ok(st), (st, r)


def fechar(api, cid, ch, corpo=None):
    st, r = api.fechar(cid, ch, corpo or {"resultado": "negociando"})
    assert ok(st), (st, r)


# ---------- retomar ----------

def test_retomar_contato_encerrado(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch)
    st, r = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert ok(st), (st, r)
    assert r["status"] == "atendendo" and r["dono"] == "ana" and r["motivo"] == "retomada" and r["id"] != ch
    assert [c["id"] for c in eu(api, "ana")["chamados"]] == [r["id"]]
    responder(api, "ana", r["id"], "Oi, Maria! Passando para saber se decidiu.")
    assert "Oi, Maria" in api.textos_para("5541999990001")


def test_retomar_bloqueado_quando_nao_quer_contato(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch, {"resultado": "sem_interesse", "motivo": "nao_quer_contato"})
    st, r = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert st == 409 and "não ser mais contatado" in r.get("erro", "")
    st, cs = api.get("/api/equipe/contatos", codigo=CODIGOS["ana"])
    assert cs[0]["nao_contatar"] is True
    api.msg(TEL, "oi, voltei")                                  # o próprio cliente voltou: libera de novo
    st, r = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert ok(st), (st, r)


def test_retomar_pelo_parar(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch)
    api.msg(TEL, "parar")
    st, _ = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert st == 409


def test_retomar_so_quem_atendeu(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch)
    api.status("bruno", "livre")
    st, _ = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["bruno"])
    assert st == 403


def test_retomar_com_outro_atendendo_409(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch)
    api.status("bruno", "livre")
    st, _ = api.post(f"/api/gestor/leads/{lead['id']}/atribuir", {"colaborador": "bruno"})
    assert ok(st)
    st, r = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert st == 409 and "Bruno" in r.get("erro", "")


# ---------- gestor passa conversa do robô ----------

def test_gestor_passa_conversa_do_robo(api):
    api.status("bruno", "livre")
    r = api.msg_full(TEL_B, "oi, qual o horário?", nome="Bia")
    lid = r["lead"]["id"]
    st, ch = api.post(f"/api/gestor/leads/{lid}/atribuir", {"colaborador": "bruno"})
    assert ok(st), (st, ch)
    assert ch["status"] == "atendendo" and ch["dono"] == "bruno" and ch["motivo"] == "gestor"
    assert "Bruno vai te atender agora" in api.textos_para("5541999990002")
    st, av = api.get("/api/gestor/ao-vivo")
    assert av["robo"] == [] and [x["id"] for x in av["atendendo"]] == [ch["id"]]


def test_gestor_atribui_quem_esta_fora_409(api):
    r = api.msg_full(TEL_B, "oi", nome="Bia")
    st, _ = api.post(f"/api/gestor/leads/{r['lead']['id']}/atribuir", {"colaborador": "carla"})
    assert st == 409


def test_atribuir_chamado_na_fila_transfere(api):
    api.status("ana", "livre")
    lead, ch = api.abrir()
    api.status("bruno", "livre")
    st, r = api.post(f"/api/gestor/leads/{lead['id']}/atribuir", {"colaborador": "bruno"})
    assert ok(st) and r["id"] == ch and r["dono"] == "bruno"


# ---------- robô cobre ----------

def test_robo_responde_por_mim(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert eu(api, "ana")["robo_por_mim"] is False
    assert api.msg(TEL, "qual o horário de vocês?") == ""          # atendente responde, o robô fica quieto
    st, r = api.post("/api/equipe/robo", {"ativo": True}, codigo=CODIGOS["ana"])
    assert ok(st) and r["robo_por_mim"] is True
    resp = api.msg(TEL, "qual o horário de vocês?")
    assert resp.strip()                                             # agora o robô responde
    assert "Ana já vai te responder" in api.msg(TEL, "tá bom, e aí")  # sem resposta pronta: avisa que a Ana responde
    st, p = api.get("/api/painel", codigo=CODIGOS["carla"])
    assert next(e for e in p["equipe"] if e["id"] == "ana")["robo_por_mim"] is True
    st, _ = api.post("/api/gestor/equipe/ana/robo", {"ativo": False})
    assert ok(st) and api.msg(TEL, "qual o horário de vocês?") == ""


def test_robo_assume_espera_configuravel(api):
    st, cfg = api.get("/api/gestor/config")
    cfg["robo"] = {"assume_espera": True, "apos_min": 5}
    assert ok(api.put("/api/gestor/config", cfg)[0])
    lead, ch = api.abrir()                                           # ninguém livre
    api.avancar(4)
    assert "Nossa equipe está ocupada" not in api.textos_para("5541999990001")
    api.avancar(1)
    assert api.textos_para("5541999990001").count("Nossa equipe está ocupada") == 1
    api.avancar(3)
    assert api.textos_para("5541999990001").count("Nossa equipe está ocupada") == 1   # avisa uma vez
    assert "Sigo por aqui com você" in api.msg(TEL, "ok")


def test_robo_config_invalida_422(api):
    st, cfg = api.get("/api/gestor/config")
    cfg["robo"] = {"assume_espera": "sim"}
    assert api.put("/api/gestor/config", cfg)[0] == 422
    cfg["robo"] = {"assume_espera": True, "apos_min": 0}
    assert api.put("/api/gestor/config", cfg)[0] == 422


# ---------- tempos classificados ----------

def test_tempos_classificados(api):
    lead, ch = api.abrir()                                # 10:00 abre (robô: "vou chamar alguém")
    api.avancar(2)
    api.msg(TEL, "qual o horário de vocês?")              # 10:02 robô responde na hora
    api.avancar(3)
    api.msg(TEL, "ok")                                    # 10:05 "Eu já avisei a equipe" (robô)
    api.avancar(1)
    api.msg(TEL, "alguém?")                               # 10:06
    api.avancar(4)                                        # 10:10 ana assume
    api.status("ana", "livre")
    assert ok(api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "ana"})[0])
    api.avancar(2)
    responder(api, "ana", ch)                             # 1ª resposta 2 min depois
    t = api.chamado_aberto(lead["id"])["tempos"]
    assert t["espera_min"] == 10 and t["primeira_resposta_min"] == 2
    assert t["robo_msgs"] == 1                            # só a do horário; "Eu já avisei" é frase pronta
    assert t["espera_sem_resposta_min"] == 5              # "ok" das 10:05 sem resposta de verdade até assumir às 10:10
    assert t["espera_min"] == t["espera_sem_resposta_min"] + t["espera_robo_min"] + t["espera_silencio_min"]
    st, h = api.get("/api/gestor/hoje")
    assert h["tempos"]["primeira_resposta_media_min"] == 2


def test_eu_minhas_conversas_com_sem_resposta(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.avancar(3)
    c = eu(api, "ana")["chamados"][0]
    assert c["sem_resposta_min"] == 3 and c["ultima_msg_lead"] > 0 and "tempos" in c


def test_painel_equipe_mostra_quem_atende_sem_telefone(api):
    api.status("ana", "livre")
    api.atendendo("ana")
    st, p = api.get("/api/painel", codigo=CODIGOS["carla"])
    assert [(a["lead"], a["dono"]) for a in p["atendendo"]] == [("Maria", "ana")]
    assert all("telefone" not in a for a in p["atendendo"])


# ---------- achados do revisor independente (1.9.8) ----------

def test_frase_pronta_nao_conta_como_conversa_do_robo(api):
    lead, ch = api.abrir()                                # ninguém livre; robô: "vou chamar alguém" (pronta)
    api.avancar(1)
    api.msg(TEL, "ok")                                    # 10:01 "Eu já avisei a equipe" (pronta)
    api.avancar(9)                                        # 10:10
    api.status("ana", "livre")
    assert ok(api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "ana"})[0])
    t = api.chamado_aberto(lead["id"])["tempos"]
    assert t["robo_msgs"] == 0 and t["espera_robo_min"] == 0
    assert t["espera_sem_resposta_min"] == 9               # o "ok" das 10:01 ficou sem resposta de verdade
    assert t["espera_silencio_min"] == 1
    assert t["espera_min"] == t["espera_sem_resposta_min"] + t["espera_robo_min"] + t["espera_silencio_min"]


def test_robo_por_mim_nao_repete_anotei(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert ok(api.post("/api/equipe/robo", {"ativo": True}, codigo=CODIGOS["ana"])[0])
    assert api.msg(TEL, "obrigado") == ""                         # uma palavra: nada
    assert "Anotei!" in api.msg(TEL, "e aí, tudo certo")
    assert api.msg(TEL, "tudo certo então") == ""                  # já avisou nos últimos 30 min
    api.avancar(31)
    assert "Anotei!" in api.msg(TEL, "tudo certo então")


def test_gestor_nao_atribui_quem_nao_quer_contato(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch, {"resultado": "sem_interesse", "motivo": "nao_quer_contato"})
    st, r = api.post(f"/api/gestor/leads/{lead['id']}/atribuir", {"colaborador": "ana"})
    assert st == 409 and "não ser mais contatado" in r.get("erro", "")


def test_retomada_fora_das_metricas_de_assumir(api):
    api.status("ana", "livre")
    lead, ch = api.abrir()
    api.avancar(4)
    assert ok(api.assumir("ana", ch)[0])
    fechar(api, "ana", ch)
    st, h0 = api.get("/api/gestor/hoje")
    assert ok(api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])[0])
    st, h1 = api.get("/api/gestor/hoje")
    assert h1["assumidos"] == h0["assumidos"] and h1["tempo_medio_assumir_min"] == h0["tempo_medio_assumir_min"] == 4


def test_retomar_nao_tira_oferta_de_colega(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    fechar(api, "ana", ch)
    api.status("ana", "ocupado")
    api.status("bruno", "livre")
    api.msg(TEL, "quero falar com um atendente")                   # nova oferta vai para o Bruno
    api.status("ana", "livre")
    st, r = api.post(f"/api/equipe/leads/{lead['id']}/retomar", {}, codigo=CODIGOS["ana"])
    assert st == 409 and "Bruno" in r.get("erro", "")
