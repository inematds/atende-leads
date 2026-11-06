"""1.5.4 — aparência do chat do lead (seção 2 `aparencia`, seção 11) e Cadastros em formulário (seção 13)."""
import copy
import json

import pytest

from conftest import CODIGOS, NEGOCIO


def _cfg(api):
    return api.get("/api/gestor/config")[1]


def _com_aparencia(api, ap):
    cfg = _cfg(api)
    cfg["aparencia"] = ap
    return api.put("/api/gestor/config", cfg)


# ------------------------------------------------------------ GET /api/aparencia (pública)

def test_aparencia_padrao_publica(api):
    st, ap = api.get("/api/aparencia", token=None)
    assert st == 200
    assert ap == {"tema": "claro", "cor_destaque": None, "cor_destaque_texto": None, "nome_exibido": NEGOCIO}


def test_aparencia_configurada_so_os_campos_publicos(api, dados):
    st, r = _com_aparencia(api, {"tema": "marinho", "cor_destaque": "#1d4ed8", "nome_exibido": "Viva Pilates"})
    assert st == 200, r
    st, ap = api.get("/api/aparencia", token=None)
    assert st == 200
    assert ap == {"tema": "marinho", "cor_destaque": "#1d4ed8", "cor_destaque_texto": "#ffffff",
                  "nome_exibido": "Viva Pilates"}
    texto = json.dumps(ap)
    assert all(c not in texto for c in CODIGOS.values()) and "token" not in texto
    assert json.loads((dados / "negocio.json").read_text())["aparencia"]["tema"] == "marinho"


def test_aparencia_cor_clara_usa_letra_escura(api):
    assert _com_aparencia(api, {"tema": "escuro", "cor_destaque": "#FACC15"})[0] == 200
    ap = api.get("/api/aparencia", token=None)[1]
    assert ap["tema"] == "escuro" and ap["cor_destaque_texto"] == "#1a1206"
    assert ap["nome_exibido"] == NEGOCIO  # vazio/ausente = nome do negócio


@pytest.mark.parametrize("ap", [
    {"tema": "rosa"},
    {"cor_destaque": "azul"},
    {"cor_destaque": "#12345"},
    {"cor_destaque": "#1234567"},
    {"cor_destaque": "#GGGGGG"},
    {"nome_exibido": "x" * 81},
    {"nome_exibido": 12},
    {"fonte": "Comic Sans"},
])
def test_aparencia_invalida_422_nada_muda(api, dados, ap):
    antes = (dados / "negocio.json").read_text()
    st, r = _com_aparencia(api, ap)
    assert st == 422, (ap, r)
    assert (dados / "negocio.json").read_text() == antes
    assert api.get("/api/aparencia", token=None)[1]["tema"] == "claro"


def test_aparencia_contraste_abaixo_de_aa_422_com_mensagem(api, dados):
    antes = (dados / "negocio.json").read_text()
    st, r = _com_aparencia(api, {"tema": "claro", "cor_destaque": "#777777"})  # 4,48:1 com branco
    assert st == 422
    assert "contraste" in r["erro"] and "4,5" in r["erro"]
    assert (dados / "negocio.json").read_text() == antes


def test_aparencia_objeto_obrigatorio(api):
    cfg = _cfg(api)
    cfg["aparencia"] = "escuro"
    assert api.put("/api/gestor/config", cfg)[0] == 422


def test_widget_usa_a_aparencia(api):
    assert _com_aparencia(api, {"tema": "escuro", "cor_destaque": "#1d4ed8"})[0] == 200
    st, js = api.get("/widget.js", token=None)
    assert st == 200 and "#1d4ed8" in js and '"escuro"' in js and "__APARENCIA__" not in js


# ------------------------------------------------------------ Cadastros em formulário (PUT config continua validando)

def _como_formulario(cfg):
    """O que o formulário de Cadastros manda: cada item = o objeto atual + os campos editados (nada se perde)."""
    novo = copy.deepcopy(cfg)
    novo["token_gestor"] = "***"
    novo["equipe"] = [dict(m, nome=m["nome"] + " Silva") for m in cfg["equipe"]]
    novo["equipe"].append({"id": "dani", "nome": "Dani Rocha", "telefone": "5541999990099",
                           "codigo": "Qm7rT2xK9pLw4ZsA"})  # "gerar novo": 16 caracteres aleatórios
    novo["produtos"] = [dict(p, palavras=list(p.get("palavras", [])) + ["promo"]) for p in cfg["produtos"]]
    novo["horarios"] = dict(cfg["horarios"], sab=[["09:00", "12:00"], ["14:00", "17:00"]], dom=[])
    return novo


def test_cadastros_formulario_grava(api, dados):
    cfg = _cfg(api)
    st, r = api.put("/api/gestor/config", _como_formulario(cfg))
    assert st == 200, r
    disco = json.loads((dados / "negocio.json").read_text())
    assert [m["id"] for m in disco["equipe"]][-1] == "dani"
    assert disco["equipe"][0]["codigo"] == CODIGOS["ana"]  # código mantido
    assert disco["horarios"]["sab"] == [["09:00", "12:00"], ["14:00", "17:00"]]
    assert all("promo" in p["palavras"] for p in disco["produtos"])
    assert disco["token_gestor"] != "***"
    # o novo código entra no painel da equipe
    assert api.get("/api/equipe/eu", token=None, codigo="Qm7rT2xK9pLw4ZsA")[0] == 200


@pytest.mark.parametrize("estraga", ["codigo_curto", "id_repetido", "hora_ruim", "janela_invertida",
                                     "produto_sem_nome", "telefone_letras"])
def test_cadastros_formulario_invalido_422(api, dados, estraga):
    cfg = _como_formulario(_cfg(api))
    if estraga == "codigo_curto":
        cfg["equipe"][-1]["codigo"] = "curto-123"
    elif estraga == "id_repetido":
        cfg["equipe"][-1]["id"] = "ana"
    elif estraga == "hora_ruim":
        cfg["horarios"]["sab"] = [["9h", "12:00"]]
    elif estraga == "janela_invertida":
        cfg["horarios"]["sab"] = [["14:00", "12:00"]]
    elif estraga == "produto_sem_nome":
        cfg["produtos"][0]["nome"] = " "
    elif estraga == "telefone_letras":
        cfg["equipe"][-1]["telefone"] = "(41) 9999"
    antes = (dados / "negocio.json").read_text()
    assert api.put("/api/gestor/config", cfg)[0] == 422
    assert (dados / "negocio.json").read_text() == antes
