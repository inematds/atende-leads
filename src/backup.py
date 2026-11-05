"""Backup consistente (SQLite online backup + negocio.json) em .tar.gz, e restauração."""
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


def restaurar(dados, arquivo):
    """Com o servidor parado."""
    dados = Path(dados)
    dados.mkdir(parents=True, exist_ok=True)
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
