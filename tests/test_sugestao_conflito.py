"""1.6.8 — seções 7a, 12, 13a, 14 e 16: a sugestão é a fala do vendedor (o que ele disse vale sobre a base),
conflito base × conversa vira aviso + "Atualizar a base" (proposta ao gestor, idempotente), propostas sem
bastidores, tipo `preco` com promoção e validade, info que acrescenta, cérebro da curadoria e a limpeza
`./atende manutencao limpar-bastidores`. Cérebro falso local; nada sai da máquina."""
import json
import subprocess
import sys

import pytest

from conftest import (CODIGOS, RAIZ, TEL, TG_ID, Servidor, Tg, callbacks, env_integracoes, equipe_pronta, esperar,
                      ok)
from falsos import FalsoLLM, cfg_cerebro

sys.path.insert(0, str(RAIZ))
from src import sugestao as SUG  # noqa: E402  (parser: função pura)

PRINCIPAL = {"tipo": "anthropic", "modelo": "claude-sonnet-5-5", "esforco": "low"}
CURADORIA = {"tipo": "anthropic", "modelo": "claude-opus-5-5", "esforco": "medium"}
CONFLITO = "A base diz R$ 1.200 para o Plano anual; você informou R$ 670 (promoção Black)."
RESP_SUG = "Oi, Maria! O Plano anual está por R$ 670 na promoção Black. Quer que eu já reserve?"


def eh_sugestao(corpo):
    return "PRÓXIMA MENSAGEM do vendedor" in corpo["system"][0]["text"]


def eh_curadoria(corpo):
    return "melhorar a base de conhecimento" in corpo["system"][0]["text"]


@pytest.fixture
def llm():
    f = FalsoLLM()
    f.propostas = {"propostas": []}

    def responder(corpo):
        if eh_sugestao(corpo):
            return json.dumps({"resposta": RESP_SUG, "conflito": CONFLITO}, ensure_ascii=False)
        if eh_curadoria(corpo):
            return json.dumps(f.propostas, ensure_ascii=False)
        return "SEM_RESPOSTA"
    f.texto = responder
    yield f
    f.fechar()


def subir(dados, llm, externo=None):
    env = dict(env_integracoes(externo)) if externo else {}
    env.update({"CEREBRO_API_KEY": "sk-falsa-teste", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"})
    return Servidor(dados, env=env).subir()


def pedidos(llm, filtro):
    return [p["json"] for p in llm.lista() if p["rota"] == "/v1/messages" and filtro(p["json"])]


def vendedor_disse(api, ch, texto):
    st, r = api.post(f"/api/equipe/chamados/{ch}/responder", {"texto": texto}, codigo=CODIGOS["ana"])
    assert ok(st), (st, r)


def ficha_sug(api, lead_id):
    st, f = api.get(f"/api/equipe/leads/{lead_id}", codigo=CODIGOS["ana"])
    assert st == 200, (st, f)
    return f["sugestao"]


def propostas(api):
    st, r = api.get("/api/gestor/propostas")
    assert st == 200, (st, r)
    return r


# ------------------------------------------------------------ parser (função pura)

def test_parser_json_puro_cercado_e_texto_livre():
    assert SUG.ler_sugestao('{"resposta": "Olá!", "conflito": "x"}') == ("Olá!", "x")
    assert SUG.ler_sugestao('```json\n{"resposta": "Oi, tudo bem?", "conflito": ""}\n```') == ("Oi, tudo bem?", "")
    assert SUG.ler_sugestao('Claro:\n```\n{"resposta": "R$ 670", "conflito": "c"}\n```') == ("R$ 670", "c")
    assert SUG.ler_sugestao("Oi! Posso te ajudar com o plano?") == ("Oi! Posso te ajudar com o plano?", "")
    assert SUG.ler_sugestao("") == ("", "")
    assert SUG.ler_sugestao('{"resposta": "ok"}') == ("ok", "")  # conflito ausente = vazio


# ------------------------------------------------------------ sugestão com conflito, prompt e painel

def test_sugestao_com_conflito_prompt_ficha_e_base(dados, llm):
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL, extra={"cerebro_curadoria": CURADORIA})
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    vendedor_disse(api, ch, "O Plano anual está R$ 700.")
    vendedor_disse(api, ch, "Corrigindo: na promoção Black o Plano anual sai por R$ 670.")
    api.msg(TEL, "e até quando vale esse preço?")
    assert esperar(lambda: (ficha_sug(api, lead["id"]) or {}).get("conflito"), timeout=8)
    sg = ficha_sug(api, lead["id"])
    assert sg["texto"] == RESP_SUG and sg["conflito"] == CONFLITO and not sg["proposta_id"]
    # o PROMPT: fala do vendedor em 1ª pessoa, ordem de verdade, último valor, sem bastidores, JSON
    p = pedidos(llm, eh_sugestao)[-1]
    sistema = p["system"][0]["text"]
    for trecho in ("primeira pessoa", "Ordem de verdade", "vale sobre a base", "vale o ÚLTIMO",
                   "nunca mencione base", "não peça desculpa", '"resposta"', '"conflito"'):
        assert trecho in sistema, trecho
    assert "Se a base não responder, diga que vai chamar alguém da equipe" not in sistema
    assert p["model"] == "claude-sonnet-5-5" and p["output_config"]["effort"] == "low"  # sugestão = principal
    fmt = p["output_config"]["format"]
    assert fmt["type"] == "json_schema" and set(fmt["schema"]["required"]) == {"resposta", "conflito"}
    assert "R$ 670" in p["messages"][-1]["content"] and "R$ 700" in p["messages"][-1]["content"]
    assert "R$ 1.200" in p["system"][1]["text"]  # a base vai junto
    # Atualizar a base: cria a proposta uma vez só
    st, r = api.post(f"/api/equipe/sugestoes/{sg['id']}/base", {}, codigo=CODIGOS["ana"])
    assert st == 200 and r["ok"] is True and r["proposta"], (st, r)
    pid = r["proposta"]
    st, r2 = api.post(f"/api/equipe/sugestoes/{sg['id']}/base", {}, codigo=CODIGOS["ana"])
    assert st == 200 and r2["proposta"] == pid
    nossas = [x for x in propostas(api) if x.get("sugestao_id") == sg["id"]]
    assert len(nossas) == 1 and nossas[0]["id"] == pid and nossas[0]["status"] == "nova"
    pr = nossas[0]
    assert pr["tipo"] == "preco" and pr["produto_id"] == "plano-anual" and pr["preco_novo"] == "R$ 670"
    assert pr["promocao"] == "Promoção Black" and pr["origem"] == "vendedor"
    assert CONFLITO in pr["justificativa"] and "R$ 670" in pr["justificativa"]  # o porquê fica na justificativa
    assert "base diz" not in pr["resposta"].lower()  # o recado interno nunca vira texto da base
    assert pr["atual"] == "Plano anual: R$ 1.200"
    assert ficha_sug(api, lead["id"])["proposta_id"] == pid
    # sem conflito → 422; de outro vendedor → 409
    st, _ = api.post(f"/api/equipe/sugestoes/{sg['id']}/base", {}, codigo=CODIGOS["bruno"])
    assert st == 409


def test_telegram_sugestao_com_aviso_e_botao_sb(dados, externo, llm):
    api = subir(dados, llm, externo)
    cfg_cerebro(api, PRINCIPAL)
    tg = Tg(api)
    equipe_pronta(api, tg, ("ana",))
    lead, ch = api.atendendo("ana")
    vendedor_disse(api, ch, "Na promoção Black o Plano anual sai por R$ 670.")
    api.msg(TEL, "fechado, como pago?")

    def sug_tg():
        return [p for p in externo.privado("ana") if str(p["json"].get("text", "")).startswith("💡 Sugestão:")]
    assert esperar(sug_tg, timeout=8)
    p = sug_tg()[-1]
    assert p["json"]["text"] == f"💡 Sugestão: {RESP_SUG}\n\n⚠️ {CONFLITO}"
    sb = [d for d in callbacks(p) if d.startswith("sb:")]
    assert len(sb) == 1 and any(d.endswith(":ok") for d in callbacks(p))
    cbid = tg.cb(TG_ID["ana"], sb[0])
    assert esperar(lambda: any(a["json"].get("callback_query_id") == cbid and a["json"].get("text") == "Enviado ao gestor ✓"
                               for a in externo.tg("answerCallbackQuery")))
    tg.cb(TG_ID["ana"], sb[0])  # de novo: idempotente
    sid = int(sb[0].split(":")[1])
    assert esperar(lambda: len([x for x in propostas(api) if x.get("sugestao_id") == sid]) == 1)
    assert len(propostas(api)) == 1


def test_sugestao_sem_conflito_telegram_igual_ao_antigo(dados, externo, llm):
    llm.texto = lambda corpo: '```json\n{"resposta": "Oi! Ficamos na Rua Exemplo, 100.", "conflito": ""}\n```'
    api = subir(dados, llm, externo)
    cfg_cerebro(api, PRINCIPAL)
    tg = Tg(api)
    equipe_pronta(api, tg, ("ana",))
    lead, ch = api.atendendo("ana")
    api.msg(TEL, "vocês ficam onde?")

    def sug_tg():
        return [p for p in externo.privado("ana") if str(p["json"].get("text", "")).startswith("💡 Sugestão:")]
    assert esperar(sug_tg, timeout=8)
    p = sug_tg()[-1]
    assert p["json"]["text"] == "💡 Sugestão: Oi! Ficamos na Rua Exemplo, 100."
    assert not [d for d in callbacks(p) if d.startswith("sb:")]
    sg = ficha_sug(api, lead["id"])
    assert sg["conflito"] == ""
    st, _ = api.post(f"/api/equipe/sugestoes/{sg['id']}/base", {}, codigo=CODIGOS["ana"])
    assert st == 422


# ------------------------------------------------------------ resposta automática com atendente na conversa

def test_resposta_automatica_usa_o_que_o_atendente_disse(dados, llm):
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    vendedor_disse(api, ch, "Na promoção Black o Plano anual sai por R$ 670.")
    st, r = api.post(f"/api/equipe/chamados/{ch}/devolver", {}, codigo=CODIGOS["ana"])
    assert ok(st), (st, r)
    antes = len(pedidos(llm, lambda c: True))
    api.msg(TEL, "e aquela condição especial continua valendo pra mim?")
    novos = [p for p in pedidos(llm, lambda c: True)[antes:] if not eh_sugestao(p) and not eh_curadoria(p)]
    assert novos, "a dúvida devia ir ao cérebro"
    p = novos[-1]
    assert "Ordem de verdade" in p["system"][0]["text"] and "SEM_RESPOSTA" in p["system"][0]["text"]
    assert "R$ 670" in p["messages"][-1]["content"] and "condição especial" in p["messages"][-1]["content"]


def test_resposta_automatica_sem_atendente_nao_muda(dados, llm):
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    st, r = api.post("/api/gestor/testar", {"texto": "vocês trabalham com algum tipo de parceria cultural?"})
    assert st == 200, r
    ps = [p for p in pedidos(llm, lambda c: True) if not eh_sugestao(p) and not eh_curadoria(p)]
    assert ps and "Ordem de verdade" not in ps[-1]["system"][0]["text"]
    assert ps[-1]["messages"][-1]["content"] == "vocês trabalham com algum tipo de parceria cultural?"


# ------------------------------------------------------------ propostas: curadoria, bastidores, preço, info

def _registro(api):
    """Um registro de aprendizado (resposta livre do vendedor a uma mensagem do lead)."""
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    api.msg(TEL, "quanto está o plano anual?")
    vendedor_disse(api, ch, "Na promoção Black o Plano anual sai por R$ 670 até 30/11.")
    return lead, ch


def test_propostas_usam_curadoria_filtram_bastidor_e_validam_preco(dados, llm):
    llm.propostas = {"propostas": [
        {"tipo": "info", "campo": "observacoes", "resposta": "O vendedor informou duas vezes o Plano anual por R$ 670. "
         "A base atual diz R$ 1.200. Confirmar com a equipe.", "justificativa": "divergência"},
        {"tipo": "faq", "perguntas": ["tem promoção?"], "resposta": "Segundo o vendedor, sim.", "justificativa": "x"},
        {"tipo": "info", "campo": "pagamento", "resposta": "Pix e cartão em até 12x.", "justificativa": "vendedores"},
        {"tipo": "preco", "produto_id": "plano-anual", "preco_novo": "R$ 670", "promocao": "Promoção Black",
         "validade": "2026-11-30", "justificativa": "O vendedor informou R$ 670; a base diz R$ 1.200."},
        {"tipo": "preco", "produto_id": "nao-existe", "preco_novo": "R$ 10", "justificativa": "x"},
        {"tipo": "preco", "produto_id": "curso-ingles", "preco_novo": "trezentos", "justificativa": "x"},
    ]}
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL, extra={"cerebro_curadoria": CURADORIA})
    st, s = api.get("/api/saude")
    cu = s["cerebro_curadoria"]
    assert cu["propria"] is True and cu["tipo"] == "anthropic" and cu["modelo"] == "claude-opus-5-5" and cu["ok"] is True
    _registro(api)
    st, r = api.post("/api/gestor/propostas/gerar", {})
    assert st == 200, (st, r)
    p = pedidos(llm, eh_curadoria)[-1]
    assert p["model"] == "claude-opus-5-5" and p["output_config"]["effort"] == "medium" and p["max_tokens"] == 4096
    assert "thinking" not in p
    sist = p["system"][0]["text"]
    assert "sem bastidores" in sist and '"preco"' in sist and "justificativa" in sist
    assert "plano-anual: Plano anual — R$ 1.200" in p["messages"][-1]["content"]
    tipos = sorted((x["tipo"], x.get("campo") or x.get("produto_id")) for x in r["propostas"])
    assert tipos == [("info", "pagamento"), ("preco", "plano-anual")], tipos
    # sugestões continuam no principal
    assert all(x["model"] == "claude-sonnet-5-5" for x in pedidos(llm, eh_sugestao))
    # incorporar o preço com promoção: o normal fica, o promocional vale até a validade
    pr = next(x for x in r["propostas"] if x["tipo"] == "preco")
    st, r2 = api.post(f"/api/gestor/propostas/{pr['id']}/incorporar", {})
    assert st == 200, (st, r2)
    st, cfg = api.get("/api/gestor/config")
    plano = next(x for x in cfg["produtos"] if x["id"] == "plano-anual")
    assert plano["preco"] == "R$ 1.200" and plano["preco_promocao"] == "R$ 670"
    assert plano["promocao"] == "Promoção Black" and plano["promocao_ate"] == "2026-11-30"
    st, t = api.post("/api/gestor/testar", {"texto": "quero comprar o plano anual"})
    assert "R$ 670 (Promoção Black até 30/11)" in " ".join(t["respostas"]), t
    api.relogio("2026-12-01T10:00")
    st, t = api.post("/api/gestor/testar", {"texto": "quero comprar o plano anual"})
    assert "R$ 1.200" in " ".join(t["respostas"]) and "670" not in " ".join(t["respostas"]), t


def test_curadoria_ausente_usa_o_principal(dados, llm):
    llm.propostas = {"propostas": [{"tipo": "info", "campo": "entrega", "resposta": "Entregamos em todo o Brasil.",
                                    "justificativa": "x"}]}
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    st, s = api.get("/api/saude")
    assert s["cerebro_curadoria"]["propria"] is False and s["cerebro_curadoria"]["tipo"] == "anthropic"
    _registro(api)
    st, r = api.post("/api/gestor/propostas/gerar", {})
    assert st == 200 and r["criadas"] == 1, r
    p = pedidos(llm, eh_curadoria)[-1]
    assert p["model"] == "claude-sonnet-5-5" and p["max_tokens"] == 4096


def test_curadoria_valida_como_o_cerebro(dados, llm):
    api = subir(dados, llm)
    st, cfg = api.get("/api/gestor/config")
    for ruim in ({"tipo": "xyz"}, {"tipo": "anthropic", "esforco": "turbo"}, {"tipo": "anthropic", "api_key": "x"},
                 {"tipo": "anthropic", "modelo": "-x"}):
        st, r = api.put("/api/gestor/config", dict(cfg, cerebro_curadoria=ruim))
        assert st == 422, (ruim, st, r)
    st, r = api.put("/api/gestor/config", dict(cfg, cerebro_curadoria={}))
    assert st == 200, r


def test_incorporar_info_acrescenta_sem_duplicar_e_recusa_bastidor(dados, llm):
    llm.propostas = {"propostas": [{"tipo": "info", "campo": "observacoes", "resposta": "Atendemos também aos sábados.",
                                    "justificativa": "x"}]}
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL, info={"observacoes": "Estacionamento gratuito."})
    _registro(api)

    def gerar_e_incorporar(corpo=None):
        st, r = api.post("/api/gestor/propostas/gerar", {})
        assert st == 200 and r["criadas"] == 1, r
        pid = r["propostas"][0]["id"]
        assert r["propostas"][0]["atual"] == "Estacionamento gratuito." or "Estacionamento" in r["propostas"][0]["atual"]
        return api.post(f"/api/gestor/propostas/{pid}/incorporar", corpo or {})
    st, r = gerar_e_incorporar()
    assert st == 200, r
    st, cfg = api.get("/api/gestor/config")
    assert cfg["info"]["observacoes"] == "Estacionamento gratuito.\nAtendemos também aos sábados."
    st, r = gerar_e_incorporar()  # o mesmo texto de novo: não duplica
    assert st == 200, r
    st, cfg = api.get("/api/gestor/config")
    assert cfg["info"]["observacoes"] == "Estacionamento gratuito.\nAtendemos também aos sábados."
    # o gestor edita o texto: vale o editado; recado interno é recusado
    st, r = api.post("/api/gestor/propostas/gerar", {})
    pid = r["propostas"][0]["id"]
    st, r = api.post(f"/api/gestor/propostas/{pid}/incorporar", {"resposta": "O vendedor informou que abre sábado."})
    assert st == 422 and "recado interno" in str(r)
    st, r = api.post(f"/api/gestor/propostas/{pid}/incorporar", {"resposta": "Aos sábados, das 9h às 13h."})
    assert st == 200, r
    st, cfg = api.get("/api/gestor/config")
    assert cfg["info"]["observacoes"].endswith("\nAos sábados, das 9h às 13h.")


def test_incorporar_preco_editado_pelo_gestor(dados, llm):
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    vendedor_disse(api, ch, "O Plano anual sai por R$ 670 na promoção Black.")
    api.msg(TEL, "beleza, e como pago?")
    assert esperar(lambda: (ficha_sug(api, lead["id"]) or {}).get("conflito"), timeout=8)
    sid = ficha_sug(api, lead["id"])["id"]
    st, r = api.post(f"/api/equipe/sugestoes/{sid}/base", {}, codigo=CODIGOS["ana"])
    pid = r["proposta"]
    st, r = api.post(f"/api/gestor/propostas/{pid}/incorporar", {"preco_novo": "seiscentos"})
    assert st == 422
    st, r = api.post(f"/api/gestor/propostas/{pid}/incorporar", {"preco_novo": "R$ 990", "promocao": "", "validade": ""})
    assert st == 200, r
    st, cfg = api.get("/api/gestor/config")
    plano = next(x for x in cfg["produtos"] if x["id"] == "plano-anual")
    assert plano["preco"] == "R$ 990" and not plano.get("preco_promocao")


# ------------------------------------------------------------ manutenção: limpar bastidores do negocio.json

def test_manutencao_limpar_bastidores(dados):
    api = Servidor(dados).subir()  # cria o negocio.json da fixture
    st, cfg = api.get("/api/gestor/config")
    cfg["info"] = {"observacoes": "Estacionamento gratuito. O vendedor informou duas vezes o Plano anual por R$ 670, "
                                  "em promoção Black. A base atual diz R$ 1.200. Confirmar com a equipe qual é o "
                                  "preço vigente.", "endereco": "Rua Exemplo, 100."}
    cfg["faq"] = list(cfg.get("faq") or []) + [{"id": "ruim", "perguntas": ["promo?"],
                                                "resposta": "Segundo o vendedor, tem promoção."}]
    st, r = api.put("/api/gestor/config", dict(cfg, token_gestor="***"))
    assert st == 200, r
    exe = [str(RAIZ / "atende"), "manutencao", "limpar-bastidores", "--dados", str(dados)]
    arq = dados / "negocio.json"
    antes = arq.read_text(encoding="utf-8")
    sim = subprocess.run(exe, capture_output=True, text=True, timeout=30)
    assert sim.returncode == 0, sim.stderr
    assert "vendedor informou" in sim.stdout and "faq ruim" in sim.stdout and "Simulação" in sim.stdout
    assert arq.read_text(encoding="utf-8") == antes
    rodando = subprocess.run(exe + ["--aplicar"], capture_output=True, text=True, timeout=30)
    assert rodando.returncode != 0 and "rodando" in (rodando.stderr + rodando.stdout)  # servidor no ar: recusa
    from conftest import SERVIDORES
    while SERVIDORES:
        SERVIDORES.pop().parar()
    ap = subprocess.run(exe + ["--aplicar"], capture_output=True, text=True, timeout=30)
    assert ap.returncode == 0, ap.stderr
    novo = json.loads(arq.read_text(encoding="utf-8"))
    assert novo["info"]["observacoes"] == "Estacionamento gratuito."
    assert novo["info"]["endereco"] == "Rua Exemplo, 100."
    assert not [f for f in novo["faq"] if f["id"] == "ruim"]
    baks = list(dados.glob("negocio.json.*.bak"))
    assert len(baks) == 1 and "vendedor informou" in baks[0].read_text(encoding="utf-8")
    assert (arq.stat().st_mode & 0o777) == 0o600
    de_novo = subprocess.run(exe, capture_output=True, text=True, timeout=30)
    assert "Nada a remover" in de_novo.stdout


# ------------------------------------------------------------ destino estruturado: produto novo e horário

def test_propostas_produto_e_horario_gravam_no_cadastro(dados, llm):
    llm.propostas = {"propostas": [
        {"tipo": "produto", "nome": "Plano mensal", "palavras": ["mensal"], "preco_novo": "R$ 120", "justificativa": "x"},
        {"tipo": "produto", "nome": "Plano anual", "preco_novo": "R$ 1", "justificativa": "já existe"},
        {"tipo": "horario", "horarios": {"sab": [["09:00", "13:00"]]}, "resposta": "Sábado das 9h às 13h.",
         "justificativa": "vendedores"},
        {"tipo": "horario", "horarios": {"xyz": [["09:00", "13:00"]]}, "justificativa": "inválido"},
    ]}
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    _registro(api)
    st, r = api.post("/api/gestor/propostas/gerar", {})
    assert st == 200 and sorted(x["tipo"] for x in r["propostas"]) == ["horario", "produto"], r
    prod = next(x for x in r["propostas"] if x["tipo"] == "produto")
    hor = next(x for x in r["propostas"] if x["tipo"] == "horario")
    assert prod["destino"] == "Cadastros → Produtos → novo: Plano mensal (R$ 120)"
    assert hor["destino"].startswith("Cadastros → Horários:") and "sab 09:00–13:00" in hor["destino"]
    st, x = api.post(f"/api/gestor/propostas/{prod['id']}/incorporar", {"preco_novo": "R$ 130"})
    assert st == 200, x
    st, x = api.post(f"/api/gestor/propostas/{hor['id']}/incorporar", {})
    assert st == 200, x
    st, cfg = api.get("/api/gestor/config")
    novo = next(p for p in cfg["produtos"] if p["nome"] == "Plano mensal")
    assert novo["preco"] == "R$ 130" and novo["palavras"] == ["mensal"] and novo["id"] == "plano-mensal"
    assert cfg["horarios"]["sab"] == [["09:00", "13:00"]] and cfg["horarios"]["seg"]  # só o dia proposto muda


def test_destino_do_preco_no_formulario(dados, llm):
    llm.propostas = {"propostas": [{"tipo": "preco", "produto_id": "plano-anual", "preco_novo": "R$ 670",
                                    "justificativa": "x"}]}
    api = subir(dados, llm)
    cfg_cerebro(api, PRINCIPAL)
    _registro(api)
    st, r = api.post("/api/gestor/propostas/gerar", {})
    assert r["propostas"][0]["destino"] == "Cadastros → Produtos → Plano anual → preço: R$ 1.200 → R$ 670"
    st, x = api.post(f"/api/gestor/propostas/{r['propostas'][0]['id']}/incorporar", {})
    st, cfg = api.get("/api/gestor/config")
    assert next(p for p in cfg["produtos"] if p["id"] == "plano-anual")["preco"] == "R$ 670"


# ------------------------------------------------------------ base consolidada (seção 13b)

def _cfg_base(api, **mud):
    st, cfg = api.get("/api/gestor/config")
    cfg.update(mud)
    st, r = api.put("/api/gestor/config", dict(cfg, token_gestor="***"))
    assert st == 200, r
    return r


def test_base_consolidada_texto_e_conflitos(dados):
    api = Servidor(dados).subir()
    todos = {d: [["00:00", "23:59"]] for d in ("seg", "ter", "qua", "qui", "sex", "sab", "dom")}
    _cfg_base(api, horarios=todos,
              faq=[{"id": "hor", "perguntas": ["qual o horário de atendimento?"],
                    "resposta": "Atendemos de segunda a sexta, das 8h às 18h."},
                   {"id": "hor2", "perguntas": ["vocês abrem no domingo?"], "resposta": "Sim, todos os dias, 24h."},
                   {"id": "preco", "perguntas": ["quanto custa o plano anual?"], "resposta": "O Plano anual custa R$ 990."},
                   {"id": "a", "perguntas": ["tem estacionamento?"], "resposta": "Sim."},
                   {"id": "b", "perguntas": ["tem estacionamento?"], "resposta": "Não temos."},
                   {"id": "c", "perguntas": ["aceita pix?"], "resposta": "Sim."}],
              info={"observacoes": "O vendedor informou R$ 670. Confirmar com a equipe."},
              produtos=[{"id": "plano-anual", "nome": "Plano anual", "palavras": ["anual"], "preco": "R$ 1.200",
                         "preco_promocao": "R$ 670", "promocao": "Promoção Black", "promocao_ate": "2026-11-01"}])
    st, d = api.get("/api/gestor/base")
    assert st == 200, d
    st, cfg = api.get("/api/gestor/config")
    assert "Perguntas frequentes:" in d["texto"] and "Plano anual — preço R$ 1.200" in d["texto"]  # promo vencida
    assert d["secoes"]["produtos"][0]["promocao_ativa"] is False and d["secoes"]["info"]["observacoes"]
    por = {}
    for x in d["conflitos"]:
        por.setdefault(x["tipo"], []).append(x)
    assert [x["alvo"] for x in por["horario"]] == ["faq:hor"], por.get("horario")  # o caso real; o 24h bate
    assert "dias diferentes e horas diferentes" in por["horario"][0]["mensagem"]
    assert por["preco"][0]["alvo"] == "faq:preco" and "R$ 990" in por["preco"][0]["mensagem"]
    assert por["promocao_vencida"][0]["alvo"] == "produto:plano-anual"
    assert por["faq_contraditoria"][0]["alvo"] in ("faq:a", "faq:b")
    assert por["faq_duplicada"][0]["alvo"] in ("faq:a", "faq:c")  # "Sim." em a e c
    assert por["bastidor"][0]["alvo"] == "info:observacoes"


def test_base_exportar_importar_ida_e_volta(dados):
    api = Servidor(dados).subir()
    st, b = api.get("/api/gestor/base.json", bruto=True)
    assert st == 200
    j = json.loads(b.decode("utf-8"))
    assert set(j) >= {"info", "faq", "produtos"}
    st, md = api.get("/api/gestor/base.md", bruto=True)
    md = md.decode("utf-8")
    assert st == 200 and md.startswith("# Base de conhecimento") and "## Produtos" in md and "Plano anual" in md
    # ida e volta sem mudar nada
    st, r = api.post("/api/gestor/base/importar", j)
    assert st == 200 and r["mudancas"] == [] and r["aplicado"] is False
    # prévia não grava
    j2 = json.loads(json.dumps(j))
    j2["info"]["pagamento"] = "Pix e cartão."
    j2["produtos"][0]["preco"] = "R$ 999"
    antes = (dados / "negocio.json").read_text(encoding="utf-8")
    st, r = api.post("/api/gestor/base/importar", j2)
    assert st == 200 and r["aplicado"] is False and {m["onde"] for m in r["mudancas"]} == {"info.pagamento", "produtos.plano-anual"}
    assert (dados / "negocio.json").read_text(encoding="utf-8") == antes
    # inválido → 422 sem gravar
    st, r = api.post("/api/gestor/base/importar", {"faq": [{"id": "x"}]})
    assert st == 422
    # aplicar grava, com backup
    st, r = api.post("/api/gestor/base/importar?aplicar=1", j2)
    assert st == 200 and r["aplicado"] is True and r["backup"].startswith("negocio.json.")
    assert (dados / r["backup"]).exists()
    st, cfg = api.get("/api/gestor/config")
    assert cfg["info"]["pagamento"] == "Pix e cartão." and cfg["produtos"][0]["preco"] == "R$ 999"
    st, b = api.get("/api/gestor/base.json", bruto=True)
    assert json.loads(b.decode("utf-8"))["produtos"][0]["preco"] == "R$ 999"  # volta igual ao importado
