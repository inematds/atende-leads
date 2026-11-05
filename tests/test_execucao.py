"""Seções 1 e 18: execução, relógio, tarefas, persistência, backup e saúde."""
import json
import os
import subprocess
import tarfile

from conftest import AGORA, RAIZ, TEL, Servidor


def test_primeira_linha_porta_e_saude(api):
    st, r = api.get("/api/saude", token=None)
    assert st == 200
    assert r["ok"] is True
    assert isinstance(r["versao"], str) and r["versao"]
    assert r["evolution"] is False and r["telegram"] is False
    assert r["cerebro"] == "regras"


def test_saude_com_integracoes(api_int):
    st, r = api_int.get("/api/saude", token=None)
    assert st == 200 and r["ok"] is True
    assert r["evolution"] is True and r["telegram"] is True


def test_persistencia_ao_reiniciar(dados):
    s = Servidor(dados)
    api = s.subir()
    r = api.msg_full(TEL, "oi", nome="Maria Souza")
    token = r["lead"]["token"]
    api.status("ana", "livre")
    s.parar()

    api2 = Servidor(dados).subir()
    st, meu = api2.get(f"/api/meu/{token}", token=None)
    assert st == 200, (st, meu)
    assert meu["nome"] == "Maria Souza"
    assert api2.colab("ana")["status"] == "livre"
    assert (dados / "leads.db").exists()


def test_copia_exemplo_quando_dados_vazio(tmp_path):
    exemplo = RAIZ / "exemplos" / "negocio.json"
    assert exemplo.exists(), "falta exemplos/negocio.json"
    d = tmp_path / "vazio"
    d.mkdir()
    Servidor(d).subir()
    assert (d / "negocio.json").exists()
    assert json.loads((d / "negocio.json").read_text()) == json.loads(exemplo.read_text())


def test_relogio_403_sem_atende_agora(dados):
    api = Servidor(dados, agora=None).subir()
    st, _ = api.post("/api/relogio", {"agora": AGORA})
    assert st == 403


def test_relogio_exige_gestor(api):
    st, _ = api.post("/api/relogio", {"agora": AGORA}, token=None)
    assert st == 401


def test_tarefas_rodar_formato(api):
    r = api.rodar()
    assert r["ok"] is True
    assert isinstance(r["acoes"], int)


def test_tarefas_rodar_exige_gestor(api):
    st, _ = api.post("/api/tarefas/rodar", token="errado")
    assert st == 401


def _cli(*args):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("ATENDE_", "EVOLUTION_", "TELEGRAM_"))}
    return subprocess.run([str(RAIZ / "atende"), *args], cwd=RAIZ, env=env,
                          capture_output=True, text=True, timeout=60)


def test_backup_e_restaurar(dados, tmp_path):
    s = Servidor(dados)
    api = s.subir()
    token = api.msg_full(TEL, "oi", nome="Maria Souza")["lead"]["token"]
    s.parar()

    arq = tmp_path / "bkp.tar.gz"
    p = _cli("backup", "--dados", str(dados), "--saida", str(arq))
    assert p.returncode == 0, p.stderr
    assert arq.exists()
    with tarfile.open(arq, "r:gz") as t:
        nomes = [os.path.basename(n) for n in t.getnames()]
    assert "negocio.json" in nomes and "leads.db" in nomes

    novo = tmp_path / "restaurado"
    novo.mkdir()
    p = _cli("restaurar", "--dados", str(novo), "--arquivo", str(arq))
    assert p.returncode == 0, p.stderr
    api2 = Servidor(novo).subir()
    st, meu = api2.get(f"/api/meu/{token}", token=None)
    assert st == 200 and meu["nome"] == "Maria Souza"


def test_backup_com_servidor_rodando(api, dados, tmp_path):
    api.msg_full(TEL, "oi", nome="Maria Souza")
    arq = tmp_path / "quente.tar.gz"
    p = _cli("backup", "--dados", str(dados), "--saida", str(arq))
    assert p.returncode == 0, p.stderr
    with tarfile.open(arq, "r:gz") as t:
        assert any(n.endswith("leads.db") for n in t.getnames())


def test_sem_integracoes_nenhum_envio_e_saida_simulada(api):
    api.msg_full(TEL, "oi")
    saida = api.saida()
    assert saida, "resposta do agente deve aparecer na caixa de saída"
    assert all(m["status"] == "simulado" for m in saida)
