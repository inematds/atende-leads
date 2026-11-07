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
