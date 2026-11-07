"""1.11.8: conversa pelo WhatsApp do atendente (ou ligação) → resumo obrigatório ao encerrar, que entra na conversa."""
from conftest import CODIGOS, TEL, ok


def test_por_fora_exige_resumo_e_registra_na_conversa(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert api.fechar("ana", ch, {"resultado": "negociando", "por_fora": True})[0] == 422
    assert api.fechar("ana", ch, {"resultado": "negociando", "por_fora": True, "nota": "curto"})[0] == 422
    assert api.fechar("ana", ch, {"resultado": "negociando", "por_fora": "sim", "nota": "x" * 20})[0] == 422
    st, r = api.fechar("ana", ch, {"resultado": "vendeu", "valor": 1200, "por_fora": True,
                                   "nota": "Fechou o plano anual no Pix, começa segunda às 7h"})
    assert ok(st), r
    f = api.ficha(lead["id"])
    assert "[Combinado fora do sistema] Fechou o plano anual no Pix" in str(f)
    assert "Fechou o plano anual" not in api.textos_para("5541999990001")   # não vai para o cliente
    c = api.chamados_do_lead(lead["id"])[0]
    assert c["tempos"]["primeira_resposta_min"] is None                  # o resumo não conta como resposta


def test_sem_por_fora_continua_como_antes(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert ok(api.fechar("ana", ch, {"resultado": "negociando"})[0])
    assert "Combinado fora do sistema" not in str(api.ficha(lead["id"]))


def test_resumo_nao_aparece_no_chat_web(api):
    api.status("ana", "livre")
    st, w = api.post("/api/mensagens", {"telefone": "41980001220", "texto": "quero falar com um atendente",
                                        "nome": "Carol Antunes", "canal": "web"}, token=None)
    assert ok(st), w
    ch = api.chamado_aberto(w["lead"]["id"])["id"]
    assert ok(api.assumir("ana", ch)[0])
    assert ok(api.fechar("ana", ch, {"resultado": "negociando", "por_fora": True,
                                     "nota": "Combinamos visita na quinta às 10h"})[0])
    st, r = api.get(f"/api/web/{w['sessao']}", token=None)
    assert st == 200 and "Combinamos visita" not in str(r)
    assert "Combinamos visita" in str(api.ficha(w["lead"]["id"]))


def test_nota_so_espacos_nao_vale_como_resumo(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    assert api.fechar("ana", ch, {"resultado": "negociando", "por_fora": True, "nota": " " * 30})[0] == 422


def test_gestor_fecha_por_fora(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    st, r = api.post(f"/api/equipe/chamados/{ch}/fechar", {"resultado": "negociando", "por_fora": True,
                                                           "nota": "Liguei e ficou para a semana que vem"})
    assert ok(st), r
    assert "[Combinado fora do sistema] Liguei" in str(api.ficha(lead["id"]))
