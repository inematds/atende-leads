"""Seções 6 e 12: status do colaborador, ordem de vez e painel da equipe (sem Telegram: oferta no painel)."""
import pytest

from conftest import CODIGOS, TEL, equipe_pronta, mais, ok


def test_status_livre_ocupado_fora(api):
    for st in ("livre", "ocupado", "fora"):
        api.status("ana", st)
        assert api.eu("ana")["status"] == st


def test_atendendo_ou_invalido_nao_vem_do_painel(api):
    for st in ("atendendo", "dormindo"):
        s, _ = api.post("/api/equipe/status", {"status": st}, codigo=CODIGOS["ana"])
        assert s >= 400
    assert api.eu("ana")["status"] == "fora"


def test_ordem_de_vez_por_livre_desde(api):
    api.status("carla", "livre")
    api.relogio(mais(api.agora, 1))
    api.status("ana", "livre")
    api.relogio(mais(api.agora, 1))
    api.status("bruno", "livre")
    eq = {c["id"]: c for c in api.painel()["equipe"]}
    assert eq["carla"]["proximo"]
    assert not eq["ana"]["proximo"] and not eq["bruno"]["proximo"]
    _, ch = api.abrir()
    assert next(f for f in api.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "carla"


def test_empate_segue_ordem_do_negocio_json(api):
    for cid in ("carla", "bruno", "ana"):
        api.status(cid, "livre")  # mesmo minuto
    _, ch = api.abrir()
    assert next(f for f in api.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "ana"


def test_fora_com_chamado_atendendo_409(api):
    api.status("ana", "livre")
    api.atendendo("ana")
    assert api.eu("ana")["status"] == "atendendo"
    s, _ = api.post("/api/equipe/status", {"status": "fora"}, codigo=CODIGOS["ana"])
    assert s == 409
    assert api.eu("ana")["status"] == "atendendo"


def test_ao_fechar_volta_ao_fim_da_fila(api):
    equipe_pronta(api, quem=("ana", "bruno", "carla"))
    lead, ch = api.atendendo("ana")
    api.relogio(mais(api.agora, 5))
    st, r = api.fechar("ana", ch, {"resultado": "negociando"})
    assert ok(st), (st, r)
    ana = api.colab("ana")
    assert ana["status"] == "livre"
    assert api.agora[11:16] in str(ana["livre_desde"])
    eq = {c["id"]: c for c in api.painel()["equipe"]}
    assert eq["bruno"]["proximo"]
    _, ch2 = api.abrir("(41) 99999-0002", "Paulo Lima")
    assert next(f for f in api.fila() if str(f["id"]) == str(ch2))["ofertado_a"] == "bruno"


def test_eu_lista_chamados_abertos(api):
    api.status("ana", "livre")
    _, ch = api.atendendo("ana")
    eu = api.eu("ana")
    assert [str(c["id"]) for c in eu["chamados"]] == [str(ch)]
    assert isinstance(eu["retornos_hoje"], list)


def test_gestor_muda_status_do_colaborador(api):
    st, _ = api.post("/api/gestor/equipe/bruno/status", {"status": "livre"})
    assert ok(st)
    assert api.eu("bruno")["status"] == "livre"


def test_passar_pelo_painel_vai_ao_proximo(api):
    equipe_pronta(api, quem=("ana", "bruno"))
    _, ch = api.abrir()
    st, _ = api.post(f"/api/equipe/chamados/{ch}/passar", codigo=CODIGOS["ana"])
    assert ok(st)
    assert next(f for f in api.fila() if str(f["id"]) == str(ch))["ofertado_a"] == "bruno"


def test_ficha_do_lead_restrita(api):
    equipe_pronta(api, quem=("ana", "bruno"))
    lead, ch = api.abrir()  # ofertado à ana
    assert api.get(f"/api/equipe/leads/{lead['id']}", codigo=CODIGOS["ana"])[0] == 200
    assert api.get(f"/api/equipe/leads/{lead['id']}", codigo=CODIGOS["carla"])[0] == 403


def test_fora_nao_pode_assumir_ocupado_pode(api):
    lead, ch = api.abrir()  # ninguém livre → alerta (qualquer cadastrado pode assumir)
    assert api.assumir("carla", ch)[0] == 409  # carla está fora
    api.status("bruno", "ocupado")
    st, r = api.assumir("bruno", ch)
    assert ok(st), (st, r)
    assert api.eu("bruno")["status"] == "atendendo"
