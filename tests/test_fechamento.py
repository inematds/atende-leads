"""Seção 9: fechamento (API, botões do Telegram e /fechar), histórico, retorno e devolver."""
import pytest

from conftest import (CODIGOS, TEL, TEL_D, TEL2, TEL2_D, TEL2_FMT, TG_ID, botoes, buscar, callbacks, equipe_pronta,
                      esperar, mais, ok, urls)

AMANHA_9 = "2026-11-10T09:00"


def eventos(api, lead_id):
    return buscar(api.ficha(lead_id), lambda d: "resultado" in d and "minutos_atendimento" in d)


def status_chamado(api, lead_id, ch):
    return next(c for c in api.chamados_do_lead(lead_id) if str(c["id"]) == str(ch))["status"]


@pytest.fixture
def atend(api):
    """ana atendendo Maria (TEL)."""
    equipe_pronta(api, quem=("ana", "bruno"))
    lead, ch = api.atendendo("ana")
    return api, lead, ch


# ------------------------------------------------------------ validações

@pytest.mark.parametrize("corpo", [
    {},
    {"resultado": "ganhou"},
    {"resultado": "vendeu"},
    {"resultado": "vendeu", "valor": -1},
    {"resultado": "retornar"},
    {"resultado": "retornar", "retornar_em": "2026-11-09T08:00"},   # passado
    {"resultado": "retornar", "retornar_em": "amanhã"},
    {"resultado": "sem_interesse"},
    {"resultado": "sem_interesse", "motivo": "spam"},               # só para inválido
    {"resultado": "invalido"},
    {"resultado": "invalido", "motivo": "preco"},                   # só para sem_interesse
    {"resultado": "invalido", "motivo": "xyz"},
])
def test_fechar_validacao_422(atend, corpo):
    api, lead, ch = atend
    st, _ = api.fechar("ana", ch, corpo)
    assert st == 422
    assert status_chamado(api, lead["id"], ch) == "atendendo"


def test_fechar_nao_dono_403(atend):
    api, _, ch = atend
    assert api.fechar("bruno", ch, {"resultado": "negociando"})[0] == 403


def test_gestor_fecha_qualquer(atend):
    api, lead, ch = atend
    st, _ = api.post(f"/api/equipe/chamados/{ch}/fechar", {"resultado": "negociando"})
    assert ok(st)
    assert status_chamado(api, lead["id"], ch) == "fechado"


def test_fechar_duas_vezes_409(atend):
    api, _, ch = atend
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    assert api.fechar("ana", ch, {"resultado": "negociando"})[0] == 409


@pytest.mark.parametrize("corpo,status_lead", [
    ({"resultado": "vendeu", "valor": 1200.0, "produto": "plano-anual"}, "ganho"),
    ({"resultado": "vendeu", "valor": 0}, "ganho"),
    ({"resultado": "retornar", "retornar_em": AMANHA_9}, "retornar"),
    ({"resultado": "negociando"}, "negociando"),
    ({"resultado": "sem_interesse", "motivo": "preco"}, "perdido"),
    ({"resultado": "sem_interesse", "motivo": "ja_comprou"}, "perdido"),
    ({"resultado": "invalido", "motivo": "numero_errado"}, "invalido"),
])
def test_fechar_status_do_lead(atend, corpo, status_lead):
    api, lead, ch = atend
    st, r = api.fechar("ana", ch, corpo)
    assert ok(st), (st, r)
    assert api.lead_csv(lead["id"])["status"] == status_lead
    c = next(c for c in api.chamados_do_lead(lead["id"]) if str(c["id"]) == str(ch))
    assert c["status"] == "fechado" and c["resultado"] == corpo["resultado"]


def test_fechar_libera_colaborador(atend):
    api, _, ch = atend
    api.fechar("ana", ch, {"resultado": "negociando"})
    assert api.eu("ana")["status"] == "livre"
    assert api.eu("ana")["chamados"] == []


def test_fechar_com_outro_chamado_continua_atendendo(api):
    api.status("ana", "livre")
    _, ch1 = api.atendendo("ana")
    _, ch2 = api.abrir(TEL2, "Paulo Lima")
    assert ok(api.post(f"/api/gestor/chamados/{ch2}/transferir", {"colaborador": "ana"})[0])
    assert ok(api.fechar("ana", ch1, {"resultado": "negociando"})[0])
    assert api.eu("ana")["status"] == "atendendo"


def test_historico_do_lead(api):
    api.status("ana", "livre")
    lead, ch = api.abrir()
    api.relogio(mais(api.agora, 1))
    assert ok(api.assumir("ana", ch)[0])
    api.relogio(mais(api.agora, 10))
    corpo = {"resultado": "vendeu", "valor": 1200.0, "produto": "plano-anual", "nota": "pagou no pix"}
    assert ok(api.fechar("ana", ch, corpo)[0])
    evs = eventos(api, lead["id"])
    assert len(evs) == 1
    e = evs[0]
    assert set(e) >= {"em", "colaborador", "resultado", "valor", "produto", "motivo", "nota",
                      "minutos_ate_assumir", "minutos_atendimento"}
    assert e["colaborador"] == "ana" and e["resultado"] == "vendeu"
    assert float(e["valor"]) == 1200.0 and e["produto"] == "plano-anual" and e["nota"] == "pagou no pix"
    assert e["minutos_ate_assumir"] == 1 and e["minutos_atendimento"] == 10


def test_mensagem_ao_lead_so_em_retornar(atend):
    api, lead, ch = atend
    assert ok(api.fechar("ana", ch, {"resultado": "retornar", "retornar_em": AMANHA_9})[0])
    assert esperar(lambda: "Combinado! Vamos te procurar em 10/11 às 09:00." in api.textos_para(TEL_D))
    st, meu = api.get(f"/api/meu/{lead['token']}", token=None)
    assert "2026-11-10" in str(meu["retornar_em"]) and "09:00" in str(meu["retornar_em"])


@pytest.mark.parametrize("corpo", [{"resultado": "vendeu", "valor": 10},
                                   {"resultado": "sem_interesse", "motivo": "curioso"},
                                   {"resultado": "negociando"}])
def test_sem_mensagem_ao_lead_nos_outros_resultados(atend, corpo):
    api, _, ch = atend
    assert esperar(lambda: "vai te atender agora" in api.textos_para(TEL_D))
    antes = len(api.saida_para(TEL_D))
    assert ok(api.fechar("ana", ch, corpo)[0])
    assert len(api.saida_para(TEL_D)) == antes


def test_devolver_ao_bot(atend):
    api, lead, ch = atend
    st, _ = api.post(f"/api/equipe/chamados/{ch}/devolver", codigo=CODIGOS["ana"])
    assert ok(st)
    c = next(c for c in api.chamados_do_lead(lead["id"]) if str(c["id"]) == str(ch))
    assert c["status"] == "fechado" and c["resultado"] == "devolvido"
    assert api.lead_csv(lead["id"])["status"] == "novo"
    assert api.eu("ana")["status"] == "livre"
    assert api.msg_full(TEL, "qual o horario de atendimento")["respostas"]  # agente volta a responder


# ------------------------------------------------------------ pelo Telegram

@pytest.fixture
def tatend(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    lead, ch = api_int.atendendo("ana", TEL2, "Maria Souza")
    assert esperar(lambda: cartao(externo, ch))
    return api_int, tg, externo, lead, ch


def cartao(externo, ch):
    cs = [c for c in externo.privado("ana") if any(x.startswith(f"fe:{ch}:") for x in callbacks(c))]
    return cs[0] if cs else None


def fechado(api, lead, ch):
    return esperar(lambda: status_chamado(api, lead["id"], ch) == "fechado")


def test_cartao_tem_botoes_de_fechamento(tatend):
    api, tg, externo, lead, ch = tatend
    c = cartao(externo, ch)
    cbs = callbacks(c)
    for res in ("vendeu", "retornar", "negociando", "sem_interesse", "invalido"):
        assert f"fe:{ch}:{res}" in cbs
    assert f"dv:{ch}" in cbs
    rot = " ".join(b.get("text", "") for b in botoes(c))
    for r in ("Vendeu", "Retornar", "Negociando", "Sem interesse", "Inválido", "Devolver ao bot"):
        assert r in rot


def test_fechar_vendeu_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:vendeu")
    tg.msg(a, "1200")
    tg.cb(a, f"fp:{ch}")
    assert fechado(api, lead, ch)
    assert api.lead_csv(lead["id"])["status"] == "ganho"
    assert float(eventos(api, lead["id"])[0]["valor"]) == 1200.0


def test_fechar_sem_interesse_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:sem_interesse")
    assert esperar(lambda: [p for p in externo.privado("ana") if f"fm:{ch}:preco" in callbacks(p)])
    tg.cb(a, f"fm:{ch}:preco")
    tg.cb(a, f"fp:{ch}")
    assert fechado(api, lead, ch)
    assert api.lead_csv(lead["id"])["status"] == "perdido"
    assert eventos(api, lead["id"])[0]["motivo"] == "preco"


def test_fechar_retornar_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:retornar")
    assert esperar(lambda: [p for p in externo.privado("ana") if f"fr:{ch}:3" in callbacks(p)])
    p = [p for p in externo.privado("ana") if f"fr:{ch}:3" in callbacks(p)][0]
    assert {f"fr:{ch}:1", f"fr:{ch}:3", f"fr:{ch}:7"} <= set(callbacks(p))
    tg.cb(a, f"fr:{ch}:1")
    tg.cb(a, f"fp:{ch}")
    assert fechado(api, lead, ch)
    assert api.lead_csv(lead["id"])["status"] == "retornar"
    st, meu = api.get(f"/api/meu/{lead['token']}", token=None)
    assert "2026-11-10" in str(meu["retornar_em"]) and "09:00" in str(meu["retornar_em"])


def test_fechar_negociando_com_nota_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:negociando")
    tg.msg(a, "vai pensar ate sexta")
    assert fechado(api, lead, ch)
    assert eventos(api, lead["id"])[0]["nota"] == "vai pensar ate sexta"


def test_fechar_invalido_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:invalido")
    tg.cb(a, f"fm:{ch}:spam")
    tg.cb(a, f"fp:{ch}")
    assert fechado(api, lead, ch)
    assert api.lead_csv(lead["id"])["status"] == "invalido"


def test_devolver_pelo_bot(tatend):
    api, tg, externo, lead, ch = tatend
    tg.cb(TG_ID["ana"], f"dv:{ch}")
    assert fechado(api, lead, ch)
    c = next(c for c in api.chamados_do_lead(lead["id"]) if str(c["id"]) == str(ch))
    assert c["resultado"] == "devolvido"


def test_audio_como_nota_sem_whisper(tatend):
    api, tg, externo, lead, ch = tatend
    a = TG_ID["ana"]
    tg.cb(a, f"fe:{ch}:negociando")
    tg.msg(a, None, extra={"voice": {"file_id": "VOZ1", "file_unique_id": "u1", "duration": 3,
                                     "mime_type": "audio/ogg"}})
    assert fechado(api, lead, ch)
    assert eventos(api, lead["id"])[0]["nota"] == "[áudio]"


@pytest.mark.parametrize("cmd,status_lead", [
    ("vendeu 1200", "ganho"),
    (f"retornar {AMANHA_9}", "retornar"),
    ("negociando", "negociando"),
    ("sem preco", "perdido"),
    ("invalido spam", "invalido"),
])
def test_fechar_por_comando(tatend, cmd, status_lead):
    api, tg, externo, lead, ch = tatend
    tg.msg(TG_ID["ana"], f"/fechar {ch} {cmd}")
    assert fechado(api, lead, ch)
    assert api.lead_csv(lead["id"])["status"] == status_lead


# ------------------------------------------------------------ retorno agendado

def test_retorno_dispara_aviso_na_data(tatend):
    api, tg, externo, lead, ch = tatend
    assert ok(api.fechar("ana", ch, {"resultado": "retornar", "retornar_em": AMANHA_9})[0])
    api.avancar(para="2026-11-10T08:30")
    assert not externo.com_texto(externo.privado("ana"), "📅 Retorno:")
    api.avancar(para="2026-11-10T09:01")
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "📅 Retorno:"))
    p = externo.com_texto(externo.privado("ana"), "📅 Retorno:")[0]
    assert "Maria" in p["json"]["text"] and TEL2_FMT in p["json"]["text"]
    assert f"https://wa.me/{TEL2_D}" in urls(p)
    assert any("/ligar/" in u for u in urls(p))
    ra = [c for c in callbacks(p) if c.startswith("ra:")]
    assert ra
    tg.cb(TG_ID["ana"], ra[0], p["message_id"])
    assert esperar(lambda: len(api.eu("ana")["chamados"]) == 1)
    novo = api.eu("ana")["chamados"][0]
    assert novo["motivo"] == "venda" and novo["status"] == "atendendo" and novo["dono"] == "ana"
    assert api.eu("ana")["status"] == "atendendo"


def test_retorno_nao_vai_ao_lead_que_pediu_parar(tatend):
    api, tg, externo, lead, ch = tatend
    api.msg_full(TEL2, "parar")
    assert ok(api.fechar("ana", ch, {"resultado": "retornar", "retornar_em": AMANHA_9})[0])
    api.avancar(para="2026-11-10T09:01")
    assert "Combinado!" not in externo.whats_texto(TEL2_D)
