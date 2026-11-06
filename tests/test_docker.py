"""Seção 17: entrega em Docker para a VPS (estático; build real só com TESTAR_DOCKER=1)."""
import os
import re
import shutil
import subprocess
import time

import pytest

from conftest import RAIZ

VARIAVEIS = ("EVOLUTION_URL", "EVOLUTION_API_KEY", "EVOLUTION_INSTANCIA", "WEBHOOK_SEGREDO",
             "TELEGRAM_API_URL", "TELEGRAM_TOKEN", "TELEGRAM_GRUPO_ID", "TELEGRAM_SEGREDO", "CEREBRO_API_KEY")


def ler(nome):
    p = RAIZ / nome
    assert p.exists(), f"falta {nome}"
    return p.read_text()


def test_dockerfile():
    d = ler("Dockerfile")
    assert re.search(r"^FROM\s+python:3", d, re.M)
    assert "pip install" not in d
    plano = d.replace("\n", " ").replace('"', "").replace(",", " ")
    assert re.search(r"serve.*--host\s+0\.0\.0\.0", plano)
    assert re.search(r"--porta\s+8080", plano) and re.search(r"--dados\s+/dados", plano)
    assert "HEALTHCHECK" in d and "/api/saude" in d


def test_compose():
    c = ler("docker-compose.yml")
    for trecho in ("atende:", "build: .", "unless-stopped", "env_file", ".env", "./dados:/dados",
                   "127.0.0.1:8080:8080"):
        assert trecho in c, trecho


def test_compose_perfil_evolution_so_em_localhost():
    c = ler("docker-compose.yml")
    assert re.search(r"profiles:\s*(\[\s*['\"]?evolution|\n\s*-\s*['\"]?evolution)", c)
    assert "evolution" in c.lower()
    portas = re.findall(r"^\s*-\s*['\"]?((?:[\d.]+:)?\d+:\d+)['\"]?\s*$", c, re.M)
    assert portas
    for p in portas:
        assert p.startswith("127.0.0.1:"), f"porta exposta fora do localhost: {p}"


def test_env_exemplo():
    e = ler(".env.exemplo")
    for var in VARIAVEIS:
        assert re.search(rf"^{var}=", e, re.M), var
    assert not re.search(r"\d{8,10}:[A-Za-z0-9_-]{30,}", e)  # formato de token real do Telegram
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", e)


def test_instalar_vps():
    p = RAIZ / "instalar-vps.sh"
    assert p.exists()
    assert os.access(p, os.X_OK)
    s = p.read_text()
    assert "--sem-perguntas" in s
    for trecho in ("docker", ".env", "negocio.json", "setWebhook"):
        assert trecho in s, trecho


def test_readme():
    r = ler("README.md")
    assert "Deploy na VPS" in r
    assert "O processo, do início ao fim" in r


@pytest.mark.skipif(not (shutil.which("docker") and os.environ.get("TESTAR_DOCKER") == "1"),
                    reason="build real só com docker e TESTAR_DOCKER=1")
def test_docker_build_e_compose_config():
    b = subprocess.run(["docker", "build", "-q", "-t", "atende-leads-teste", "."], cwd=RAIZ,
                       capture_output=True, text=True, timeout=900)
    assert b.returncode == 0, b.stderr
    env = dict(os.environ)
    criado = False
    if not (RAIZ / ".env").exists():
        shutil.copy(RAIZ / ".env.exemplo", RAIZ / ".env")
        criado = True
    try:
        for extra in ([], ["--profile", "evolution"]):
            c = subprocess.run(["docker", "compose", *extra, "config", "-q"], cwd=RAIZ, env=env,
                               capture_output=True, text=True, timeout=120)
            assert c.returncode == 0, c.stderr
    finally:
        if criado:
            (RAIZ / ".env").unlink()
    # Seção 1: com os segredos do exemplo e --host 0.0.0.0 (CMD da imagem) o container recusa subir...
    r = subprocess.run(["docker", "run", "--rm", "atende-leads-teste"], capture_output=True, text=True, timeout=120)
    assert r.returncode != 0 and "instalar-vps.sh" in r.stderr, (r.returncode, r.stderr)
    # ...e ATENDE_PERMITIR_EXEMPLO=1 (só teste/demonstração) libera; o HEALTHCHECK responde.
    nome = "atende-leads-teste-saude"
    subprocess.run(["docker", "rm", "-f", nome], capture_output=True, timeout=60)
    r = subprocess.run(["docker", "run", "-d", "--name", nome, "-e", "ATENDE_PERMITIR_EXEMPLO=1",
                        "atende-leads-teste"], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    try:
        saude = None
        for _ in range(40):
            saude = subprocess.run(["docker", "exec", nome, "python3", "-c",
                                    "import json,urllib.request; print(json.load(urllib.request.urlopen("
                                    "'http://127.0.0.1:8080/api/saude', timeout=3))['ok'])"],
                                   capture_output=True, text=True, timeout=30)
            if saude.stdout.strip() == "True":
                break
            time.sleep(0.5)
        assert saude.stdout.strip() == "True", (saude.stdout, saude.stderr)
    finally:
        subprocess.run(["docker", "rm", "-f", nome], capture_output=True, timeout=60)
