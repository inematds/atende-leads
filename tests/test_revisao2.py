"""Segunda revisão independente (1.0.2): nome do lead, apagar com chamado aberto, "fechar" restrito,
assumir só o ofertado/alerta, minutos_ate_assumir do início do prazo."""
import re
import time

from conftest import (CODIGOS, GRUPO, TEL, TEL_D, TEL_FMT, Servidor, equipe_pronta, esperar, mais, ok)


def _motivos(api, lead_id):
    return [c["motivo"] for c in api.chamados_do_lead(lead_id)]


# ------------------------------------------------------------ item 5: nome livre

def test_nome_que_nao_parece_nome_pergunta_de_novo(api):
    lead = api.msg_full(TEL, "oi")["lead"]
    for texto in ("não sei", "Maria123", "quero ver depois", "tenho uma dúvida sobre o site", "1 2 3",
                  "boa tarde pessoal", "Ana Maria de Souza Lima Costa"):
        r = api.msg(TEL, texto)
        assert "Pode me dizer só o seu nome?" in r, (texto, r)
    st, meu = api.get(f"/api/meu/{lead['token']}", token=None)
    assert not meu["nome"]
    r = api.msg(TEL, "meu nome é joana d'arc")
    assert "Prazer, Joana" in r
    assert api.get(f"/api/meu/{lead['token']}", token=None)[1]["nome"] == "Joana D'arc"


def test_nome_com_digitos_nunca_vai_ao_grupo(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana",))
    r = api_int.msg_full(TEL, "quero falar com um atendente", nome="41999990001 Silva")
    ch = api_int.chamado_aberto(r["lead"]["id"])["id"]
    assert esperar(lambda: externo.com_texto(externo.grupo(), f"#{ch}"))
    externo.quieto()
    linha = externo.textos(externo.com_texto(externo.grupo(), f"#{ch}"))
    assert " lead " in linha and not re.search(r"\d{4,}", linha.replace(f"#{ch}", ""))


# ------------------------------------------------------------ item 6: apagar com chamado aberto

def test_apagar_com_chamado_em_atendimento(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana",))
    lead, ch = api_int.atendendo("ana")
    assert api_int.eu("ana")["status"] == "atendendo"
    externo.quieto()
    r = api_int.msg_full(TEL, "apagar meus dados")
    assert "apagados" in "\n".join(r["respostas"])
    c = next(x for x in api_int.chamados_do_lead(lead["id"]) if str(x["id"]) == str(ch))
    assert c["status"] == "fechado" and c["resultado"] == "apagado"
    assert api_int.eu("ana")["status"] == "livre"
    assert all(str(f["id"]) != str(ch) for f in api_int.fila())
    texto = f"🗑️ #{ch} lead pediu para apagar os dados"
    assert esperar(lambda: externo.com_texto(externo.grupo(), texto))
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), texto))  # aviso ao dono
    edits = [p for p in externo.tg("editMessageText") if p["json"].get("text") == texto]
    assert edits and all(not (p["json"].get("reply_markup") or {}).get("inline_keyboard") for p in edits)
    # o cartão do atendimento (com nome e telefone) foi editado para o aviso
    assert [p for p in edits if str(p["json"].get("chat_id")) != str(GRUPO)]


def test_apagar_com_oferta_pendente(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana",))
    lead, ch = api_int.abrir()
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), f"#{ch}"))
    externo.quieto()
    api_int.msg(TEL, "apagar meus dados")
    texto = f"🗑️ #{ch} lead pediu para apagar os dados"
    assert esperar(lambda: [p for p in externo.tg("editMessageText", 7001) if p["json"].get("text") == texto])
    assert esperar(lambda: externo.com_texto(externo.grupo(), texto))
    assert api_int.fila() == []
    assert api_int.eu("ana")["status"] == "livre"


def test_apagar_cancela_envios_pendentes_com_dados_do_lead(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana",))
    externo.quieto()
    externo.falhas = 10_000          # Telegram e Evolution fora: a oferta (com telefone) fica na fila
    lead, ch = api_int.abrir()
    api_int.msg(TEL, "apagar meus dados")
    externo.falhas = 0
    time.sleep(7)                    # passa o 1º backoff (5 s): o que ficou pendente teria saído agora
    externo.quieto()
    privados = externo.textos(externo.privado("ana"))
    assert TEL_FMT not in privados and "Maria" not in privados
    assert TEL_FMT not in externo.textos(externo.tg())


# ------------------------------------------------------------ item 8: "fechar" só em expressões de compra

def test_fechar_solto_nao_e_chance_de_venda(api):
    lead = api.msg_full(TEL, "hoje vou fechar a loja mais cedo", nome="Maria Souza")["lead"]
    assert api.chamados_do_lead(lead["id"]) == []
    assert lead["nota"] != "quente"


def test_quero_fechar_abre_venda(api):
    api.status("ana", "livre")
    r = api.msg_full(TEL, "quero fechar o plano anual", nome="Maria Souza")
    assert r["lead"]["nota"] == "quente" and "Plano anual: R$ 1.200" in "\n".join(r["respostas"])
    assert _motivos(api, r["lead"]["id"]) == ["venda"]
    r2 = api.msg_full("(41) 98888-1111", "podemos fechar negócio hoje?", nome="Paulo")
    assert _motivos(api, r2["lead"]["id"]) == ["venda"]


# ------------------------------------------------------------ item 8: assumir só o ofertado ou em alerta

def test_assumir_so_quem_recebeu_a_oferta(api):
    equipe_pronta(api, None, ("ana", "bruno"))
    _, ch = api.abrir()                               # ofertado à ana (1ª da vez)
    st, r = api.assumir("bruno", ch)
    assert st == 403, (st, r)
    assert ok(api.assumir("ana", ch)[0])


def test_assumir_em_alerta_qualquer_um(api):
    api.status("bruno", "ocupado")                   # ninguém livre → alerta
    _, ch = api.abrir()
    assert next(f for f in api.fila() if str(f["id"]) == str(ch))["status"] == "alerta"
    assert ok(api.assumir("bruno", ch)[0])


def test_gestor_transfere_chamado_ofertado_a_outro(api):
    equipe_pronta(api, None, ("ana", "bruno"))
    _, ch = api.abrir()
    assert api.assumir("bruno", ch)[0] == 403
    assert ok(api.post(f"/api/gestor/chamados/{ch}/transferir", {"colaborador": "bruno"})[0])
    assert api.eu("bruno")["status"] == "atendendo"


def test_assumir_pelo_telegram_sem_oferta_recusa(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana", "bruno"))
    _, ch = api_int.abrir()
    tg.cb(7002, f"as:{ch}")                           # bruno toca num botão de um chamado da ana
    assert esperar(lambda: externo.com_texto(externo.privado("bruno"), "não foi oferecido a você"))
    assert api_int.eu("ana")["status"] == "livre" and api_int.eu("bruno")["status"] == "livre"


# ------------------------------------------------------------ item 8: minutos_ate_assumir

def test_minutos_ate_assumir_conta_da_abertura_do_expediente(dados):
    api = Servidor(dados, agora="2026-11-09T07:00").subir()   # segunda, antes das 08:00
    api.status("ana", "livre")
    lead, ch = api.abrir()
    api.avancar(para="2026-11-09T08:00")              # abre o expediente: oferta à ana, prazo conta daqui
    api.relogio("2026-11-09T08:03")
    assert ok(api.assumir("ana", ch)[0])
    api.relogio("2026-11-09T08:10")
    st, r = api.fechar("ana", ch, {"resultado": "negociando"})
    assert ok(st)
    assert r["evento"]["minutos_ate_assumir"] == 3
    assert float(api.get("/api/gestor/hoje")[1]["tempo_medio_assumir_min"]) == 3
