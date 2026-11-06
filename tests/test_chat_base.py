"""1.7.8 — seção 13b: chat da base. O gestor pergunta; a resposta vem só da base, com a seção citada; o que falta
volta como `lacuna` + rascunho de proposta (que vira proposta `nova` pelo POST /api/gestor/propostas); contradição
aponta o conflito da Base consolidada. Sem cérebro: busca por palavras. Nada é gravado. Cérebro falso local."""
import json

import pytest

from conftest import Servidor
from falsos import FalsoLLM, cfg_cerebro

PRINCIPAL = {"tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low"}


def eh_chat(corpo):
    return "GESTOR" in corpo["system"][0]["text"] and "conferindo a base" in corpo["system"][0]["text"]


@pytest.fixture
def llm():
    f = FalsoLLM()
    f.saida = {}
    f.texto = lambda corpo: f.saida if isinstance(f.saida, str) else json.dumps(f.saida, ensure_ascii=False)
    yield f
    f.fechar()


def subir_llm(dados, llm):
    api = Servidor(dados, env={"CEREBRO_API_KEY": "sk-falsa-teste",
                               "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"}).subir()
    cfg_cerebro(api, PRINCIPAL)
    return api


def n_propostas(api):
    st, ps = api.get("/api/gestor/propostas")
    return len(ps)


def test_sem_cerebro_busca_por_palavras_e_lacuna(api):
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "onde fica a loja?"})
    assert st == 200, r
    assert r["lacuna"] is False and r["origem"] == "regras"
    assert any(f["secao"] == "FAQ: onde fica a loja" and "Rua Exemplo, 100" in f["trecho"] for f in r["fontes"])
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "quanto custa o plano anual?"})
    assert any(f["secao"] == "Produtos" and f["trecho"] == "Plano anual: R$ 1.200" for f in r["fontes"]), r
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "que horas vocês abrem?"})
    assert any(f["secao"] == "Horários" for f in r["fontes"]), r
    antes = n_propostas(api)
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "vocês vendem bicicleta elétrica?"})
    assert st == 200 and r["lacuna"] is True and r["fontes"] == []
    assert r["resposta"].startswith("Isso não está na base.")
    assert r["proposta"]["tipo"] == "faq" and r["proposta"]["perguntas"] == ["vocês vendem bicicleta elétrica?"]
    assert n_propostas(api) == antes                          # o chat não grava nada
    for corpo in ({}, {"pergunta": "  "}, {"pergunta": "x" * 1001}, {"pergunta": "oi", "historico": "x"}):
        st, r = api.post("/api/gestor/base/perguntar", corpo)
        assert st == 422, (corpo, r)
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "oi"}, token="errado")
    assert st == 401


def test_com_cerebro_cita_secoes_e_aponta_o_conflito(dados, llm):
    api = subir_llm(dados, llm)
    st, cfg = api.get("/api/gestor/config")
    cfg["horarios"] = {d: [["00:00", "23:59"]] for d in ("seg", "ter", "qua", "qui", "sex", "sab", "dom")}
    st, r = api.put("/api/gestor/config", cfg)
    assert st == 200, r
    st, base = api.get("/api/gestor/base")
    i_hor = next(i for i, x in enumerate(base["conflitos"]) if x["alvo"] == "faq:horario")
    llm.saida = {"resposta": "Pelo FAQ, de segunda a sexta das 8h às 18h; pelos Horários, todos os dias 00:00–23:59.",
                 "fontes": [{"secao": "FAQ: qual o horario de atendimento",
                             "trecho": "Atendemos de segunda a sexta, das 8h às 18h."},
                            {"secao": "Horários", "trecho": "Nosso atendimento: seg a dom 00:00–23:59."}],
                 "lacuna": False, "contradicao": "O FAQ e os Horários dizem coisas diferentes.",
                 "proposta": {"tipo": "", "perguntas": [], "resposta": "", "campo": "", "nome": "", "preco_novo": "",
                              "produto_id": ""}}
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "qual o horário?",
                                                    "historico": [{"de": "gestor", "texto": "oi"},
                                                                  {"de": "base", "texto": "Olá!"}]})
    assert st == 200, r
    assert r["origem"] == "cerebro" and r["lacuna"] is False and r["proposta"] is None
    assert [f["secao"] for f in r["fontes"]] == ["FAQ: qual o horario de atendimento", "Horários"]
    assert r["contradicao"]
    assert any(x["alvo"] == "faq:horario" and x["indice"] == i_hor for x in r["conflitos"]), r["conflitos"]
    corpo = [p["json"] for p in llm.lista() if eh_chat(p["json"])][-1]
    assert corpo["model"] == "claude-sonnet-5-5" and corpo["max_tokens"] == 1024      # cérebro principal
    assert corpo["output_config"]["format"]["type"] == "json_schema"
    assert set(corpo["output_config"]["format"]["schema"]["required"]) >= {"resposta", "fontes", "lacuna", "proposta"}
    assert "Atendemos de segunda a sexta" in corpo["system"][1]["text"]              # o texto da base
    assert "faq:horario" in corpo["system"][0]["text"]                                # conflitos já achados
    usuario = corpo["messages"][0]["content"]
    assert "Gestor: oi" in usuario and "Resposta: Olá!" in usuario and "qual o horário?" in usuario


def test_lacuna_vira_proposta_editavel_pelo_gestor(dados, llm):
    api = subir_llm(dados, llm)
    llm.saida = {"resposta": "Isso não está na base. Não há informação sobre entrega.", "fontes": [], "lacuna": True,
                 "contradicao": "", "proposta": {"tipo": "info", "perguntas": ["vocês entregam?"], "resposta": "",
                                                 "campo": "entrega", "nome": "", "preco_novo": "", "produto_id": ""}}
    antes = n_propostas(api)
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "vocês entregam?"})
    assert st == 200 and r["lacuna"] is True, r
    assert r["proposta"]["tipo"] == "info" and r["proposta"]["campo"] == "entrega"
    assert n_propostas(api) == antes
    p = dict(r["proposta"], resposta="Entregamos em Curitiba em até 2 dias úteis.", origem="chat")
    st, r = api.post("/api/gestor/propostas", p)
    assert st == 200, r
    nova = r["proposta"]
    assert nova["status"] == "nova" and nova["origem"] == "chat" and nova["campo"] == "entrega"
    assert "Entrega" in nova["destino"]
    st, r = api.post(f"/api/gestor/propostas/{nova['id']}/incorporar", {})
    assert st == 200, r
    st, cfg = api.get("/api/gestor/config")
    assert cfg["info"]["entrega"] == "Entregamos em Curitiba em até 2 dias úteis."
    # validação: tipo, campo, bastidor, repetida
    for corpo in ({"tipo": "x"}, {"tipo": "info", "campo": "nada", "resposta": "x"},
                  {"tipo": "faq", "perguntas": ["a?"], "resposta": "A base diz que sim."},
                  {"tipo": "preco", "produto_id": "plano-anual", "preco_novo": "barato"}):
        st, r = api.post("/api/gestor/propostas", corpo)
        assert st == 422, (corpo, r)
    st, r = api.post("/api/gestor/propostas", {"tipo": "faq", "perguntas": "tem estacionamento?", "resposta": "Sim, grátis."})
    assert st == 200, r
    st, r = api.post("/api/gestor/propostas", {"tipo": "faq", "perguntas": ["tem estacionamento?"], "resposta": "Sim, grátis."})
    assert st == 409


def test_saida_em_texto_livre_e_falha_do_cerebro(dados, llm):
    api = subir_llm(dados, llm)
    llm.saida = "Atendemos de segunda a sexta, das 8h às 18h (FAQ: horário)."
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "qual o horário?"})
    assert st == 200 and r["resposta"].startswith("Atendemos") and r["fontes"] == []
    llm.recusa = True                                          # recusa → busca por palavras
    st, r = api.post("/api/gestor/base/perguntar", {"pergunta": "onde fica a loja?"})
    assert st == 200 and r["origem"] == "regras" and r["fontes"]
