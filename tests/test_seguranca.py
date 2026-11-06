"""Revisão de segurança/robustez da 1.0.1: outbox fora do lock, sessão do chat web, limite de tentativas,
CSV, @lid, negação, segredos de exemplo, restaurar com servidor no ar."""
import json
import os
import shutil
import subprocess
import time

import pytest

from conftest import (CODIGOS, FIXTURE, GRUPO, RAIZ, SEGREDO_WH, TEL, TEL_D, TG_ID, TOKEN, Servidor, Tg,
                      equipe_pronta, esperar, ok)


# ------------------------------------------------------------ item 1: rede fora do lock

def test_saude_responde_rapido_com_telegram_pendurado(api_int, externo, tg):
    externo.pendurar = True
    tg.entrar("ana")                     # já gera envio ao Telegram (que não responde)
    api_int.status("ana", "livre")       # e o painel do grupo
    assert esperar(lambda: externo.pedidos, timeout=3)
    for _ in range(3):
        t0 = time.time()
        st, r = api_int.get("/api/saude", token=None)
        assert st == 200 and r["ok"] is True
        assert time.time() - t0 < 1.0, time.time() - t0
    t0 = time.time()
    st, _ = api_int.post("/api/mensagens", {"telefone": TEL, "texto": "oi", "canal": "whatsapp"})
    assert st == 200
    assert time.time() - t0 < 3.5        # espera no máximo ~2 s pelo despacho, fora do lock
    t0 = time.time()
    assert api_int.get("/api/painel")[0] == 200
    assert time.time() - t0 < 1.0


# ------------------------------------------------------------ item 4: chat web por sessão

def test_web_cria_sessao_propria(api):
    st, r = api.post("/api/mensagens", {"telefone": TEL, "texto": "oi", "nome": "Ana Web", "canal": "web"},
                     token=None)
    assert st == 200, r
    assert isinstance(r.get("sessao"), str) and len(r["sessao"]) >= 24
    lead = r["lead"]
    st, r2 = api.post("/api/mensagens", {"sessao": r["sessao"], "texto": "qual o horario de atendimento"},
                      token=None)
    assert st == 200 and r2["lead"]["id"] == lead["id"]
    assert api.post("/api/mensagens", {"sessao": "x" * 32, "texto": "oi"}, token=None)[0] == 404
    # sem sessão: outro lead, mesmo com o mesmo telefone
    st, r3 = api.post("/api/mensagens", {"telefone": TEL, "texto": "oi", "canal": "web"}, token=None)
    assert st == 200 and r3["lead"]["id"] != lead["id"] and r3["sessao"] != r["sessao"]
    st, m = api.get(f"/api/web/{r['sessao']}", token=None)
    assert st == 200 and any(x["texto"] == "qual o horario de atendimento" for x in m["mensagens"])
    assert api.get("/api/web/" + "y" * 32, token=None)[0] == 404


def test_whatsapp_pela_api_exige_gestor(api):
    corpo = {"telefone": TEL, "texto": "oi", "canal": "whatsapp"}
    assert api.post("/api/mensagens", corpo, token=None)[0] == 401
    assert api.post("/api/mensagens", corpo)[0] == 200


def test_token_do_lead_whatsapp_nao_vaza_pelo_web(api):
    wa = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    st, r = api.post("/api/mensagens", {"telefone": TEL, "texto": "oi", "canal": "web"}, token=None)
    assert st == 200
    assert r["lead"]["id"] != wa["id"] and r["lead"]["token"] != wa["token"]
    assert wa["token"] not in json.dumps(r)


def test_api_meu_nao_devolve_mensagens(api):
    r = api.msg_full(TEL, "minha senha secreta 4321", nome="Maria Souza")
    st, meu = api.get(f"/api/meu/{r['lead']['token']}", token=None)
    assert st == 200
    assert set(meu) <= {"nome", "status", "colaborador", "retornar_em"}
    assert "4321" not in json.dumps(meu)


def test_injecao_web_nao_chega_ao_lead_do_whatsapp(api_int, externo, tg):
    equipe_pronta(api_int, tg, quem=("ana",))
    lead, ch = api_int.atendendo("ana")
    externo.quieto()
    antes = len(externo.privado("ana"))
    st, r = api_int.post("/api/mensagens", {"telefone": TEL, "texto": "INJETADO pelo site", "canal": "web"},
                         token=None)
    assert st == 200 and r["lead"]["id"] != lead["id"]
    externo.quieto()
    assert not externo.com_texto(externo.privado("ana")[antes:], "INJETADO")
    assert "INJETADO" not in json.dumps(api_int.ficha(lead["id"]))
    assert api_int.chamado_aberto(lead["id"])["id"] == ch


# ------------------------------------------------------------ item 5: limite de tentativas

def test_codigo_errado_5_vezes_429(api):
    for _ in range(5):
        assert api.get("/api/equipe/eu", token=None, codigo="chute-errado")[0] == 401
    st, r = api.get("/api/equipe/eu", token=None, codigo=CODIGOS["ana"])
    assert st == 429 and "Muitas tentativas" in r["erro"]


def test_token_gestor_errado_5_vezes_429(api):
    for _ in range(5):
        assert api.get("/api/gestor/hoje", token="chute")[0] == 401
    assert api.get("/api/gestor/hoje")[0] == 429


def test_entrar_limite_por_from_id(api_int, externo, tg):
    for _ in range(5):
        tg.msg(9999, "/entrar chute")
    assert esperar(lambda: len(externo.com_texto(externo.enviadas(9999), "Código inválido.")) == 5)
    tg.msg(9999, f"/entrar {CODIGOS['ana']}")
    assert esperar(lambda: externo.com_texto(externo.enviadas(9999), "Muitas tentativas, aguarde."))
    assert not externo.com_texto(externo.enviadas(9999), "Olá, Ana!")


def test_entrar_de_outra_conta_avisa_a_anterior(api_int, externo, tg):
    tg.entrar("ana")
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "Olá, Ana!"))
    tg.msg(8888, f"/entrar {CODIGOS['ana']}")
    assert esperar(lambda: externo.com_texto(externo.enviadas(8888), "Olá, Ana!"))
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "outra conta"))


# ------------------------------------------------------------ item 9: /status só no grupo da equipe

def test_status_em_outro_grupo_ignorado(api_int, externo, tg):
    tg.entrar("ana")
    tg.msg(TG_ID["ana"], "/status", chat_id=-100999)
    tg.msg(TG_ID["ana"], "/status", chat_id=GRUPO)
    assert esperar(lambda: externo.com_texto(externo.enviadas(GRUPO), "EQUIPE AGORA"))
    externo.quieto()
    assert externo.enviadas(-100999) == []


# ------------------------------------------------------------ item 7: CSV

def test_csv_sem_injecao_de_formula(api):
    api.msg_full(TEL, "oi", nome='=HYPERLINK("http://x","clique")')
    _, linhas = api.csv()
    nome = next(l["nome"] for l in linhas if l["telefone"] == TEL_D)
    assert nome.startswith("'=")


# ------------------------------------------------------------ item 8: @lid

def _evo(api, key, data_extra=None, texto="oi"):
    data = {"key": key, "pushName": "Maria", "message": {"conversation": texto}, "messageType": "conversation"}
    data.update(data_extra or {})
    return api.post(f"/webhook/evolution/{SEGREDO_WH}", {"event": "messages.upsert", "instance": "loja", "data": data},
                    token=None)


@pytest.mark.parametrize("onde", ["remoteJidAlt", "senderPn", "data.senderPn"])
def test_lid_usa_telefone_alternativo(api_int, externo, onde):
    key = {"remoteJid": "123456789012345@lid", "fromMe": False, "id": f"LID-{onde}"}
    extra = None
    if onde == "data.senderPn":
        extra = {"senderPn": f"{TEL_D}@s.whatsapp.net"}
    else:
        key[onde] = f"{TEL_D}@s.whatsapp.net"
    assert _evo(api_int, key, extra)[0] == 200
    assert esperar(lambda: [p for p in externo.whats() if p["json"].get("number") == TEL_D])
    assert any(l["telefone"] == TEL_D for l in api_int.csv()[1])


def test_lid_sem_telefone_vai_para_descartes(api_int, externo):
    assert _evo(api_int, {"remoteJid": "123456789012345@lid", "fromMe": False, "id": "LID-X"})[0] == 200
    st, r = api_int.get("/api/gestor/ao-vivo")
    assert st == 200
    assert any("@lid" in str(d) for d in r["descartes"])
    externo.quieto()
    assert externo.whats() == []
    assert api_int.csv()[1] == []


# ------------------------------------------------------------ item 10: 'problema' com negação

@pytest.mark.parametrize("texto", ["sem problema", "Nenhum problema, obrigado", "não tem problema"])
def test_problema_negado_nao_abre_chamado(api, texto):
    lead = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    api.msg(TEL, texto)
    assert api.chamados_do_lead(lead["id"]) == []


def test_problema_de_verdade_abre_chamado(api):
    lead = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]
    api.msg(TEL, "tive problemas com o pedido")
    assert [c["motivo"] for c in api.chamados_do_lead(lead["id"])] == ["precisa"]


# ------------------------------------------------------------ item 2: reenvio respeita PARAR

def test_reenvio_nao_vai_para_quem_pediu_parar(dados, externo):
    from conftest import env_integracoes
    env = {k: v for k, v in env_integracoes(externo).items() if not k.startswith("TELEGRAM_")}
    api = Servidor(dados, env=env).subir()
    externo.falhas = 1000
    api.msg_full(TEL, "oi")
    api.msg_full(TEL, "parar")
    assert esperar(lambda: [m for m in api.saida() if m["status"] == "pendente"])
    externo.falhas = 0
    api.rodar()
    # a resposta ao "oi" falhou e seria REENVIADA: cancelada. A confirmação do PARAR (1ª tentativa,
    # presa atrás da outra na fila do mesmo telefone) ainda sai.
    primeira = lambda: api.saida()[0]
    assert esperar(lambda: primeira()["status"] == "cancelado", timeout=5), api.saida()
    externo.quieto()
    assert all("não vai mais receber" in p["json"]["text"] for p in externo.whats())


# ------------------------------------------------------------ item 6: segredos de exemplo

def _serve(dados, host, env_extra=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ATENDE_", "TELEGRAM_", "EVOLUTION_"))}
    env.update(env_extra or {})
    return subprocess.Popen([str(RAIZ / "atende"), "serve", "--host", host, "--porta", "0", "--dados", str(dados)],
                            cwd=RAIZ, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _primeira_linha(p):
    try:
        out = p.stdout.readline()
    finally:
        p.terminate()
        try:
            p.wait(5)
        except subprocess.TimeoutExpired:
            p.kill()
    return out


def test_recusa_segredos_de_exemplo_em_0000(tmp_path):
    d = tmp_path / "ex"
    d.mkdir()
    p = _serve(d, "0.0.0.0")             # sem negocio.json → copia o exemplo
    assert p.wait(15) != 0
    err = p.stderr.read()
    assert "instalar-vps.sh" in err and "troque os segredos" in err
    # o mesmo exemplo em 127.0.0.1 sobe
    assert _primeira_linha(_serve(d, "127.0.0.1")).startswith("PORTA=")
    # ATENDE_PERMITIR_EXEMPLO=1 libera (teste/demonstração)
    assert _primeira_linha(_serve(d, "0.0.0.0", {"ATENDE_PERMITIR_EXEMPLO": "1"})).startswith("PORTA=")


def test_recusa_codigo_de_exemplo_e_aceita_segredos_proprios(tmp_path):
    d = tmp_path / "proprio"
    d.mkdir()
    cfg = json.loads(FIXTURE.read_text())  # token próprio, mas a Ana usa o código do exemplo
    (d / "negocio.json").write_text(json.dumps(cfg))
    p = _serve(d, "0.0.0.0")
    assert p.wait(15) != 0 and "código" in p.stderr.read()
    for m in cfg["equipe"]:
        m["codigo"] = m["id"] + "-Xk3vQ9pL2mZt"
    (d / "negocio.json").write_text(json.dumps(cfg))
    assert _primeira_linha(_serve(d, "0.0.0.0")).startswith("PORTA=")


# ------------------------------------------------------------ item 11: restaurar com servidor no ar

def test_restaurar_recusa_com_servidor_rodando(api, dados, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("ATENDE_")}
    arq = tmp_path / "b.tar.gz"
    p = subprocess.run([str(RAIZ / "atende"), "backup", "--dados", str(dados), "--saida", str(arq)],
                       cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    p = subprocess.run([str(RAIZ / "atende"), "restaurar", "--dados", str(dados), "--arquivo", str(arq)],
                       cwd=RAIZ, env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode != 0
    assert "docker compose stop atende" in p.stderr
