"""Seção 8: painel fixo no grupo e GET /api/painel."""
import re

from conftest import CODIGOS, GRUPO, TEL2, TG_ID, esperar, mais


def paineis_enviados(externo):
    return externo.com_texto(externo.enviadas(GRUPO), "EQUIPE AGORA")


def ultimo_painel(externo):
    ps = externo.com_texto(externo.grupo(), "EQUIPE AGORA")
    return ps[-1]["json"]["text"] if ps else ""


# ------------------------------------------------------------ /api/painel

def test_api_painel_campos(api):
    api.status("ana", "livre")
    api.abrir()
    p = api.painel()
    assert {c["id"] for c in p["equipe"]} == {"ana", "bruno", "carla"}
    for c in p["equipe"]:
        assert set(c) >= {"id", "nome", "status", "livre_desde", "minutos", "proximo"}
    assert len(p["fila"]) == 1
    assert set(p["fila"][0]) >= {"id", "lead", "prioridade", "status", "minutos", "ofertado_a"}
    assert p["fila"][0]["status"] == "aguardando" and p["fila"][0]["ofertado_a"] == "ana"


def test_api_painel_minutos(api):
    api.status("ana", "livre")
    api.abrir()
    api.relogio(mais(api.agora, 1))
    api.status("bruno", "livre")  # ana já tem oferta; bruno livre há 0
    api.relogio(mais(api.agora, 1))
    p = api.painel()
    assert next(c for c in p["equipe"] if c["id"] == "bruno")["minutos"] == 1
    assert p["fila"][0]["minutos"] == 2


def test_api_painel_fila_sai_ao_assumir(api):
    api.status("ana", "livre")
    _, ch = api.atendendo("ana")
    assert all(str(f["id"]) != str(ch) for f in api.fila())


def test_api_painel_aceita_equipe(api):
    st, r = api.get("/api/painel", codigo=CODIGOS["carla"])
    assert st == 200 and "equipe" in r and "fila" in r


def test_gestor_ao_vivo_tem_painel(api):
    st, r = api.get("/api/gestor/ao-vivo")
    assert st == 200 and "equipe" in r and "fila" in r


# ------------------------------------------------------------ painel no grupo

def test_painel_criado_uma_vez_e_depois_editado(api_int, tg, externo):
    tg.entrar("ana")
    tg.entrar("bruno")
    api_int.status("ana", "livre")
    assert esperar(lambda: paineis_enviados(externo))
    mid = paineis_enviados(externo)[0]["message_id"]
    api_int.status("bruno", "livre")
    api_int.abrir(TEL2, "Maria Souza")
    assert esperar(lambda: [e for e in externo.tg("editMessageText", GRUPO)
                            if e["json"].get("message_id") == mid and "EQUIPE AGORA" in e["json"].get("text", "")])
    externo.quieto()
    assert len(paineis_enviados(externo)) == 1


def test_painel_tenta_fixar(api_int, tg, externo):
    tg.entrar("ana")
    api_int.status("ana", "livre")
    assert esperar(lambda: paineis_enviados(externo))
    mid = paineis_enviados(externo)[0]["message_id"]
    assert esperar(lambda: [p for p in externo.tg("pinChatMessage", GRUPO, todos=True)
                            if p["json"].get("message_id") == mid])


def test_falha_ao_fixar_e_ignorada(api_int, tg, externo):
    externo.falhar_metodo["pinChatMessage"] = 5
    tg.entrar("ana")
    api_int.status("ana", "livre")
    assert esperar(lambda: paineis_enviados(externo))
    api_int.status("ana", "ocupado")
    assert api_int.eu("ana")["status"] == "ocupado"
    assert api_int.get("/api/saude", token=None)[0] == 200


def test_edicao_falha_envia_novo_e_guarda_id(api_int, tg, externo):
    tg.entrar("ana")
    api_int.status("ana", "livre")
    assert esperar(lambda: paineis_enviados(externo))
    externo.falhar_metodo["editMessageText"] = 1
    api_int.status("ana", "ocupado")
    assert esperar(lambda: len(paineis_enviados(externo)) == 2)
    novo = paineis_enviados(externo)[1]["message_id"]
    api_int.status("ana", "livre")
    assert esperar(lambda: [e for e in externo.tg("editMessageText", GRUPO)
                            if e["json"].get("message_id") == novo])


def test_painel_conteudo(api_int, tg, externo):
    for cid in ("ana", "bruno"):
        tg.entrar(cid)
    api_int.status("ana", "livre")
    api_int.relogio(mais(api_int.agora, 3))
    api_int.status("bruno", "ocupado")
    assert esperar(lambda: "Bruno" in ultimo_painel(externo) and "🔴" in ultimo_painel(externo))
    t = ultimo_painel(externo)
    assert re.search(r"\b\d\d:\d\d\b", t)
    assert "🟢 Ana livre há 3 min" in t and "(próxima da vez)" in t
    assert "🔴 Bruno ocupado" in t
    assert "⚫ Carla fora" in t


def test_painel_fila_e_atendendo(api_int, tg, externo):
    tg.entrar("ana")
    _, ch = api_int.abrir(TEL2, "Maria Souza")  # ninguém livre → alerta
    assert esperar(lambda: "FILA" in ultimo_painel(externo) and "esperando" in ultimo_painel(externo))
    t = ultimo_painel(externo)
    assert "Maria · esperando" in t and "⚠️ sem dono" in t
    assert "8888" not in t
    api_int.status("ana", "ocupado")
    tg.cb(TG_ID["ana"], f"as:{ch}", 1, chat_id=GRUPO)
    assert esperar(lambda: "🟡 Ana atendendo Maria" in ultimo_painel(externo))


def test_comando_status_manda_painel_novo(api_int, tg, externo):
    tg.entrar("ana")
    api_int.status("ana", "livre")
    assert esperar(lambda: paineis_enviados(externo))
    externo.quieto()
    antes = len(paineis_enviados(externo))
    tg.msg(TG_ID["ana"], "/status", chat_id=GRUPO)
    assert esperar(lambda: len(paineis_enviados(externo)) == antes + 1)
    tg.msg(TG_ID["ana"], "/status")
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "EQUIPE AGORA"))
