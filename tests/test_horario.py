"""Seção 10: fora do horário, abertura do expediente, lembrete de atendimento parado e fim do expediente."""
import pytest

from conftest import (GRUPO, TEL, TEL2, TG_ID, Servidor, Tg, botoes, callbacks, env_integracoes, equipe_pronta,
                      esperar)

DOMINGO_NOITE = "2026-11-08T20:00"


def item(api, ch):
    return next(f for f in api.fila() if str(f["id"]) == str(ch))


@pytest.mark.parametrize("agora,proximo", [
    (DOMINGO_NOITE, "09/11 às 08:00"),
    ("2026-11-09T07:00", "09/11 às 08:00"),     # segunda antes de abrir
    ("2026-11-09T18:30", "10/11 às 08:00"),     # segunda depois de fechar
    ("2026-11-14T14:00", "16/11 às 08:00"),     # sábado depois das 13h, domingo fechado
    ("2026-11-13T19:00", "14/11 às 09:00"),     # sexta à noite → sábado 09h
])
def test_fora_do_horario_avisa_proximo_inicio(dados, agora, proximo):
    api = Servidor(dados, agora=agora).subir()
    api.status("ana", "livre")
    r = api.msg_full(TEL, "quero falar com um atendente", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert "fora do horário" in txt and proximo in txt
    ch = api.chamado_aberto(r["lead"]["id"])
    assert ch["status"] == "aguardando"
    assert item(api, ch["id"])["ofertado_a"] in (None, "")


def test_fora_do_horario_nao_gera_alerta(dados):
    api = Servidor(dados, agora=DOMINGO_NOITE).subir()
    _, ch = api.abrir()
    api.avancar(para="2026-11-08T23:00")
    assert item(api, ch)["status"] == "aguardando"


def test_abertura_do_expediente_oferta(dados):
    api = Servidor(dados, agora=DOMINGO_NOITE).subir()
    api.status("ana", "livre")
    _, ch = api.abrir()
    api.avancar(para="2026-11-09T08:00")
    assert item(api, ch)["ofertado_a"] == "ana"


def test_prazo_de_alerta_conta_da_abertura(dados):
    api = Servidor(dados, agora=DOMINGO_NOITE).subir()
    equipe_pronta(api)
    _, ch = api.abrir()
    api.avancar(para="2026-11-09T08:00")
    api.avancar(para="2026-11-09T08:03")  # 3 min < alerta_normal_min (5) contados da abertura
    assert item(api, ch)["status"] == "aguardando"
    api.avancar(para="2026-11-09T08:06")
    assert item(api, ch)["status"] == "alerta"


def test_abertura_oferta_na_ordem_de_abertura(dados, externo):
    api = Servidor(dados, agora=DOMINGO_NOITE, env=env_integracoes(externo)).subir()
    tg = Tg(api)
    equipe_pronta(api, tg, quem=("ana", "bruno"))
    _, ch1 = api.abrir(TEL, "Maria Souza")
    _, ch2 = api.abrir(TEL2, "Paulo Lima")
    assert not [p for p in externo.tg("sendMessage") if f"as:{ch1}" in callbacks(p) or f"as:{ch2}" in callbacks(p)]
    api.avancar(para="2026-11-09T08:00")
    assert esperar(lambda: [p for p in externo.tg("sendMessage") if f"as:{ch2}" in callbacks(p)])
    ordem = [i for i, p in enumerate(externo.tg("sendMessage"))
             if f"as:{ch1}" in callbacks(p) or f"as:{ch2}" in callbacks(p)]
    primeiro = externo.tg("sendMessage")[ordem[0]]
    assert f"as:{ch1}" in callbacks(primeiro)


# ------------------------------------------------------------ lembrete

@pytest.fixture
def tatend(api_int, tg, externo):
    equipe_pronta(api_int, tg, quem=("ana",))
    lead, ch = api_int.atendendo("ana", TEL2, "Maria Souza")
    return api_int, tg, externo, lead, ch


def lembretes(externo, ch):
    return [p for p in externo.com_texto(externo.privado("ana"), "Ainda com Maria") if f"lc:{ch}" in callbacks(p)]


def test_lembrete_atendimento_parado(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(20)
    assert not lembretes(externo, ch)
    api.avancar(11)
    assert esperar(lambda: lembretes(externo, ch))
    p = lembretes(externo, ch)[0]
    assert f"lt:{ch}" in callbacks(p)
    rot = " ".join(b.get("text", "") for b in botoes(p))
    assert "Sim, continuo" in rot and "Terminei" in rot


def test_um_lembrete_por_periodo(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(31)
    assert esperar(lambda: lembretes(externo, ch))
    api.avancar(5)
    api.rodar()
    externo.quieto()
    assert len(lembretes(externo, ch)) == 1


def test_sim_continuo_zera_a_contagem(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(31)
    assert esperar(lambda: lembretes(externo, ch))
    tg.cb(TG_ID["ana"], f"lc:{ch}", lembretes(externo, ch)[0]["message_id"])
    api.avancar(20)
    externo.quieto()
    assert len(lembretes(externo, ch)) == 1
    api.avancar(11)
    assert esperar(lambda: len(lembretes(externo, ch)) == 2)


def test_terminei_abre_fechamento(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(31)
    assert esperar(lambda: lembretes(externo, ch))

    def com_fechamento():
        return [p for p in externo.privado("ana") if any(c.startswith(f"fe:{ch}:") for c in callbacks(p))]

    antes = len(com_fechamento())
    tg.cb(TG_ID["ana"], f"lt:{ch}", lembretes(externo, ch)[0]["message_id"])
    assert esperar(lambda: len(com_fechamento()) > antes)


def test_mensagem_nova_zera_lembrete(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(20)
    api.msg_full(TEL2, "ainda estou aqui")
    api.avancar(15)  # 35 min do início, 15 da última mensagem
    assert not lembretes(externo, ch)


# ------------------------------------------------------------ fim do expediente

def test_fim_do_expediente(tatend):
    api, tg, externo, lead, ch = tatend
    api.avancar(para="2026-11-09T17:50")
    externo.quieto()
    assert not externo.com_texto(externo.privado("ana"), "Fim do expediente")
    grupo_antes = len([p for p in externo.enviadas(GRUPO) if "EQUIPE AGORA" not in p["json"].get("text", "")])
    api.avancar(para="2026-11-09T18:01")
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "Fim do expediente: feche seus atendimentos"))
    assert esperar(lambda: len([p for p in externo.enviadas(GRUPO)
                                if "EQUIPE AGORA" not in p["json"].get("text", "")]) > grupo_antes)
    assert "8888" not in externo.textos(externo.grupo())
