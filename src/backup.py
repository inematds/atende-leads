"""Backup consistente (SQLite online backup + negocio.json) em .tar.gz, e restauração."""
import fcntl
import io
import json
import os
import sqlite3
import tarfile
import tempfile
import time
from pathlib import Path


def copiar(dados, saida):
    dados, saida = Path(dados), Path(saida)
    banco = dados / 'leads.db'
    if not banco.exists():
        raise ValueError(f'{banco} não existe')
    if saida.resolve() in (banco.resolve(), (dados / 'negocio.json').resolve()):
        raise ValueError('O backup não pode sobrescrever o estado')
    saida.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=saida.parent) as tmp:
        snap = Path(tmp) / 'leads.db'
        origem = sqlite3.connect(banco)
        destino = sqlite3.connect(snap)
        try:
            origem.backup(destino)
        finally:
            destino.close()
            origem.close()
        arq = Path(tmp) / 'backup.tar.gz'
        with tarfile.open(arq, 'w:gz') as t:
            t.add(snap, 'leads.db')
            t.add(dados / 'negocio.json', 'negocio.json')
            info = tarfile.TarInfo('BACKUP.json')
            meta = json.dumps({'criado_em': time.strftime('%Y-%m-%dT%H:%M:%S')}).encode()
            info.size = len(meta)
            t.addfile(info, io.BytesIO(meta))
        os.replace(arq, saida)


TRAVA = '.serve.lock'
PARE = 'o servidor está rodando com estes dados; pare o serviço antes: docker compose stop atende'


def travar_servidor(dados):
    """O `serve` segura esta trava enquanto roda (o `restaurar` recusa). Devolve o arquivo aberto ou None."""
    f = open(Path(dados) / TRAVA, 'a+')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    f.seek(0)
    f.truncate()
    f.write(f'{os.getpid()}\n')
    f.flush()
    return f


def servidor_rodando(dados):
    arq = Path(dados) / TRAVA
    if not arq.exists():
        return False
    with open(arq, 'a+') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return True
        fcntl.flock(f, fcntl.LOCK_UN)
    return False


def restaurar(dados, arquivo):
    """Só com o servidor parado (trava do `serve` livre)."""
    dados = Path(dados)
    dados.mkdir(parents=True, exist_ok=True)
    if servidor_rodando(dados):
        raise ValueError(PARE)
    with tempfile.TemporaryDirectory(dir=dados) as tmp:
        with tarfile.open(arquivo, 'r:gz') as t:
            membros = {m.name: m for m in t.getmembers() if m.isfile()}
            if 'leads.db' not in membros or 'negocio.json' not in membros:
                raise ValueError('Arquivo de backup sem leads.db ou negocio.json')
            banco = Path(tmp) / 'leads.db'
            banco.write_bytes(t.extractfile(membros['leads.db']).read())
            config = t.extractfile(membros['negocio.json']).read()
        json.loads(config)
        db = sqlite3.connect(banco)
        try:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('Banco do backup corrompido')
            db.execute('SELECT id FROM leads LIMIT 1')
        finally:
            db.close()
        cfg = Path(tmp) / 'negocio.json'
        cfg.write_bytes(config)
        for suf in ('-wal', '-shm', '-journal'):
            (dados / ('leads.db' + suf)).unlink(missing_ok=True)
        os.replace(banco, dados / 'leads.db')
        os.replace(cfg, dados / 'negocio.json')
