"""Seções 4 e 5: normalização, ordem das 12 regras, qualificação e produtos."""
import pytest

from conftest import TEL, TEL_D, buscar, ok

FAQ_HORARIO = "Atendemos de segunda a sexta, das 8h às 18h."
FAQ_ENDERECO = "Ficamos na Rua Exemplo, 100, Centro."
PERGUNTA_CHAMAR = "Quer que eu chame alguém para te atender?"  # 1.10.8: o robô não oferece mais
CHAMEI = "já chamei alguém da equipe"


def revela(txt):
    """1.10.8: o robô só conta que chamou a equipe quando o cliente pede."""
    t = txt.lower()
    return any(x in t for x in ("chamar", "chamei", "avisei a equipe", "equipe", "alguém da"))


def motivos(api, lead_id):
    return [c["motivo"] for c in api.chamados_do_lead(lead_id)]


def nao_contatar(api, lead_id):
    achados = buscar(api.ficha(lead_id), lambda d: "nao_contatar" in d)
    assert achados, "ficha do lead deveria expor nao_contatar"
    return achados[0]["nao_contatar"]


def qualificar_ate_urgencia(api, tel=TEL):
    api.msg(tel, "oi")
    api.msg(tel, "Maria Souza")
    return api.msg(tel, "1")


# ------------------------------------------------------------ telefone

def test_telefone_formatos_diferentes_mesmo_lead(api):
    a = api.msg_full("(41) 99999-0001", "oi")["lead"]["id"]
    b = api.msg_full("5541999990001", "oi")["lead"]["id"]
    c = api.msg_full("+55 41 99999-0001", "oi")["lead"]["id"]
    assert a == b == c


def test_telefone_10_digitos_ganha_55(api):
    lead = api.msg_full("41 3333-4444", "oi")["lead"]
    assert api.lead_csv(lead["id"])["telefone"] == "554133334444"


@pytest.mark.parametrize("tel", ["12345", "419999", "55419999900011", "123456789012345", ""])
def test_telefone_invalido_422(api, tel):
    st, _ = api.post("/api/mensagens", {"telefone": tel, "texto": "oi"}, token=None)
    assert st == 422


def test_lead_novo_comeca_novo_e_frio(api):
    r = api.msg_full(TEL, "oi")
    assert r["lead"]["status"] == "novo"
    assert r["lead"]["nota"] == "frio"
    assert set(r["lead"]) >= {"id", "token", "status", "nota"}


# ------------------------------------------------------------ regra 1: parar

@pytest.mark.parametrize("texto", ["parar", "Parar!", "SAIR", "pare"])
def test_parar(api, texto):
    r = api.msg_full(TEL, texto)
    assert "não vai mais receber" in "\n".join(r["respostas"])
    assert nao_contatar(api, r["lead"]["id"]) is True


def test_mensagem_nova_depois_de_parar_volta_ao_normal(api):
    lead = api.msg_full(TEL, "parar")["lead"]
    r = api.msg_full(TEL, "oi")
    assert r["respostas"], "mensagem nova depois de parar recebe resposta normal"
    assert nao_contatar(api, lead["id"]) is False


def test_parar_tem_precedencia_sobre_atendimento_e_bloqueia_retorno(api):
    api.status("ana", "livre")
    lead, ch = api.atendendo("ana")
    r = api.msg_full(TEL, "parar")
    assert "não vai mais receber" in "\n".join(r["respostas"])
    st, _ = api.fechar("ana", ch, {"resultado": "retornar", "retornar_em": "2026-11-10T09:00"})
    assert ok(st)
    assert "Combinado!" not in api.textos_para(TEL_D)


# ------------------------------------------------------------ regra 2: apagar

def test_apagar_meus_dados(api):
    r = api.msg_full(TEL, "oi", nome="Maria Souza")
    lead = r["lead"]
    r2 = api.msg_full(TEL, "Apagar meus dados")
    assert "apagados" in "\n".join(r2["respostas"])
    st, meu = api.get(f"/api/meu/{lead['token']}", token=None)
    assert st == 404 or meu["nome"] == "apagado"
    linha = api.lead_csv(lead["id"])
    assert linha["nome"] == "apagado"
    assert linha["telefone"] == f"apagado-{lead['id']}"
    assert "Maria" not in str(api.ficha(lead["id"]))


# ------------------------------------------------------------ regra 3 e 4

def test_em_atendimento_agente_nao_responde(api):
    api.status("ana", "livre")
    api.atendendo("ana")
    r = api.msg_full(TEL, "oi, tudo bem? quanto custa o plano anual?")
    assert r["respostas"] == []


def test_chamado_aguardando_responde_ja_avisei_e_nao_abre_outro(api):
    lead, _ = api.abrir()
    r = api.msg_full(TEL, "oi? alguém aí?")
    assert "já avisei" in "\n".join(r["respostas"])
    r = api.msg_full(TEL, "quanto custa o plano anual")  # regra 4 vem antes da 6, mas agora tira a dúvida
    txt = "\n".join(r["respostas"])
    assert "já avisei" not in txt and "R$" in txt  # 06/11/2026 (Nei): responde dúvidas enquanto espera
    assert len(api.chamados_do_lead(lead["id"])) == 1


def test_chamado_aguardando_mensagem_entra_no_historico(api):
    lead, _ = api.abrir()
    api.msg_full(TEL, "mensagem-marcador-xyz")
    assert "mensagem-marcador-xyz" in str(api.ficha(lead["id"]))


# ------------------------------------------------------------ regra 5: pediu humano

@pytest.mark.parametrize("texto", ["Quero falar com um ATENDENTE", "posso falar com alguém?",
                                   "tem algum vendedor aí", "me liga por favor", "prefiro ligação"])
def test_pediu_humano(api, texto):
    r = api.msg_full(TEL, texto)
    txt = "\n".join(r["respostas"])
    assert CHAMEI in txt and "sigo com você" in txt  # pediu: avisa e continua a conversa
    assert motivos(api, r["lead"]["id"]) == ["pediu_humano"]
    assert r["lead"]["status"] == "novo"  # chamado não assumido não muda o status


def test_pediu_humano_vem_antes_de_venda(api):
    r = api.msg_full(TEL, "quero comprar, me liga")
    c = api.chamados_do_lead(r["lead"]["id"])
    assert [x["motivo"] for x in c] == ["pediu_humano"]
    assert c[0]["prioridade"] == "normal"


# ------------------------------------------------------------ regra 6: venda

def test_venda_com_preco_do_produto(api):
    r = api.msg_full(TEL, "Quanto custa o plano anual?")
    txt = "\n".join(r["respostas"])
    assert "Plano anual: R$ 1.200" in txt
    assert not revela(txt)  # 1.10.8: chance de venda chama a equipe sem dizer ao cliente
    assert r["lead"]["nota"] == "quente"
    c = api.chamados_do_lead(r["lead"]["id"])
    assert [x["motivo"] for x in c] == ["venda"] and c[0]["prioridade"] == "quente"


def test_venda_sem_produto_nao_inventa_preco(api):
    r = api.msg_full(TEL, "qual o valor?")
    txt = "\n".join(r["respostas"])
    assert not revela(txt)
    assert "R$" not in txt or "Plano anual: R$ 1.200" in txt  # 1.10.8: só preço cadastrado (tabela), nunca inventado
    assert txt.strip()  # o robô segue a conversa (pergunta o nome)
    assert r["lead"]["nota"] == "quente"
    assert motivos(api, r["lead"]["id"]) == ["venda"]
    assert api.chamados_do_lead(r["lead"]["id"])[0]["silencioso"] is True


def test_venda_vem_antes_de_necessidade(api):
    r = api.msg_full(TEL, "quero comprar mas tive um problema")
    assert motivos(api, r["lead"]["id"]) == ["venda"]


# ------------------------------------------------------------ regra 7: necessidade

@pytest.mark.parametrize("texto", ["meu produto veio com defeito", "quero cancelar", "isso é um absurdo!",
                                   "não funciona"])
def test_necessidade(api, texto):
    r = api.msg_full(TEL, texto)
    txt = "\n".join(r["respostas"])
    assert "avisei a equipe" in txt.lower() and "sigo com você" in txt  # avisa que notificou e segue
    c = api.chamados_do_lead(r["lead"]["id"])
    assert [x["motivo"] for x in c] == ["precisa"] and c[0]["silencioso"] is False and c[0]["prioridade"] == "normal"


# ------------------------------------------------------------ regra 9: FAQ

def test_faq_exato_resposta_unica(api):
    r = api.msg_full(TEL, "Qual o horário de atendimento?")
    assert r["respostas"] == [FAQ_HORARIO]


def test_faq_segunda_pergunta(api):
    r = api.msg_full(TEL, "onde fica a loja de vocês?")
    assert r["respostas"] == [FAQ_ENDERECO]


def test_faq_parcial_acima_de_60(api):
    r = api.msg_full(TEL, "horário de atendimento")
    assert r["respostas"] == [FAQ_HORARIO]


def test_faq_abaixo_de_60_nao_responde(api):
    r = api.msg_full(TEL, "atendimento")
    assert FAQ_HORARIO not in r["respostas"]


# ------------------------------------------------------------ regra 10: produto

def test_produto_sem_nome_vira_morno_e_qualifica(api):
    r = api.msg_full(TEL, "tenho interesse no curso de inglês")
    assert r["lead"]["nota"] == "morno"
    assert "nome" in "\n".join(r["respostas"]).lower()
    assert api.lead_csv(r["lead"]["id"])["interesse"] in ("curso-ingles", "Curso de inglês")


def test_produto_com_nome_pergunta_quando_e_abre_venda_calado(api):
    r = api.msg_full(TEL, "me fala do plano anual", nome="Maria Souza")
    txt = "\n".join(r["respostas"])
    assert "Plano anual" in txt and PERGUNTA_CHAMAR not in txt and "Para quando" in txt
    assert r["lead"]["nota"] == "morno"
    assert api.chamados_do_lead(r["lead"]["id"]) == []
    txt = api.msg(TEL, "1")
    assert not revela(txt)
    assert motivos(api, r["lead"]["id"]) == ["venda"]


def test_produto_palavra_ou_nome(api):
    r = api.msg_full(TEL, "vi o anual no site", nome="Maria Souza")
    assert "Plano anual" in "\n".join(r["respostas"])


# ------------------------------------------------------------ regra 11 e qualificação

def test_primeiro_contato_saudacao_com_nome_do_negocio(api):
    txt = api.msg(TEL, "oi")
    assert "Loja Teste" in txt
    assert "nome" in txt.lower()


def test_qualificacao_lista_produtos_numerados(api):
    api.msg(TEL, "oi")
    txt = api.msg(TEL, "Maria Souza")
    for trecho in ("1 - Plano anual", "2 - Curso de inglês", "0 - Outro assunto"):
        assert trecho in txt


def test_qualificacao_grava_nome(api):
    lead = api.msg_full(TEL, "oi")["lead"]
    api.msg(TEL, "Maria Souza")
    st, meu = api.get(f"/api/meu/{lead['token']}", token=None)
    assert meu["nome"] == "Maria Souza"


def test_nome_no_corpo_pula_pergunta_do_nome(api):
    txt = api.msg(TEL, "oi", nome="Maria")
    assert "1 - Plano anual" in txt


def test_qualificacao_pergunta_urgencia(api):
    txt = qualificar_ate_urgencia(api)
    for trecho in ("1 - Hoje / esta semana", "2 - Este mês", "3 - Só pesquisando"):
        assert trecho in txt


def test_qualificacao_numero_invalido_repete(api):
    api.msg(TEL, "oi")
    api.msg(TEL, "Maria Souza")
    assert "1 - Plano anual" in api.msg(TEL, "7")
    api.msg(TEL, "1")
    assert "3 - Só pesquisando" in api.msg(TEL, "9")


def test_urgencia_1_quente_abre_venda(api):
    qualificar_ate_urgencia(api)
    r = api.msg_full(TEL, "1")
    assert r["lead"]["nota"] == "quente"
    assert motivos(api, r["lead"]["id"]) == ["venda"]


def test_urgencia_2_morno_abre_venda_calado(api):
    qualificar_ate_urgencia(api)
    r = api.msg_full(TEL, "2")
    assert r["lead"]["nota"] == "morno"
    assert not revela("\n".join(r["respostas"]))
    assert motivos(api, r["lead"]["id"]) == ["venda"]


def test_urgencia_3_frio_sem_chamado(api):
    qualificar_ate_urgencia(api)
    r = api.msg_full(TEL, "3")
    assert r["lead"]["nota"] == "frio"
    assert "qualquer dúvida" in "\n".join(r["respostas"]).lower()
    assert api.chamados_do_lead(r["lead"]["id"]) == []


def test_regras_1_a_7_valem_no_meio_da_qualificacao(api):
    api.msg(TEL, "oi")
    r = api.msg_full(TEL, "quero falar com um atendente")
    assert CHAMEI in "\n".join(r["respostas"])
    assert motivos(api, r["lead"]["id"]) == ["pediu_humano"]


# ------------------------------------------------------------ regra 12: não entendi

def _lead_sem_qualificacao(api):
    qualificar_ate_urgencia(api)
    return api.msg_full(TEL, "3")["lead"]


def test_nao_entendi_nao_oferece_atendente(api):
    _lead_sem_qualificacao(api)
    txt = api.msg(TEL, "xpto blablabla")
    assert "não sei responder com certeza" in txt.lower() and not revela(txt)
    assert "desculpe, não entendi" not in txt.lower()


def test_nao_sei_duas_vezes_avisa_que_notificou(api):
    lead = _lead_sem_qualificacao(api)
    api.msg(TEL, "xpto blablabla")
    assert api.chamados_do_lead(lead["id"]) == []
    txt = api.msg(TEL, "qwerty zzz")
    assert "avisei a equipe" in txt.lower() and "sigo com você" in txt
    assert motivos(api, lead["id"]) == ["precisa"]


def test_nao_sei_e_nao_nao_abre(api):
    lead = _lead_sem_qualificacao(api)
    api.msg(TEL, "xpto blablabla")
    assert "qualquer dúvida" in api.msg(TEL, "não")
    assert api.chamados_do_lead(lead["id"]) == []


def test_nao_entendi_duas_seguidas_abre_chamado(api):
    lead = _lead_sem_qualificacao(api)
    api.msg(TEL, "xpto blablabla")
    assert api.chamados_do_lead(lead["id"]) == []
    api.msg(TEL, "zzz qwerty")
    assert motivos(api, lead["id"]) == ["precisa"]


def test_nao_entendi_intercalado_nao_abre(api):
    lead = _lead_sem_qualificacao(api)
    api.msg(TEL, "xpto blablabla")
    assert api.msg_full(TEL, "qual o horario de atendimento")["respostas"] == [FAQ_HORARIO]
    api.msg(TEL, "zzz qwerty")
    assert api.chamados_do_lead(lead["id"]) == []
