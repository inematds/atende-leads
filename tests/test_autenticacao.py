"""Seção 3: [G] gestor, [E] equipe, token do lead e rotas públicas."""
import pytest

from conftest import CODIGOS, TEL, ok


@pytest.mark.parametrize("rota", ["/api/saida", "/api/gestor/hoje", "/api/gestor/config", "/api/gestor/ao-vivo"])
def test_gestor_sem_token_ou_errado_401(api, rota):
    assert api.get(rota, token=None)[0] == 401
    assert api.get(rota, token="errado")[0] == 401
    assert api.get(rota)[0] == 200


def test_equipe_codigo_errado_401(api):
    assert api.get("/api/equipe/eu", token=None, codigo="nao-existe")[0] == 401
    assert api.get("/api/equipe/eu", token=None)[0] == 401


def test_equipe_codigo_certo_age_como_colaborador(api):
    eu = api.eu("bruno")
    assert eu["id"] == "bruno" and eu["nome"] == "Bruno"
    assert eu["status"] == "fora"  # seção 6: começa fora


def test_codigo_de_equipe_nao_abre_rota_de_gestor(api):
    assert api.get("/api/gestor/hoje", token=None, codigo=CODIGOS["ana"])[0] == 401


def test_gestor_passa_em_rota_de_equipe_com_colaborador(api):
    st, r = api.post("/api/equipe/status", {"status": "livre", "colaborador": "carla"})
    assert ok(st), (st, r)
    assert api.colab("carla")["status"] == "livre"


def test_painel_aceita_gestor_e_equipe(api):
    assert api.get("/api/painel")[0] == 200
    assert api.get("/api/painel", codigo=CODIGOS["ana"])[0] == 200
    assert api.get("/api/painel", token=None)[0] == 401


def test_token_do_lead(api):
    lead = api.msg_full(TEL, "oi")["lead"]
    assert isinstance(lead["token"], str) and len(lead["token"]) >= 16
    assert api.get(f"/api/meu/{lead['token']}", token=None)[0] == 200
    assert api.get("/api/meu/token-que-nao-existe-123456", token=None)[0] == 404
    assert api.get("/meu/token-que-nao-existe-123456", token=None)[0] == 404


def test_tokens_de_leads_diferentes_sao_diferentes(api):
    a = api.msg_full("(41) 99999-0001", "oi")["lead"]["token"]
    b = api.msg_full("(41) 99999-0002", "oi")["lead"]["token"]
    assert a != b


@pytest.mark.parametrize("rota", ["/", "/widget.js", "/equipe", "/gestor", "/api/saude"])
def test_rotas_publicas(api, rota):
    assert api.get(rota, token=None)[0] == 200
