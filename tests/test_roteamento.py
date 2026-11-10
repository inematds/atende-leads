"""Seção 7: abrir chamado, linha no grupo, oferta privada, vencimento, passar, alerta, assumir."""
import threading

from conftest import (CODIGOS, GRUPO, TEL, TEL_D, TEL2, TEL2_D, TEL2_FMT, TG_ID, URL_PUBLICA, botoes, callbacks,
                      equipe_pronta, esperar, mais, ok, urls)


def oferta(externo, cid, ch):
    """Mensagem privada de oferta do chamado ch ao colaborador cid (a primeira)."""
    achou = {}

    def cond():
        ps = [p for p in externo.privado(cid) if f"#{ch}" in p["json"].get("text", "")
              and f"as:{ch}" in callbacks(p)]
        if ps:
            achou["p"] = ps[0]
        return bool(ps)

    assert esperar(cond), f"sem oferta de #{ch} para {cid}: {externo.textos(externo.privado(cid))}"
    return achou["p"]


def alertas(externo, ch):
    return [p for p in externo.enviadas(GRUPO) if p["json"].get("text", "").startswith("🚨")
            and f"#{ch}" in p["json"]["text"]]


def abrir_tel2(api, texto="quero falar com um atendente"):
    return api.abrir(TEL2, "Maria Souza", texto)


# ------------------------------------------------------------ linha do grupo

def test_linha_no_grupo_normal_sem_telefone(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: [p for p in externo.enviadas(GRUPO) if f"#{ch}" in p["json"].get("text", "")])
    linha = [p for p in externo.enviadas(GRUPO) if f"#{ch}" in p["json"]["text"]][0]["json"]["text"]
    assert linha.startswith("🙋")
    assert "Maria" in linha and "pediu humano" in linha and "→ Ana" in linha
    assert "8888" not in linha       # sem telefone no grupo
    assert "Souza" not in linha      # só o primeiro nome


def test_linha_no_grupo_quente_venda(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int, "quanto custa o plano anual?")
    assert esperar(lambda: [p for p in externo.enviadas(GRUPO) if f"#{ch}" in p["json"].get("text", "")])
    linha = [p for p in externo.enviadas(GRUPO) if f"#{ch}" in p["json"]["text"]][0]["json"]["text"]
    assert linha.startswith("🔥") and "chance de venda" in linha


def test_linha_no_grupo_precisa(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int, "meu produto veio com defeito")
    assert esperar(lambda: [p for p in externo.enviadas(GRUPO) if "precisa de atenção" in p["json"].get("text", "")
                            and f"#{ch}" in p["json"]["text"]])


# ------------------------------------------------------------ oferta privada

def test_oferta_privada_com_dados(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    api_int.msg_full(TEL2, "tenho interesse no plano anual", nome="Maria Souza")
    _, ch = abrir_tel2(api_int)
    txt = oferta(externo, "ana", ch)["json"]["text"]
    assert TEL2_FMT in txt
    assert "Maria" in txt and "morno" in txt and "Plano anual" in txt
    assert "tenho interesse no plano anual" in txt  # últimas mensagens
    assert "⏱ Sua vez até " in txt and "Maria Souza · cliente morno" in txt  # 1.12.8: prazo à vista, ficha curta
    assert "Motivo:" not in txt and "Nome:" not in txt
    assert not [p for p in externo.privado("bruno") if f"#{ch}" in p["json"].get("text", "")]


def test_oferta_botoes(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    p = oferta(externo, "ana", ch)
    cbs = callbacks(p)
    assert f"as:{ch}" in cbs and f"pa:{ch}" in cbs
    us = urls(p)
    assert any(u.startswith(f"{URL_PUBLICA}/ligar/") for u in us), us
    assert f"https://wa.me/{TEL2_D}" in us
    rotulos = " ".join(b.get("text", "") for b in botoes(p))
    for r in ("Assumir", "Passar", "Ligar", "WhatsApp"):
        assert r in rotulos
    assert all(len(c.encode()) <= 64 for c in cbs if c)


def test_ligar_redireciona_para_tel(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    u = [u for u in urls(oferta(externo, "ana", ch)) if "/ligar/" in u][0]
    token = u.rsplit("/ligar/", 1)[1]
    assert len(token) >= 16
    st, html = api_int.get(f"/ligar/{token}", token=None)
    assert st == 200
    assert f"tel:+{TEL2_D}" in html
    assert "refresh" in html.lower()
    assert api_int.get("/ligar/nao-existe-0000000000", token=None)[0] == 404


def test_oferta_vencida_vai_ao_proximo_e_edita(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    p_ana = oferta(externo, "ana", ch)
    api_int.avancar(3)
    oferta(externo, "bruno", ch)

    def editada():
        return [e for e in externo.tg("editMessageText", TG_ID["ana"])
                if e["json"].get("message_id") == p_ana["message_id"]
                and "passou para o próximo" in e["json"].get("text", "")]

    assert esperar(editada)
    e = editada()[-1]
    assert e["json"]["text"].startswith("⌛") and f"#{ch}" in e["json"]["text"]
    assert botoes(e) == []
    assert str(next(f for f in api_int.fila() if str(f["id"]) == str(ch))["ofertado_a"]) == "bruno"


def test_oferta_nao_vence_antes_do_prazo(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    oferta(externo, "ana", ch)
    api_int.avancar(1)
    assert next(f for f in api_int.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "ana"


def test_passar_pelo_botao(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    p = oferta(externo, "ana", ch)
    cbid = tg.cb(TG_ID["ana"], f"pa:{ch}", p["message_id"])
    oferta(externo, "bruno", ch)
    assert esperar(lambda: [a for a in externo.tg("answerCallbackQuery")
                            if a["json"].get("callback_query_id") == cbid])


# ------------------------------------------------------------ alerta

def test_alerta_normal_no_prazo(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    oferta(externo, "ana", ch)
    api_int.avancar(3)
    assert not alertas(externo, ch)
    api_int.avancar(3)  # 6 min > alerta_normal_min (5)
    assert esperar(lambda: alertas(externo, ch))
    a = alertas(externo, ch)[0]
    assert f"as:{ch}" in callbacks(a)
    assert "Maria" in a["json"]["text"] and "8888" not in a["json"]["text"]
    assert next(f for f in api_int.fila() if str(f["id"]) == str(ch))["status"] == "alerta"


def test_alerta_quente_no_prazo(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    api_int.msg_full(TEL2, "tenho interesse no plano anual", nome="Maria Souza")  # regra 10 grava interesse
    _, ch = abrir_tel2(api_int, "quanto custa?")
    oferta(externo, "ana", ch)
    api_int.avancar(1)
    assert not alertas(externo, ch)
    api_int.avancar(2)  # 3 min > alerta_quente_min (2)
    assert esperar(lambda: alertas(externo, ch))
    assert "Plano anual" in alertas(externo, ch)[0]["json"]["text"]


def test_sem_ninguem_livre_alerta_imediato(api_int, tg, externo):
    for cid in ("ana", "bruno", "carla"):
        tg.entrar(cid)
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: alertas(externo, ch))
    assert next(f for f in api_int.fila() if str(f["id"]) == str(ch))["status"] == "alerta"
    for cid in ("ana", "bruno", "carla"):
        assert not [p for p in externo.privado(cid) if f"as:{ch}" in callbacks(p)]


def test_um_alerta_por_chamado(api_int, tg, externo):
    tg.entrar("ana")
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: alertas(externo, ch))
    api_int.avancar(3)
    api_int.avancar(10)
    api_int.rodar()
    externo.quieto()
    assert len(alertas(externo, ch)) == 1


def test_em_alerta_continua_oferecendo_a_quem_fica_livre(api_int, tg, externo):
    tg.entrar("ana")
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: alertas(externo, ch))
    api_int.status("ana", "livre")
    api_int.rodar()
    oferta(externo, "ana", ch)


def test_todos_recusaram_vai_ao_alerta(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    _, ch = abrir_tel2(api_int)
    p = oferta(externo, "ana", ch)
    tg.cb(TG_ID["ana"], f"pa:{ch}", p["message_id"])
    assert esperar(lambda: alertas(externo, ch))


# ------------------------------------------------------------ assumir

def test_assumir_atomico_concorrente(api):
    _, ch = api.abrir()  # ninguém livre → alerta: qualquer um pode assumir
    api.status("ana", "ocupado")
    api.status("bruno", "ocupado")
    barreira = threading.Barrier(2)
    res = {}

    def vai(cid):
        barreira.wait()
        res[cid] = api.assumir(cid, ch)[0]

    ts = [threading.Thread(target=vai, args=(c,)) for c in ("ana", "bruno")]
    [t.start() for t in ts]
    [t.join(15) for t in ts]
    sts = sorted(res.values())
    assert len(sts) == 2 and sum(ok(s) for s in sts) == 1 and 409 in sts, res
    vencedor = next(c for c, s in res.items() if ok(s))
    assert api.eu(vencedor)["status"] == "atendendo"
    assert [str(c["id"]) for c in api.eu(vencedor)["chamados"]] == [str(ch)]


def test_assumir_muda_status_e_avisa_lead(api):
    equipe_pronta(api, quem=("ana",))
    lead, ch = api.atendendo("ana")
    assert api.lead_csv(lead["id"])["status"] == "em_atendimento"
    assert esperar(lambda: "Ana vai te atender agora." in api.textos_para(TEL_D))
    assert api.assumir("ana", ch)[0] == 409  # já assumido


def test_assumir_pelo_botao_edita_grupo_e_manda_cartao(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    p = oferta(externo, "ana", ch)
    linha = [g for g in externo.enviadas(GRUPO) if f"#{ch}" in g["json"].get("text", "")][0]
    cbid = tg.cb(TG_ID["ana"], f"as:{ch}", p["message_id"])
    assert esperar(lambda: [a for a in externo.tg("answerCallbackQuery") if a["json"].get("callback_query_id") == cbid])
    assert esperar(lambda: [e for e in externo.tg("editMessageText", GRUPO)
                            if e["json"].get("message_id") == linha["message_id"]
                            and f"✅ Ana assumiu #{ch}" in e["json"].get("text", "")])
    assert esperar(lambda: [c for c in externo.privado("ana") if any(x.startswith(f"fe:{ch}:") for x in callbacks(c))])
    assert esperar(lambda: "Ana vai te atender agora." in externo.whats_texto(TEL2_D))


def test_segundo_a_assumir_no_telegram_recebe_ja_foi(api_int, tg, externo):
    for cid in ("ana", "bruno"):
        tg.entrar(cid)
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: alertas(externo, ch))
    a = alertas(externo, ch)[0]
    api_int.status("ana", "ocupado")
    api_int.status("bruno", "ocupado")
    tg.cb(TG_ID["ana"], f"as:{ch}", a["message_id"], chat_id=GRUPO)
    assert esperar(lambda: api_int.eu("ana")["status"] == "atendendo")
    cbid = tg.cb(TG_ID["bruno"], f"as:{ch}", a["message_id"], chat_id=GRUPO)

    def recebeu():
        resp = [x for x in externo.tg("answerCallbackQuery") if x["json"].get("callback_query_id") == cbid]
        textos = externo.textos(resp) + externo.textos(externo.privado("bruno"))
        return "já foi assumido por Ana" in textos

    assert esperar(recebeu)
    assert api_int.eu("bruno")["status"] == "ocupado"


def test_alerta_editado_ao_assumir(api_int, tg, externo):
    tg.entrar("ana")
    _, ch = abrir_tel2(api_int)
    assert esperar(lambda: alertas(externo, ch))
    a = alertas(externo, ch)[0]
    api_int.status("ana", "ocupado")
    tg.cb(TG_ID["ana"], f"as:{ch}", a["message_id"], chat_id=GRUPO)
    assert esperar(lambda: [e for e in externo.tg("editMessageText", GRUPO)
                            if e["json"].get("message_id") == a["message_id"]
                            and f"✅ Ana assumiu #{ch}" in e["json"].get("text", "")
                            and botoes(e) == []])


def test_colaborador_sem_vinculo_e_pulado(api_int, tg, externo):
    tg.entrar("bruno")
    api_int.status("ana", "livre")          # ana é a 1ª da vez, mas não tem vínculo
    api_int.relogio(mais(api_int.agora, 1))
    api_int.status("bruno", "livre")
    _, ch = abrir_tel2(api_int)
    oferta(externo, "bruno", ch)
    assert next(f for f in api_int.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "bruno"


def test_lead_que_volta_vai_ao_antigo_dono(api):
    equipe_pronta(api, quem=("ana", "bruno", "carla"))
    _, ch = api.atendendo("ana")
    api.relogio(mais(api.agora, 5))
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    # ana agora é a última da vez, mas o lead já foi atendido por ela
    _, ch2 = api.abrir(TEL, "Maria Souza", "quero falar com um atendente de novo")
    assert next(f for f in api.fila() if str(f["id"]) == str(ch2))["ofertado_a"] == "ana"


def test_lead_que_volta_antigo_dono_ocupado_segue_a_vez(api):
    equipe_pronta(api, quem=("ana", "bruno", "carla"))
    _, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    api.status("ana", "ocupado")
    _, ch2 = api.abrir(TEL, "Maria Souza", "quero falar com um atendente de novo")
    assert next(f for f in api.fila() if str(f["id"]) == str(ch2))["ofertado_a"] == "bruno"


# ------------------------------------------------------------ conversa durante o atendimento

def test_mensagem_do_lead_vai_ao_dono(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    oferta(externo, "ana", ch)
    tg.cb(TG_ID["ana"], f"as:{ch}")
    assert esperar(lambda: api_int.eu("ana")["status"] == "atendendo")
    r = api_int.msg_full(TEL2, "tenho uma dúvida extra")
    assert r["respostas"] == []
    assert esperar(lambda: [p for p in externo.privado("ana")
                            if p["json"].get("text", "").startswith("💬")
                            and "tenho uma dúvida extra" in p["json"]["text"]])
    assert "tenho uma dúvida extra" not in externo.textos(externo.grupo())


def test_dono_responde_por_reply_e_pela_api(api_int, tg, externo):
    equipe_pronta(api_int, tg)
    _, ch = abrir_tel2(api_int)
    oferta(externo, "ana", ch)
    tg.cb(TG_ID["ana"], f"as:{ch}")
    assert esperar(lambda: [c for c in externo.privado("ana") if any(x.startswith(f"fe:{ch}:") for x in callbacks(c))])
    cartao = [c for c in externo.privado("ana") if any(x.startswith(f"fe:{ch}:") for x in callbacks(c))][0]
    tg.msg(TG_ID["ana"], "Oi Maria, aqui é a Ana pelo reply", reply_to=cartao["message_id"])
    assert esperar(lambda: "Oi Maria, aqui é a Ana pelo reply" in externo.whats_texto(TEL2_D))
    st, _ = api_int.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "Resposta pela API"}, codigo=CODIGOS["ana"])
    assert ok(st)
    assert esperar(lambda: "Resposta pela API" in externo.whats_texto(TEL2_D))
    humanos = [m for m in api_int.saida_para(TEL2_D) if m.get("tipo") == "humano"]
    assert {"Oi Maria, aqui é a Ana pelo reply", "Resposta pela API"} <= {m["texto"] for m in humanos}
