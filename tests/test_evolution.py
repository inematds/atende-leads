"""Seção 15: WhatsApp pela Evolution API (webhook de entrada, envio e caixa de saída)."""
import pytest

from conftest import APIKEY, INSTANCIA, SEGREDO_WH, TEL_D, Servidor, env_integracoes, esperar

JID = f"{TEL_D}@s.whatsapp.net"


class Evo:
    def __init__(self, api):
        self.api = api
        self.n = 0

    def enviar(self, texto="oi", from_me=False, jid=JID, id_=None, push="Maria", event="messages.upsert",
               message=None, segredo=SEGREDO_WH, tipo="conversation"):
        self.n += 1
        corpo = {"event": event, "instance": INSTANCIA, "data": {
            "key": {"remoteJid": jid, "fromMe": from_me, "id": id_ or f"MSG{self.n}"},
            "pushName": push,
            "message": message if message is not None else {"conversation": texto},
            "messageType": tipo}}
        return self.api.post(f"/webhook/evolution/{segredo}", corpo, token=None)


@pytest.fixture
def evo(api_int):
    return Evo(api_int)


@pytest.fixture
def api_evo(dados, externo):
    env = {k: v for k, v in env_integracoes(externo).items() if not k.startswith("TELEGRAM_")}
    return Servidor(dados, env=env).subir()


def textos(externo):
    return [p["json"].get("text", "") for p in externo.whats() if p["json"].get("number") == TEL_D]


def test_segredo_errado_404(evo):
    assert evo.enviar(segredo="errado")[0] == 404


def test_mensagem_responde_por_sendtext(evo, externo):
    assert evo.enviar("oi")[0] == 200
    assert esperar(lambda: externo.whats())
    p = externo.whats()[0]
    assert p["rota"] == f"/message/sendText/{INSTANCIA}"
    assert p["headers"].get("apikey") == APIKEY
    assert p["json"]["number"] == TEL_D and p["json"]["text"]


def test_pushname_pergunta_posso_te_chamar(evo, externo, api_int):
    evo.enviar("oi", push="Maria")
    assert esperar(lambda: any("Posso te chamar de Maria?" in t for t in textos(externo)))
    n = len(textos(externo))
    evo.enviar("sim")
    assert esperar(lambda: any("1 - Plano anual" in t for t in textos(externo)[n:]))
    linha = next(l for l in api_int.csv()[1] if l["telefone"] == TEL_D)
    assert linha["nome"] == "Maria"


def test_pushname_outra_resposta_vira_nome(evo, externo, api_int):
    evo.enviar("oi", push="Maria")
    assert esperar(lambda: any("Posso te chamar de Maria?" in t for t in textos(externo)))
    evo.enviar("Mariana Costa")
    assert esperar(lambda: next(l for l in api_int.csv()[1] if l["telefone"] == TEL_D)["nome"] == "Mariana Costa")


def test_pushname_nao_vira_nome_sem_confirmar(evo, externo, api_int):
    evo.enviar("oi", push="Maria")
    assert esperar(lambda: textos(externo))
    linha = next(l for l in api_int.csv()[1] if l["telefone"] == TEL_D)
    assert linha["nome"] != "Maria"


@pytest.mark.parametrize("kw", [
    {"from_me": True},
    {"jid": "120363000000000000@g.us"},
    {"event": "messages.update"},
    {"event": "connection.update"},
])
def test_ignorados(evo, externo, api_int, kw):
    assert evo.enviar("quero falar com um atendente", **kw)[0] == 200
    externo.quieto()
    assert externo.whats() == []
    assert [l for l in api_int.csv()[1] if l["telefone"] == TEL_D] == []


def test_id_repetido_ignorado(evo, externo):
    evo.enviar("oi", id_="REPETIDO1")
    assert esperar(lambda: externo.whats())
    externo.quieto()
    n = len(externo.whats())
    assert evo.enviar("oi", id_="REPETIDO1")[0] == 200
    externo.quieto()
    assert len(externo.whats()) == n


def test_extended_text_message(evo, externo):
    evo.enviar(message={"extendedTextMessage": {"text": "Qual o horário de atendimento?"}},
               tipo="extendedTextMessage")
    assert esperar(lambda: "Atendemos de segunda a sexta, das 8h às 18h." in textos(externo))


def test_sem_texto(evo, externo):
    evo.enviar(message={"imageMessage": {"mimetype": "image/jpeg"}}, tipo="imageMessage")
    assert esperar(lambda: "Por enquanto só consigo ler mensagens de texto." in textos(externo))


def test_envio_na_ordem_das_respostas(api_evo, externo):
    r = api_evo.msg_full("(41) 99999-0001", "quero falar com um atendente", nome="Maria Souza")
    assert len(r["respostas"]) >= 1
    assert esperar(lambda: textos(externo) == r["respostas"])


def test_saida_campos_e_status_enviado(api_evo, externo):
    api_evo.msg_full("(41) 99999-0001", "oi")
    assert esperar(lambda: externo.whats())
    assert esperar(lambda: all(m["status"] == "enviado" for m in api_evo.saida()))
    m = api_evo.saida()[0]
    assert set(m) >= {"id", "telefone", "texto", "tipo", "status", "em"}
    assert m["tipo"] == "agente" and m["telefone"].endswith("999990001")


def test_pendente_reenviado_pela_tarefa(api_evo, externo):
    externo.falhas = 100
    api_evo.msg_full("(41) 99999-0001", "oi")
    assert esperar(lambda: [m for m in api_evo.saida() if m["status"] == "pendente"])
    assert externo.whats() == []
    externo.falhas = 0
    api_evo.rodar()
    assert esperar(lambda: externo.whats())
    assert esperar(lambda: all(m["status"] == "enviado" for m in api_evo.saida()))
