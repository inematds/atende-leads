"""Seções 7a e 14: sugestão de resposta à equipe (Telegram sg:ok/ed, painel), aprendizado com as 3 origens,
cérebro anthropic/openrouter/CLI contra falsos locais (corpo, recusa, timeout → regras)."""
import time

import pytest

from conftest import (CODIGOS, TEL, TEL_D, TG_ID, Servidor, Tg, callbacks, env_integracoes, equipe_pronta,
                      esperar, ok)
from falsos import FalsoLLM, cfg_cerebro, cli_falso

FAQ_ENDERECO = "Ficamos na Rua Exemplo, 100, Centro."
ANTHROPIC = {"tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low"}


@pytest.fixture
def llm():
    f = FalsoLLM()
    yield f
    f.fechar()


def subir(dados, externo=None, env=None):
    e = dict(env_integracoes(externo)) if externo else {}
    e.update(env or {})
    return Servidor(dados, env=e).subir()


def env_anthropic(llm, **extra):
    return dict({"CEREBRO_API_KEY": "sk-falsa-teste", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"}, **extra)


def aprendizado(api, **q):
    qs = "&".join(f"{k}={v}" for k, v in q.items())
    st, r = api.get("/api/gestor/aprendizado" + ("?" + qs if qs else ""))
    assert st == 200, (st, r)
    return r


def em_atendimento(api, tg):
    equipe_pronta(api, tg, ("ana",))
    lead, ch = api.atendendo("ana")
    return lead, ch


def sugestoes(externo):
    return [p for p in externo.privado("ana") if str(p["json"].get("text", "")).startswith("💡 Sugestão:")]


def sg_ids(p):
    return [d for d in callbacks(p) if d.startswith("sg:")]


# ------------------------------------------------------------ sugestão por regras + Telegram

def test_sugestao_regras_no_telegram_e_enviar(dados, externo):
    api = subir(dados, externo)
    tg = Tg(api)
    lead, ch = em_atendimento(api, tg)
    api.msg(TEL, "onde fica a loja?")
    assert esperar(lambda: sugestoes(externo)), externo.textos(externo.privado("ana"))
    textos = [str(p["json"].get("text")) for p in externo.privado("ana")]
    i_msg = next(i for i, t in enumerate(textos) if t.startswith("💬") and "onde fica a loja" in t)
    i_sug = next(i for i, t in enumerate(textos) if t.startswith("💡 Sugestão:"))
    assert i_sug > i_msg  # depois do 💬
    p = sugestoes(externo)[-1]
    assert p["json"]["text"] == f"💡 Sugestão: {FAQ_ENDERECO}"
    ok_cb, ed_cb = sg_ids(p)
    assert ok_cb.endswith(":ok") and ed_cb.endswith(":ed")
    tg.cb(TG_ID["ana"], ok_cb)
    assert esperar(lambda: FAQ_ENDERECO in externo.whats_texto(TEL_D))
    assert esperar(lambda: externo.com_texto(externo.tg("editMessageText"), f"✅ Enviada: {FAQ_ENDERECO}"))
    r = aprendizado(api)
    it = r["itens"][0]
    assert it["origem"] == "sugestao_ok" and it["distancia"] == 1.0 and it["sugestao"] == FAQ_ENDERECO
    assert it["enviado"] == FAQ_ENDERECO and "onde fica a loja" in it["msg_lead"] and it["colaborador"] == "ana"
    assert it["lead_id"] == lead["id"] and it["chamado_id"] == ch
    # o mesmo botão de novo: já usada
    cbid = tg.cb(TG_ID["ana"], ok_cb)
    assert esperar(lambda: any("já foi usada" in a["json"].get("text", "") for a in externo.tg("answerCallbackQuery")
                               if a["json"].get("callback_query_id") == cbid))


def test_sugestao_editar_por_reply(dados, externo):
    api = subir(dados, externo)
    tg = Tg(api)
    em_atendimento(api, tg)
    api.msg(TEL, "onde fica a loja?")
    assert esperar(lambda: sugestoes(externo))
    ed_cb = sg_ids(sugestoes(externo)[-1])[1]
    tg.cb(TG_ID["ana"], ed_cb)
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "Mande o texto editado respondendo a esta mensagem"))
    pedido = externo.com_texto(externo.privado("ana"), "Mande o texto editado")[-1]
    editado = "Ficamos na Rua Exemplo, 100, Centro, ao lado da praça."
    tg.msg(TG_ID["ana"], editado, reply_to=pedido["message_id"])
    assert esperar(lambda: editado in externo.whats_texto(TEL_D))
    it = aprendizado(api)["itens"][0]
    assert it["origem"] == "sugestao_editada" and 0 < it["distancia"] < 1 and it["enviado"] == editado


def test_reply_livre_com_sugestao_vira_ignorada(dados, externo):
    api = subir(dados, externo)
    tg = Tg(api)
    em_atendimento(api, tg)
    api.msg(TEL, "onde fica a loja?")
    assert esperar(lambda: sugestoes(externo))
    msg = externo.com_texto(externo.privado("ana"), "💬")[-1]
    tg.msg(TG_ID["ana"], "Te mando a localização no mapa já já.", reply_to=msg["message_id"])
    assert esperar(lambda: aprendizado(api)["itens"])
    it = aprendizado(api)["itens"][0]
    assert it["origem"] == "livre" and it["sugestao"] == FAQ_ENDERECO and it["distancia"] < 1
    c = aprendizado(api)["contadores"]
    assert c["ignoradas"] == 1 and c["com_sugestao"] == 1 and c["pct_ignoradas"] == 100.0
    assert esperar(lambda: externo.com_texto(externo.tg("editMessageText"), "💡 Sugestão (não usada)"))


def test_sem_sugestao_quando_regras_nao_casam(dados, externo):
    api = subir(dados, externo)
    tg = Tg(api)
    _lead, ch = em_atendimento(api, tg)
    api.msg(TEL, "zzz qqq www")
    externo.quieto()
    assert not sugestoes(externo)
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "Oi, pode repetir?"}, codigo=CODIGOS["ana"])
    assert ok(st), r
    it = aprendizado(api)["itens"][0]
    assert it["origem"] == "livre" and it["sugestao"] is None and it["distancia"] is None


def test_painel_traz_sugestao_e_responder_com_sugestao_id(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.msg(TEL, "onde fica a loja?")
    st, f = api.get(f"/api/equipe/leads/{lead['id']}", codigo=CODIGOS["ana"])
    assert st == 200 and f["sugestao"]["texto"] == FAQ_ENDERECO
    sid = f["sugestao"]["id"]
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": FAQ_ENDERECO, "sugestao_id": sid},
                     codigo=CODIGOS["ana"])
    assert ok(st), r
    assert aprendizado(api)["itens"][0]["origem"] == "sugestao_ok"
    st, f = api.get(f"/api/equipe/leads/{lead['id']}", codigo=CODIGOS["ana"])
    assert f["sugestao"] is None  # usada
    # sugestao_id de outro chamado / inexistente → 422
    api.msg(TEL, "onde fica a loja mesmo?")
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "x", "sugestao_id": 9999}, codigo=CODIGOS["ana"])
    assert st == 422


def test_resposta_sem_mensagem_pendente_nao_grava(api):
    api.status("ana", "livre")
    _lead, ch = api.atendendo("ana")
    api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "Olá!"}, codigo=CODIGOS["ana"])
    n = len(aprendizado(api)["itens"])
    api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "Ainda está aí?"}, codigo=CODIGOS["ana"])
    assert len(aprendizado(api)["itens"]) == n


def test_apagar_meus_dados_apaga_aprendizado(api):
    api.status("ana", "livre")
    _lead, ch = api.atendendo("ana")
    api.msg(TEL, "onde fica a loja?")
    api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": "Rua Exemplo, 100."}, codigo=CODIGOS["ana"])
    assert aprendizado(api)["itens"]
    api.msg(TEL, "apagar meus dados")
    assert aprendizado(api)["itens"] == []


# ------------------------------------------------------------ cérebro anthropic (servidor falso)

def test_anthropic_corpo_headers_e_resposta(dados, llm):
    llm.texto = "Entregamos em todo o Brasil em até 5 dias úteis."
    api = subir(dados, env=env_anthropic(llm))
    cfg_cerebro(api, ANTHROPIC)
    s = api.get("/api/saude")[1]
    assert s["cerebro"] == "anthropic" and s["cerebro_ok"] is True
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert api.msg(TEL, "vocês entregam em Curitiba?") == llm.texto
    p = [x for x in llm.lista() if x["rota"] == "/v1/messages"][-1]
    j, h = p["json"], p["headers"]
    assert h["x-api-key"] == "sk-falsa-teste" and h["anthropic-version"] == "2023-06-01"
    assert h["anthropic-beta"] == "server-side-fallback-2026-07-01" and "application/json" in h["content-type"]
    assert j["model"] == "claude-sonnet-5-5" and j["max_tokens"] == 1024
    assert j["output_config"] == {"effort": "low"} and j["fallbacks"] == "default"
    for proibido in ("thinking", "temperature", "top_p", "top_k"):
        assert proibido not in j
    assert j["messages"][-1]["role"] == "user" and all(m["role"] == "user" for m in j["messages"])
    sistema = j["system"]
    assert isinstance(sistema, list) and sistema[-1]["cache_control"] == {"type": "ephemeral"}
    assert "português do Brasil" in sistema[0]["text"] and "Plano anual" in sistema[-1]["text"]


def test_anthropic_recusa_cai_nas_regras(dados, llm):
    llm.recusa = True
    api = subir(dados, env=env_anthropic(llm))
    cfg_cerebro(api, ANTHROPIC)
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert "não sei responder" in api.msg(TEL, "vocês entregam em Curitiba?").lower()
    assert llm.lista()


def test_anthropic_timeout_cai_nas_regras(dados, llm):
    llm.atraso = 3
    api = subir(dados, env=env_anthropic(llm, CEREBRO_TIMEOUT_S="1"))
    cfg_cerebro(api, ANTHROPIC)
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    t0 = time.time()
    assert "não sei responder" in api.msg(TEL, "vocês entregam em Curitiba?").lower()
    assert time.time() - t0 < 2.8


def test_anthropic_sem_chave_saude_e_regras(dados, llm):
    api = subir(dados, env={"CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"})
    cfg_cerebro(api, ANTHROPIC)
    s = api.get("/api/saude")[1]
    assert s["cerebro_ok"] is False and "CEREBRO_API_KEY" in s["cerebro_motivo"]
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert "não sei responder" in api.msg(TEL, "vocês entregam em Curitiba?").lower()
    assert llm.lista() == []


def test_chave_nunca_aparece_na_config(dados, llm):
    api = subir(dados, env=env_anthropic(llm))
    cfg_cerebro(api, ANTHROPIC)
    st, b = api.get("/api/gestor/config", bruto=True)
    assert b"sk-falsa-teste" not in b


def test_sugestao_llm_assincrona(dados, externo, llm):
    llm.texto = "Oi Maria! Ficamos na Rua Exemplo, 100. Quer que eu mande a localização?"
    llm.atraso = 1.5
    api = subir(dados, externo, env_anthropic(llm))
    cfg_cerebro(api, ANTHROPIC)
    tg = Tg(api)
    em_atendimento(api, tg)
    t0 = time.time()
    api.msg(TEL, "vocês ficam onde?")
    assert time.time() - t0 < 1.4  # a resposta ao lead não espera o modelo
    assert esperar(lambda: sugestoes(externo), timeout=8)
    assert sugestoes(externo)[-1]["json"]["text"] == f"💡 Sugestão: {llm.texto}"
    p = [x for x in llm.lista() if x["rota"] == "/v1/messages"][-1]
    assert "vocês ficam onde?" in p["json"]["messages"][-1]["content"]
    assert "Maria" in p["json"]["messages"][-1]["content"]


# ------------------------------------------------------------ openrouter e CLI

def test_openrouter_headers(dados, llm):
    llm.texto = "Entregamos sim."
    api = subir(dados, env={"CEREBRO_API_KEY": "sk-or-falsa", "CEREBRO_OPENROUTER_URL": llm.url + "/api/v1/chat/completions"})
    cfg_cerebro(api, {"tipo": "openrouter", "modelo": "z-ai/glm-5"})
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert api.msg(TEL, "vocês entregam em Curitiba?") == "Entregamos sim."
    p = llm.lista()[-1]
    assert p["headers"]["authorization"] == "Bearer sk-or-falsa" and p["headers"]["x-title"] == "atende-leads"
    assert p["headers"]["http-referer"] == "https://loja.exemplo.test"
    assert p["json"]["model"] == "z-ai/glm-5" and p["json"]["messages"][0]["role"] == "system"


def test_claude_cli_binario_falso(dados, tmp_path):
    exe = cli_falso(tmp_path, "Resposta do CLI.")
    api = subir(dados, env={"CEREBRO_CLI_BIN": str(exe)})
    cfg_cerebro(api, {"tipo": "claude_cli", "modelo": "sonnet"})
    assert api.get("/api/saude")[1]["cerebro_ok"] is True
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert api.msg(TEL, "vocês entregam em Curitiba?") == "Resposta do CLI."
    assert (tmp_path / "args.txt").read_text().split() == ["-p", "--model", "sonnet"]
    assert "vocês entregam em Curitiba?" in (tmp_path / "stdin.txt").read_text()


def test_codex_cli_binario_falso(dados, tmp_path):
    exe = cli_falso(tmp_path, "Resposta do Codex.")
    api = subir(dados, env={"CEREBRO_CLI_BIN": str(exe)})
    cfg_cerebro(api, {"tipo": "codex_cli", "modelo": "gpt-6-luna"})
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert api.msg(TEL, "vocês entregam em Curitiba?") == "Resposta do Codex."
    assert (tmp_path / "args.txt").read_text().split() == ["exec", "-m", "gpt-6-luna", "-s", "read-only",
                                                           "--skip-git-repo-check", "-"]


def test_cli_ausente_saude_e_regras(dados, tmp_path):
    api = subir(dados, env={"CEREBRO_CLI_BIN": str(tmp_path / "nao-existe")})
    cfg_cerebro(api, {"tipo": "claude_cli", "modelo": "sonnet"})
    s = api.get("/api/saude")[1]
    assert s["cerebro_ok"] is False and "não encontrado" in s["cerebro_motivo"]
    api.msg(TEL, "qual o horario de atendimento", nome="Ivo")
    assert "não sei responder" in api.msg(TEL, "vocês entregam em Curitiba?").lower()
