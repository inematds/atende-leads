"""Seção 16: webhook do Telegram, vínculo, comandos, botões e privacidade no grupo."""
import pytest

from conftest import (GRUPO, SEGREDO_TG, TEL2, TG_ID, TG_TOKEN, Servidor, Tg, callbacks, env_integracoes,
                      equipe_pronta, esperar, ok)


def respondeu(externo, cid, trecho):
    return esperar(lambda: externo.com_texto(externo.privado(cid), trecho))


def resp_cb(externo, cbid):
    return [a for a in externo.tg("answerCallbackQuery") if a["json"].get("callback_query_id") == cbid]


# ------------------------------------------------------------ webhook

def test_webhook_segredo(api_int):
    corpo = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 1}, "chat": {"id": 1, "type": "private"},
                                         "text": "oi"}}
    assert api_int.post("/webhook/telegram", corpo, token=None)[0] == 401
    h = {"X-Telegram-Bot-Api-Secret-Token": "errado"}
    assert api_int.post("/webhook/telegram", corpo, token=None, headers=h)[0] == 401
    h = {"X-Telegram-Bot-Api-Secret-Token": SEGREDO_TG}
    assert api_int.post("/webhook/telegram", corpo, token=None, headers=h)[0] == 200


def test_webhook_update_estranho_200(tg):
    assert tg.update({"edited_message": {"message_id": 1}})[0] == 200
    assert tg.update({})[0] == 200


# ------------------------------------------------------------ vínculo

def test_entrar_ok(tg, externo):
    tg.entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!")
    p = externo.com_texto(externo.privado("ana"), "Olá, Ana!")[0]
    assert {"st:livre", "st:ocupado", "st:fora"} <= set(callbacks(p))


def test_entrar_codigo_errado(tg, externo):
    tg.msg(TG_ID["ana"], "/entrar codigo-errado")
    assert respondeu(externo, "ana", "Código inválido.")


def test_nao_vinculado_recebe_instrucao(api_int, tg, externo):
    tg.msg(TG_ID["bruno"], "/livre")
    assert respondeu(externo, "bruno", "Envie /entrar")
    assert api_int.eu("bruno")["status"] == "fora"


def test_nao_vinculado_botao(api_int, tg, externo):
    cbid = tg.cb(TG_ID["bruno"], "st:livre")
    assert esperar(lambda: resp_cb(externo, cbid))
    textos = externo.textos(resp_cb(externo, cbid)) + externo.textos(externo.privado("bruno"))
    assert "Envie /entrar" in textos
    assert api_int.eu("bruno")["status"] == "fora"


def test_vinculo_persiste_ao_reiniciar(dados, externo):
    s = Servidor(dados, env=env_integracoes(externo))
    tg = Tg(s.subir())
    tg.entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!")
    s.parar()
    api2 = Servidor(dados, env=env_integracoes(externo)).subir()
    Tg(api2).msg(TG_ID["ana"], "/livre")
    assert esperar(lambda: api2.eu("ana")["status"] == "livre")


# ------------------------------------------------------------ comandos e botões de status

@pytest.mark.parametrize("cmd,st", [("/livre", "livre"), ("/ocupado", "ocupado"), ("/fora", "fora")])
def test_comandos_de_status(api_int, tg, cmd, st):
    tg.entrar("ana")
    if st == "fora":
        api_int.status("ana", "livre")
    tg.msg(TG_ID["ana"], cmd)
    assert esperar(lambda: api_int.eu("ana")["status"] == st)


def test_botao_de_status(api_int, tg, externo):
    tg.entrar("ana")
    cbid = tg.cb(TG_ID["ana"], "st:livre")
    assert esperar(lambda: api_int.eu("ana")["status"] == "livre")
    assert esperar(lambda: resp_cb(externo, cbid))


def test_comando_de_status_no_grupo_e_ignorado(api_int, tg):
    tg.entrar("ana")
    tg.msg(TG_ID["ana"], "/livre", chat_id=GRUPO)
    assert api_int.eu("ana")["status"] == "fora"


def test_meus(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    _, ch = api_int.atendendo("ana", TEL2, "Maria Souza")
    externo.quieto()
    n = len(externo.privado("ana"))
    tg.msg(TG_ID["ana"], "/meus")
    assert esperar(lambda: f"#{ch}" in externo.textos(externo.privado("ana")[n:]))


def test_retornos_de_hoje(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    _, ch = api_int.atendendo("ana", TEL2, "Maria Souza")
    assert ok(api_int.fechar("ana", ch, {"resultado": "retornar", "retornar_em": "2026-11-09T15:00"})[0])
    externo.quieto()
    n = len(externo.privado("ana"))
    tg.msg(TG_ID["ana"], "/retornos")
    assert esperar(lambda: "Maria" in externo.textos(externo.privado("ana")[n:]))
    assert any(r for r in api_int.eu("ana")["retornos_hoje"])


def test_lead_ficha_curta(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    api_int.atendendo("ana", TEL2, "Maria Souza")
    tg.entrar("carla")
    externo.quieto()
    n = len(externo.privado("ana"))
    tg.msg(TG_ID["ana"], "/lead Maria")
    assert esperar(lambda: "Maria" in externo.textos(externo.privado("ana")[n:]))
    m = len(externo.privado("carla"))
    tg.msg(TG_ID["carla"], "/lead Maria")
    assert esperar(lambda: len(externo.privado("carla")) > m)
    assert "8888" not in externo.textos(externo.privado("carla")[m:])  # carla não pode ver esse lead


@pytest.mark.parametrize("data", ["as:999999", "pa:999999", "xx:1", "st:livre", "fe:999999:vendeu"])
def test_toda_callback_recebe_answer(api_int, tg, externo, data):
    tg.entrar("ana")
    cbid = tg.cb(TG_ID["ana"], data)
    assert esperar(lambda: resp_cb(externo, cbid))


# ------------------------------------------------------------ sem Telegram configurado / privacidade

def test_sem_telegram_nada_vai_ao_telegram(dados, externo):
    env = {k: v for k, v in env_integracoes(externo).items() if not k.startswith("TELEGRAM_")}
    api = Servidor(dados, env=env).subir()
    api.status("ana", "livre")
    _, ch = api.abrir(TEL2, "Maria Souza")
    assert next(f for f in api.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "ana"  # oferta só no painel
    api.avancar(10)
    assert [p for p in externo.pedidos if p["rota"].startswith("/bot")] == []
    assert api.get("/api/saude", token=None)[1]["telegram"] is False


def test_privacidade_no_grupo(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana", "bruno"))
    api_int.msg_full(TEL2, "tenho interesse no plano anual abacaxi", nome="Maria Souza")
    _, ch = api_int.abrir(TEL2, "Maria Souza", "quero falar com um atendente sobre o abacaxi")
    api_int.avancar(3)
    api_int.avancar(4)                                      # alerta
    tg.msg(TG_ID["ana"], "/status", chat_id=GRUPO)
    api_int.status("ana", "ocupado")
    tg.cb(TG_ID["ana"], f"as:{ch}", 1, chat_id=GRUPO)
    assert esperar(lambda: api_int.eu("ana")["status"] == "atendendo")
    api_int.msg_full(TEL2, "segredo-do-lead melancia")
    api_int.avancar(para="2026-11-09T18:01")               # fim do expediente
    grupo = [p for p in externo.tg(chat=GRUPO, todos=True) if p["metodo"] in ("sendMessage", "editMessageText")]
    assert grupo, "deveria haver mensagens no grupo"
    txt = externo.textos(grupo)
    for proibido in ("8888", "98888-7777", "5541988887777", "abacaxi", "melancia", "Souza"):
        assert proibido not in txt, proibido
    assert TG_TOKEN not in txt
