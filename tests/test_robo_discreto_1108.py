"""1.10.8: o robô só conta que chamou alguém quando o cliente pede; necessidade → avisa e segue;
chance de venda → chama a equipe sem dizer ao cliente (chamado silencioso)."""
from conftest import CODIGOS, TEL, ok

DIG = "5541999990001"


def revela(txt):
    t = txt.lower()
    return any(x in t for x in ("chamar", "chamei", "avisei a equipe", "equipe", "alguém da", "atender agora"))


def chamados(api, lead_id):
    return api.chamados_do_lead(lead_id)


def test_venda_abre_calada_e_a_equipe_recebe(api):
    api.status("ana", "livre")
    r = api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert "R$ 1.200" in txt and not revela(txt)
    assert "Para quando" in txt                                   # segue a conversa normal
    c = chamados(api, r["lead"]["id"])
    assert len(c) == 1 and c[0]["motivo"] == "venda" and c[0]["silencioso"] is True
    assert c[0]["ofertado_a"] == "ana"                            # a equipe foi chamada
    st, eu = api.get("/api/equipe/eu", codigo=CODIGOS["ana"])
    assert eu["ofertas"][0]["silencioso"] is True                 # o atendente sabe que o cliente não sabe
    assert not revela(api.textos_para(DIG))


def test_conversa_segue_sem_abrir_outro_chamado(api):
    r = api.msg_full(TEL, "quero comprar o plano anual", nome="Maria Souza")
    lid = r["lead"]["id"]
    txt = api.msg(TEL, "1")                                       # para quando: hoje
    assert not revela(txt)
    assert not revela(api.msg(TEL, "qual o valor?"))
    api.msg(TEL, "onde fica a loja de vocês?")                    # FAQ normal
    c = chamados(api, lid)
    assert len(c) == 1 and c[0]["silencioso"] is True and c[0]["prioridade"] == "quente"


def test_cliente_pede_pessoa_e_ai_o_robo_conta(api):
    r = api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    lid = r["lead"]["id"]
    txt = api.msg(TEL, "tem alguém aí?")
    assert "já chamei alguém da equipe" in txt and "sigo com você" in txt
    c = chamados(api, lid)
    assert len(c) == 1 and c[0]["silencioso"] is False
    assert "Eu já avisei a equipe" in api.msg(TEL, "ok")        # daí em diante, a espera normal


def test_reclamacao_durante_venda_calada_avisa_sem_novo_chamado(api):
    r = api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    lid = r["lead"]["id"]
    txt = api.msg(TEL, "o produto que comprei veio com defeito")
    assert "avisei a equipe" in txt.lower()
    c = chamados(api, lid)
    assert len(c) == 1 and c[0]["silencioso"] is False


def test_pediu_humano_avisa_e_continua(api):
    r = api.msg_full(TEL, "quero falar com um atendente", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert "já chamei alguém da equipe" in txt and "pode perguntar" in txt
    assert "seg a sex" in api.msg(TEL, "qual o horário de vocês?")  # e responde enquanto espera


def test_robo_nao_avisa_espera_de_chamado_calado(api):
    st, cfg = api.get("/api/gestor/config")
    cfg["robo"] = {"assume_espera": True, "apos_min": 2}
    assert ok(api.put("/api/gestor/config", cfg)[0])
    api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    api.avancar(5)
    assert "Nossa equipe está ocupada" not in api.textos_para(DIG)


def test_assumir_venda_calada_apresenta_o_atendente(api):
    r = api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    ch = chamados(api, r["lead"]["id"])[0]["id"]
    api.status("ana", "livre")
    assert ok(api.assumir("ana", ch)[0])
    assert "vai te atender agora" in api.textos_para(DIG)       # a passagem natural continua


def test_venda_fora_do_horario_nao_fala_em_horario_da_equipe(api):
    api.relogio("2026-11-08T22:00")                                # domingo à noite
    r = api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert "fora do horário" not in txt and not revela(txt)
    assert chamados(api, r["lead"]["id"])[0]["silencioso"] is True


def test_frases_novas_nao_contam_como_conversa_do_robo(api):
    lead, ch = api.abrir()                                         # "Certo, já chamei alguém…"
    api.avancar(1)
    api.msg(TEL, "ok")                                             # "Eu já avisei a equipe…"
    api.avancar(4)
    api.status("ana", "livre")
    assert ok(api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "ana"})[0])
    t = api.chamado_aberto(lead["id"])["tempos"]
    assert t["robo_msgs"] == 0



# ---------- alerta de cliente quente ----------

def test_painel_mostra_nota_e_silencioso_na_fila(api):
    api.msg_full(TEL, "quanto custa o plano anual?", nome="Maria Souza")
    f = api.fila()[0]
    assert f["nota"] == "quente" and f["prioridade"] == "quente" and f["silencioso"] is True
    assert "telefone" not in f


def test_bip_quente_configuravel(api):
    st, eu = api.get("/api/equipe/eu", codigo=CODIGOS["ana"])
    assert eu["alertas"] == {"bip_quente": False, "bip_s": 20}
    st, cfg = api.get("/api/gestor/config")
    cfg["alertas"] = {"bip_quente": True, "bip_s": 15}
    assert ok(api.put("/api/gestor/config", cfg)[0])
    st, eu = api.get("/api/equipe/eu", codigo=CODIGOS["ana"])
    assert eu["alertas"] == {"bip_quente": True, "bip_s": 15}
    for ruim in ({"bip_quente": "sim"}, {"bip_quente": True, "bip_s": 2}, {"bip_quente": True, "bip_s": True}):
        cfg["alertas"] = ruim
        assert api.put("/api/gestor/config", cfg)[0] == 422


# ---------- cadastro do atendente com aprovação do gestor ----------

def perfil(api, cid):
    st, r = api.get("/api/equipe/perfil", codigo=CODIGOS[cid])
    assert st == 200, r
    return r


def test_atendente_pede_e_gestor_aprova(api):
    st, r = api.post("/api/equipe/perfil", {"nome": "Ana Paula", "telefone": "(41) 98888-7777"}, codigo=CODIGOS["ana"])
    assert ok(st) and r["aplicado"] is False and r["pendente"]["dados"] == {"nome": "Ana Paula", "telefone": "5541988887777"}
    assert perfil(api, "ana")["nome"] != "Ana Paula"                     # ainda não mudou
    st, v = api.get("/api/gestor/ao-vivo")
    assert v["perfis_pendentes"] == 1
    st, ls = api.get("/api/gestor/perfis")
    assert [x["colaborador"] for x in ls] == ["ana"] and ls[0]["atual"]["nome"]
    st, ls = api.post(f"/api/gestor/perfis/{ls[0]['id']}", {"aprovar": True})
    assert ok(st) and ls == []
    p = perfil(api, "ana")
    assert p["nome"] == "Ana Paula" and p["telefone"] == "5541988887777" and p["pendente"] is None
    assert p["ultimo"]["status"] == "aprovado"
    st, cfg = api.get("/api/gestor/config")
    m = next(x for x in cfg["equipe"] if x["id"] == "ana")
    assert m["nome"] == "Ana Paula" and m["codigo"] == CODIGOS["ana"]      # código intacto: ela continua entrando
    assert api.get("/api/equipe/eu", codigo=CODIGOS["ana"])[0] == 200


def test_gestor_recusa_com_motivo(api):
    api.post("/api/equipe/perfil", {"nome": "Aninha"}, codigo=CODIGOS["ana"])
    pid = api.get("/api/gestor/perfis")[1][0]["id"]
    assert ok(api.post(f"/api/gestor/perfis/{pid}", {"aprovar": False, "motivo": "use o nome completo"})[0])
    p = perfil(api, "ana")
    assert p["nome"] != "Aninha" and p["ultimo"]["status"] == "recusado" and p["ultimo"]["motivo"] == "use o nome completo"
    assert api.post(f"/api/gestor/perfis/{pid}", {"aprovar": True})[0] == 409   # já decidido


def test_perfil_sem_aprovacao_vale_na_hora(api):
    st, cfg = api.get("/api/gestor/config")
    cfg["permissoes"] = {"perfil_sem_aprovacao": True}
    assert ok(api.put("/api/gestor/config", cfg)[0])
    st, r = api.post("/api/equipe/perfil", {"nome": "Ana Paula"}, codigo=CODIGOS["ana"])
    assert ok(st) and r["aplicado"] is True and r["nome"] == "Ana Paula"
    assert api.get("/api/gestor/perfis")[1] == []


def test_perfil_validacoes(api):
    assert api.post("/api/equipe/perfil", {"nome": "  "}, codigo=CODIGOS["ana"])[0] == 422
    assert api.post("/api/equipe/perfil", {"telefone": "123"}, codigo=CODIGOS["ana"])[0] == 422
    atual = perfil(api, "ana")["nome"]
    assert api.post("/api/equipe/perfil", {"nome": atual}, codigo=CODIGOS["ana"])[0] == 422    # nada mudou
    # código e id não mudam por aqui (campos ignorados → nada mudou)
    assert api.post("/api/equipe/perfil", {"codigo": "x" * 20, "id": "outra"}, codigo=CODIGOS["ana"])[0] == 422
    assert api.get("/api/equipe/perfil", token=None)[0] == 401
    assert api.get("/api/gestor/perfis", codigo=CODIGOS["ana"], token=None)[0] in (401, 403)
    assert api.post("/api/gestor/perfis/999", {"aprovar": True})[0] == 404


def test_novo_pedido_substitui_o_pendente_e_da_para_cancelar(api):
    api.post("/api/equipe/perfil", {"nome": "Ana A"}, codigo=CODIGOS["ana"])
    api.post("/api/equipe/perfil", {"nome": "Ana B"}, codigo=CODIGOS["ana"])
    ls = api.get("/api/gestor/perfis")[1]
    assert len(ls) == 1 and ls[0]["dados"]["nome"] == "Ana B"
    st, r = api.req("DELETE", "/api/equipe/perfil", codigo=CODIGOS["ana"])
    assert ok(st) and r["pendente"] is None and api.get("/api/gestor/perfis")[1] == []
