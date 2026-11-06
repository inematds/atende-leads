"""Seção 16: modo polling do Telegram (TELEGRAM_MODO=polling, getUpdates em vez de webhook)."""
import json
import os
import subprocess

from conftest import FIXTURE, RAIZ, TG_ID, Servidor, Tg, env_integracoes, equipe_pronta, esperar


def env_polling(externo):
    env = env_integracoes(externo)
    env.pop("TELEGRAM_SEGREDO")  # no modo polling o segredo do webhook não é exigido
    env.update({"TELEGRAM_MODO": "polling", "TELEGRAM_POLL_TIMEOUT": "1"})
    return env


class TgPoll(Tg):
    """Mesmo Tg dos testes de webhook, mas o update entra na fila do getUpdates do Telegram falso."""

    def __init__(self, api, externo):
        super().__init__(api)
        self.externo = externo
        self.ids = []

    def update(self, corpo, segredo=None):
        self.n += 1
        uid = 700000 + self.n
        self.ids.append(uid)
        self.externo.injetar(dict(corpo, update_id=uid))
        return 200, {"ok": True}


def respondeu(externo, cid, trecho, timeout=5):
    return esperar(lambda: externo.com_texto(externo.privado(cid), trecho), timeout)


def get_updates(externo, todos=False):
    return externo.tg("getUpdates", todos=todos)


def test_saude_modo_padrao_webhook(api_int):
    assert api_int.get("/api/saude", token=None)[1]["telegram_modo"] == "webhook"


def test_polling_entrar_vincula(dados, externo):
    api = Servidor(dados, env=env_polling(externo)).subir()
    saude = api.get("/api/saude", token=None)[1]
    assert saude["ok"] is True and saude["telegram"] is True and saude["telegram_modo"] == "polling"
    assert esperar(lambda: externo.tg("deleteWebhook"))
    assert externo.tg("deleteWebhook")[0]["json"].get("drop_pending_updates") is False
    assert esperar(lambda: get_updates(externo))
    pedido = get_updates(externo)[0]["json"]
    assert pedido.get("timeout") == 1
    assert set(pedido.get("allowed_updates") or []) == {"message", "callback_query"}
    tgp = TgPoll(api, externo)
    tgp.entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!")
    # Sem TELEGRAM_SEGREDO, o webhook HTTP continua fechado (401).
    corpo = {"update_id": 1, "message": {"message_id": 1, "from": {"id": 1}, "chat": {"id": 1, "type": "private"},
                                         "text": "oi"}}
    assert api.post("/webhook/telegram", corpo, token=None)[0] == 401


def test_polling_callback_assume(dados, externo):
    api = Servidor(dados, env=env_polling(externo)).subir()   # ATENDE_AGORA (relógio fixo) também faz polling
    tgp = TgPoll(api, externo)
    tgp.entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!")
    equipe_pronta(api, quem=("ana",))
    _, ch = api.abrir()
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), f"#{ch}"), 5)  # oferta chegou
    cbid = tgp.cb(TG_ID["ana"], f"as:{ch}")
    assert esperar(lambda: api.eu("ana")["status"] == "atendendo", 5)
    assert esperar(lambda: [a for a in externo.tg("answerCallbackQuery")
                            if a["json"].get("callback_query_id") == cbid], 5)


def test_polling_offset_nao_reprocessa_ao_reiniciar(dados, externo):
    s = Servidor(dados, env=env_polling(externo))
    api = s.subir()
    tgp = TgPoll(api, externo)
    tgp.entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!")
    uid = tgp.ids[-1]
    assert esperar(lambda: [p for p in get_updates(externo) if p["json"].get("offset") == uid + 1], 5)
    s.parar()
    antes = len(get_updates(externo))
    api2 = Servidor(dados, env=env_polling(externo)).subir()
    # O 1º getUpdates depois de reiniciar já pede a partir do offset gravado no SQLite.
    assert esperar(lambda: len(get_updates(externo)) > antes, 5)
    assert get_updates(externo)[antes]["json"].get("offset") == uid + 1
    tgp2 = TgPoll(api2, externo)
    tgp2.n = tgp.n  # update_id continua crescendo, como no Telegram
    tgp2.msg(TG_ID["ana"], "/livre")
    assert esperar(lambda: api2.eu("ana")["status"] == "livre", 5)
    externo.quieto()
    assert len(externo.com_texto(externo.privado("ana"), "Olá, Ana!")) == 1


def test_polling_erro_500_nao_derruba(dados, externo):
    externo.respostas["getUpdates"] = [(500, {"ok": False, "error_code": 500, "description": "Internal"})]
    api = Servidor(dados, env=env_polling(externo)).subir()
    assert esperar(lambda: [p for p in get_updates(externo, todos=True) if p["status"] == 500])
    st, saude = api.get("/api/saude", token=None)
    assert st == 200 and saude["ok"] is True
    TgPoll(api, externo).entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!", timeout=6)   # retomou depois do backoff


def test_polling_409_chama_deletewebhook_de_novo(dados, externo):
    externo.respostas["getUpdates"] = [(409, {"ok": False, "error_code": 409,
                                              "description": "Conflict: can't use getUpdates method while "
                                                             "webhook is active"})]
    api = Servidor(dados, env=env_polling(externo)).subir()
    assert esperar(lambda: [p for p in get_updates(externo, todos=True) if p["status"] == 409])
    assert esperar(lambda: len(externo.tg("deleteWebhook")) >= 2, 5)
    TgPoll(api, externo).entrar("ana")
    assert respondeu(externo, "ana", "Olá, Ana!", timeout=6)


def test_polling_nao_exige_segredo_em_0000(tmp_path, externo):
    d = tmp_path / "zero"
    d.mkdir()
    cfg = json.loads(FIXTURE.read_text())
    for m in cfg["equipe"]:
        m["codigo"] = m["id"] + "-Xk3vQ9pL2mZt"
    (d / "negocio.json").write_text(json.dumps(cfg))
    base = {k: v for k, v in os.environ.items() if not k.startswith(("ATENDE_", "TELEGRAM_", "EVOLUTION_"))}
    base.update({"TELEGRAM_API_URL": externo.url, "TELEGRAM_TOKEN": "TOKEN123", "TELEGRAM_POLL_TIMEOUT": "1"})

    def serve(extra):
        return subprocess.Popen([str(RAIZ / "atende"), "serve", "--host", "0.0.0.0", "--porta", "0", "--dados", str(d)],
                                cwd=RAIZ, env=dict(base, **extra), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
    p = serve({})                                     # webhook sem TELEGRAM_SEGREDO → recusa
    assert p.wait(15) != 0 and "TELEGRAM_SEGREDO" in p.stderr.read()
    p = serve({"TELEGRAM_MODO": "polling"})          # polling sem segredo → sobe
    try:
        assert p.stdout.readline().startswith("PORTA=")
    finally:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
