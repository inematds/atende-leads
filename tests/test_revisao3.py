"""Terceira revisão independente (1.0.3): instalador reaproveita segredos, Evolution sem cópia das mensagens,
/api/saude fora do limite de conexões, nome do chat web validado, avisos no chat web, telefone do remoteJid
sem 55, apagar edita as mensagens do privado, token do gestor forte, webhook que desiste vai a descartes."""
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import time
import urllib.error
import urllib.request

from conftest import (CODIGOS, INSTANCIA, RAIZ, SEGREDO_WH, TEL, TG_ID, TOKEN, Servidor, equipe_pronta,
                      esperar, ok)


# ------------------------------------------------------------ item 1: instalador reaproveita os segredos

SEGREDOS = ("WEBHOOK_SEGREDO", "TELEGRAM_SEGREDO", "EVOLUTION_API_KEY", "EVOLUTION_DB_SENHA")


def _env_arquivo(p):
    return dict(l.split("=", 1) for l in p.read_text().splitlines() if "=" in l and not l.startswith("#"))


def test_instalador_reaproveita_segredos_do_env(tmp_path):
    shutil.copy(RAIZ / "instalar-vps.sh", tmp_path / "instalar-vps.sh")
    shutil.copytree(RAIZ / "exemplos", tmp_path / "exemplos")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("EVOLUTION_", "TELEGRAM_", "WEBHOOK_"))}
    env.update(INSTALAR_SO_GERAR="1", NEGOCIO_NOME="Loja X", DOMINIO="leads.exemplo.test", COM_EVOLUTION="1")

    def rodar():
        r = subprocess.run(["bash", str(tmp_path / "instalar-vps.sh"), "--sem-perguntas"], cwd=tmp_path,
                           env=env, capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return r

    rodar()
    antes = _env_arquivo(tmp_path / ".env")
    assert all(len(antes[k]) >= 16 and "troque" not in antes[k] for k in SEGREDOS), antes
    r = rodar()
    depois = _env_arquivo(tmp_path / ".env")
    assert {k: depois[k] for k in SEGREDOS} == {k: antes[k] for k in SEGREDOS}
    assert "reaproveit" in r.stderr.lower(), r.stderr
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    # o que falta (ou está com "troque") é gerado
    texto = (tmp_path / ".env").read_text().replace(f"EVOLUTION_DB_SENHA={antes['EVOLUTION_DB_SENHA']}",
                                                    "EVOLUTION_DB_SENHA=troque-esta-senha")
    (tmp_path / ".env").write_text(texto)
    rodar()
    final = _env_arquivo(tmp_path / ".env")
    assert final["EVOLUTION_DB_SENHA"] not in ("troque-esta-senha", antes["EVOLUTION_DB_SENHA"])
    assert final["WEBHOOK_SEGREDO"] == antes["WEBHOOK_SEGREDO"]


def test_instalador_aborta_se_dados_nao_for_do_uid_1000():
    s = (RAIZ / "instalar-vps.sh").read_text()
    assert "sudo -n chown -R 1000:1000 dados" in s
    assert re.search(r'DONO_DADOS" != "1000".*?exit 1', s, re.S)
    assert s.index("exit 1", s.index("DONO_DADOS")) < s.index("docker compose --profile evolution up")


def test_backup_pasta_700_arquivo_600():
    for nome in ("instalar-vps.sh", "README.md"):
        s = (RAIZ / nome).read_text()
        assert "install -d -m 700" in s and "chmod 600" in s, nome


# ------------------------------------------------------------ item 3: Evolution não guarda as mensagens

def test_compose_evolution_nao_guarda_mensagens_nem_contatos():
    c = (RAIZ / "docker-compose.yml").read_text()
    flags = dict(re.findall(r"^\s*(DATABASE_SAVE_\w+):\s*\"?(\w+)\"?", c, re.M))
    assert flags.get("DATABASE_SAVE_DATA_NEW_MESSAGE") == "false"
    for k in ("DATABASE_SAVE_MESSAGE_UPDATE", "DATABASE_SAVE_DATA_CONTACTS", "DATABASE_SAVE_DATA_CHATS",
              "DATABASE_SAVE_DATA_HISTORIC"):
        assert flags.get(k) == "false", k
    assert [k for k, v in flags.items() if v == "true"] == ["DATABASE_SAVE_DATA_INSTANCE"]
    assert "LGPD" in c


# ------------------------------------------------------------ item 4: /api/saude fora do limite

def test_saude_responde_com_servidor_lotado(dados):
    api = Servidor(dados, env={"ATENDE_MAX_CONEXOES": "2"}).subir()
    porta = int(api.base.rsplit(":", 1)[1])
    presos = []
    try:
        for _ in range(2):  # conectam e não mandam nada: seguram as 2 vagas
            presos.append(socket.create_connection(("127.0.0.1", porta), timeout=5))
        time.sleep(0.5)
        with urllib.request.urlopen(f"{api.base}/api/saude", timeout=5) as r:
            assert r.status == 200 and json.load(r)["ok"] is True
        try:
            urllib.request.urlopen(f"{api.base}/api/painel", timeout=5)
            assert False, "devia dar 503 com o servidor lotado"
        except urllib.error.HTTPError as e:
            assert e.code == 503
    finally:
        for s in presos:
            s.close()


# ------------------------------------------------------------ item 6: nome do chat web validado

def test_nome_invalido_do_chat_web_e_ignorado(api):
    r = api.msg_full(TEL, "oi", nome="123 abc", canal="web")
    assert "qual é o seu nome" in "\n".join(r["respostas"]).lower()
    assert not r["lead"].get("nome")
    r = api.msg_full(TEL, "oi", nome="não sei", canal="web")
    assert "qual é o seu nome" in "\n".join(r["respostas"]).lower()
    r = api.msg_full(TEL, "oi", nome="  Maria   Souza ", canal="web")
    assert "Olá, Maria!" in "\n".join(r["respostas"])
    assert r["lead"]["nome"] == "Maria Souza"


# ------------------------------------------------------------ item 7: avisos aparecem no chat web

def test_avisos_vem_marcados_no_chat_web(api):
    api.status("ana", "livre")
    r = api.msg_full(TEL, "quero falar com um atendente", nome="Maria Souza", canal="web")
    sessao = r["sessao"]
    ch = api.chamado_aberto(r["lead"]["id"])["id"]
    assert ok(api.assumir("ana", ch)[0])
    st, m = api.get(f"/api/web/{sessao}", token=None)
    assert st == 200
    avisos = [x for x in m["mensagens"] if x.get("tipo") == "aviso"]
    assert avisos and "Ana vai te atender agora." in avisos[-1]["texto"]
    assert all(x.get("tipo") != "aviso" for x in m["mensagens"] if x["de"] == "lead")
    js = (RAIZ / "web" / "chat.js").read_text()
    assert "'aviso'" in js


# ------------------------------------------------------------ item 8: remoteJid já é internacional

def _evo(api, jid, texto="oi", ident="EX1"):
    corpo = {"event": "messages.upsert", "instance": INSTANCIA, "data": {
        "key": {"remoteJid": jid, "fromMe": False, "id": ident}, "pushName": "John",
        "message": {"conversation": texto}, "messageType": "conversation"}}
    return api.post(f"/webhook/evolution/{SEGREDO_WH}", corpo, token=None)


def test_telefone_estrangeiro_do_remotejid_sem_55(api_int, externo):
    st, _ = _evo(api_int, "12125551234@s.whatsapp.net")
    assert st == 200
    assert esperar(lambda: [p for p in externo.whats() if p["json"].get("number") == "12125551234"])
    assert not [p for p in externo.whats() if str(p["json"].get("number", "")).startswith("5512125551234")]
    st, r = api_int.get("/api/gestor/leads")
    tels = json.dumps(r)
    assert "12125551234" in tels and "5512125551234" not in tels


# ------------------------------------------------------------ item 9: apagar edita o privado do dono

def test_apagar_edita_mensagens_do_lead_no_privado(api_int, tg, externo):
    equipe_pronta(api_int, tg, ("ana",))
    lead, ch = api_int.atendendo("ana")
    api_int.msg(TEL, "segue o endereço: Rua das Flores 10")
    assert esperar(lambda: externo.com_texto(externo.privado("ana"), "Rua das Flores"))
    externo.quieto()
    mid = externo.com_texto(externo.privado("ana"), "Rua das Flores")[-1]["message_id"]
    api_int.msg(TEL, "apagar meus dados")
    texto = f"🗑️ #{ch} lead pediu para apagar os dados"
    assert esperar(lambda: [p for p in externo.tg("editMessageText", TG_ID["ana"])
                            if p["json"].get("message_id") == mid and p["json"].get("text") == texto])


# ------------------------------------------------------------ item 10: token do gestor forte, arquivo 600

def test_config_token_gestor_forte_e_arquivo_600(api, dados):
    cfg = api.get("/api/gestor/config")[1]
    ex = json.loads((RAIZ / "exemplos" / "negocio.json").read_text())["token_gestor"]
    for ruim in ("curto-demais", "TROQUE-ESTE-TOKEN", ex):
        st, r = api.put("/api/gestor/config", dict(cfg, token_gestor=ruim))
        assert st == 422, (ruim, st, r)
    assert json.loads((dados / "negocio.json").read_text())["token_gestor"] == TOKEN
    st, _ = api.put("/api/gestor/config", dict(cfg, nome="Loja Nova"))  # "***" mantém o atual
    assert ok(st)
    assert stat.S_IMODE((dados / "negocio.json").stat().st_mode) == 0o600
    novo = "um-token-novo-bem-longo-123"
    assert ok(api.put("/api/gestor/config", dict(cfg, token_gestor=novo))[0])
    assert api.get("/api/gestor/config", token=novo)[0] == 200
    assert stat.S_IMODE((dados / "negocio.json").stat().st_mode) == 0o600


# ------------------------------------------------------------ item 11: webhook que desiste → descartes

def test_webhook_que_quebra_vai_para_descartes(api_int):
    corpo = {"event": "messages.upsert", "instance": INSTANCIA, "data": {
        "key": {"remoteJid": "5541999990009@s.whatsapp.net", "fromMe": False, "id": "QUEBRA1"},
        "message": ["isto não é um objeto"]}}
    st, r = api_int.post(f"/webhook/evolution/{SEGREDO_WH}", corpo, token=None)
    assert st == 200
    st, av = api_int.get("/api/gestor/ao-vivo")
    d = [x for x in av["descartes"] if x["origem"] == "evolution" and x.get("id") == "QUEBRA1"]
    assert d and d[0]["motivo"]
