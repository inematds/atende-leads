"""Estado (SQLite), configuração, relógio e utilitários comuns."""
import json
import os
import re
import secrets
import shutil
import sqlite3
import sys
import threading
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIAS = ('seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom')
FMT = '%Y-%m-%dT%H:%M'


class Erro(Exception):
    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def log(*args):
    print(*args, file=sys.stderr, flush=True)


def versao():
    try:
        return (ROOT / 'VERSION').read_text(encoding='utf-8').strip()
    except OSError:
        return '0.0.0'


def normalizar(texto):
    """Minúsculas, sem acento, sem pontuação, espaços simples."""
    texto = unicodedata.normalize('NFD', str(texto or '').lower())
    texto = ''.join(ch for ch in texto if unicodedata.category(ch) != 'Mn')
    return ' '.join(re.sub(r'[^\w\s]|_', ' ', texto).split())


def contem(t, termo):
    """Termo normalizado aparece no texto normalizado (como trecho)."""
    termo = normalizar(termo)
    return bool(termo) and termo in t


def normalizar_telefone(valor):
    if not isinstance(valor, (str, int)) or isinstance(valor, bool):
        raise Erro(422, 'Telefone inválido')
    dig = re.sub(r'\D', '', str(valor))
    if len(dig) in (10, 11):
        dig = '55' + dig
    if len(dig) < 12 or len(dig) > 13:
        raise Erro(422, 'Telefone inválido')
    return dig


def formatar_telefone(dig):
    dig = str(dig or '')
    if not dig.isdigit() or len(dig) < 12:
        return dig
    pais, ddd, resto = dig[:2], dig[2:4], dig[4:]
    return f'+{pais} ({ddd}) {resto[:-4]}-{resto[-4:]}'


def iso(dt):
    return dt.strftime(FMT) if dt else None


def parse(valor):
    if not valor:
        return None
    return datetime.strptime(valor[:16], FMT)


def minutos(desde, ate):
    if not desde:
        return 0
    d = parse(desde) if isinstance(desde, str) else desde
    return max(0, int((ate - d).total_seconds() // 60))


def primeiro_nome(nome):
    nome = (nome or '').strip()
    return nome.split()[0] if nome else 'lead'


def ddmm_hhmm(dt):
    return dt.strftime('%d/%m às %H:%M')


SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, nome TEXT, telefone TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'novo', status_antes TEXT, nota TEXT NOT NULL DEFAULT 'frio',
    interesse TEXT, urgencia INTEGER, nao_contatar INTEGER NOT NULL DEFAULT 0, canal TEXT,
    push_name TEXT, estado TEXT NOT NULL DEFAULT '{}', criado_em TEXT, ultimo_contato TEXT);
CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, chamado_id INTEGER, de TEXT NOT NULL,
    autor TEXT, texto TEXT, em TEXT);
CREATE INDEX IF NOT EXISTS mensagens_lead ON mensagens(lead_id, id);
CREATE TABLE IF NOT EXISTS colaboradores (
    id TEXT PRIMARY KEY, status TEXT NOT NULL DEFAULT 'fora', livre_desde TEXT, status_desde TEXT,
    telegram_id TEXT);
CREATE TABLE IF NOT EXISTS chamados (
    id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, motivo TEXT NOT NULL, prioridade TEXT NOT NULL,
    status TEXT NOT NULL, ofertado_a TEXT, ofertado_em TEXT, recusaram TEXT NOT NULL DEFAULT '[]',
    dono TEXT, aberto_em TEXT, conta_desde TEXT, assumido_em TEXT, fechado_em TEXT, resultado TEXT,
    valor REAL, produto TEXT, motivo_fechamento TEXT, nota_fechamento TEXT, retornar_em TEXT,
    token TEXT UNIQUE NOT NULL, resumo TEXT, alertado INTEGER NOT NULL DEFAULT 0,
    ultimo_mov TEXT, lembrado INTEGER NOT NULL DEFAULT 0,
    tg_linha TEXT, tg_alerta TEXT, tg_oferta TEXT, tg_cartao TEXT);
CREATE INDEX IF NOT EXISTS chamados_status ON chamados(status, aberto_em);
CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, dados TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saida (
    id INTEGER PRIMARY KEY, lead_id INTEGER, telefone TEXT, texto TEXT, tipo TEXT, status TEXT, em TEXT);
CREATE TABLE IF NOT EXISTS retornos (
    chamado_id INTEGER PRIMARY KEY, lead_id INTEGER, colaborador TEXT, em TEXT,
    enviado INTEGER NOT NULL DEFAULT 0, assumido INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS evolution_ids (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS tg_msgs (chat_id TEXT, message_id TEXT, chamado_id INTEGER, tipo TEXT,
    PRIMARY KEY (chat_id, message_id));
CREATE TABLE IF NOT EXISTS tg_fluxo (colaborador TEXT PRIMARY KEY, dados TEXT NOT NULL);
'''


class App:
    def __init__(self, pasta):
        self.pasta = Path(pasta)
        self.pasta.mkdir(parents=True, exist_ok=True)
        arq = self.pasta / 'negocio.json'
        if not arq.exists():
            shutil.copyfile(ROOT / 'exemplos' / 'negocio.json', arq)
        self.cfg = json.loads(arq.read_text(encoding='utf-8'))
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.pasta / 'leads.db', check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript(SCHEMA)
        self.sujo = False
        fixo = os.environ.get('ATENDE_AGORA')
        self.modo_teste = bool(fixo)
        self._agora = datetime.strptime(fixo[:16], FMT) if fixo else None
        self.sincronizar_equipe()

    # ---- transação ----
    def transacao(self):
        return _Transacao(self)

    # ---- relógio ----
    def agora(self):
        if self._agora is not None:
            return self._agora
        return datetime.now().replace(second=0, microsecond=0)

    def mudar_relogio(self, valor):
        if not self.modo_teste:
            raise Erro(403, 'Relógio só pode mudar com ATENDE_AGORA')
        try:
            self._agora = datetime.strptime(str(valor)[:16], FMT)
        except (TypeError, ValueError):
            raise Erro(422, 'Use AAAA-MM-DDTHH:MM')
        return iso(self._agora)

    # ---- configuração ----
    def salvar_cfg(self, cfg):
        arq = self.pasta / 'negocio.json'
        tmp = arq.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
        os.replace(tmp, arq)
        self.cfg = cfg
        self.sincronizar_equipe()

    def sincronizar_equipe(self):
        agora = iso(self.agora())
        for m in self.cfg.get('equipe', []):
            self.db.execute('INSERT OR IGNORE INTO colaboradores(id,status,status_desde) VALUES (?,?,?)',
                            (m['id'], 'fora', agora))

    def membro(self, ident):
        for m in self.cfg.get('equipe', []):
            if m['id'] == ident:
                return m
        return None

    def nome_colab(self, ident):
        m = self.membro(ident)
        return m['nome'] if m else (ident or '')

    def produto(self, ident):
        for p in self.cfg.get('produtos', []):
            if p['id'] == ident:
                return p
        return None

    def prazo(self, chave, padrao):
        try:
            return int(self.cfg.get('prazos', {}).get(chave, padrao))
        except (TypeError, ValueError):
            return padrao

    # ---- leitura ----
    def lead(self, ident):
        r = self.db.execute('SELECT * FROM leads WHERE id=?', (ident,)).fetchone()
        if not r:
            raise Erro(404, 'Lead inexistente')
        return r

    def lead_token(self, token):
        r = self.db.execute('SELECT * FROM leads WHERE token=?', (token,)).fetchone()
        if not r:
            raise Erro(404, 'Não encontrado')
        return r

    def chamado(self, ident):
        r = self.db.execute('SELECT * FROM chamados WHERE id=?', (ident,)).fetchone()
        if not r:
            raise Erro(404, 'Chamado inexistente')
        return r

    def colab(self, ident):
        r = self.db.execute('SELECT * FROM colaboradores WHERE id=?', (ident,)).fetchone()
        if not r or not self.membro(ident):
            raise Erro(404, 'Colaborador inexistente')
        return r

    def meta(self, chave, valor=None, gravar=False):
        if gravar:
            self.db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (chave, valor))
            return valor
        r = self.db.execute('SELECT valor FROM meta WHERE chave=?', (chave,)).fetchone()
        return r[0] if r else valor

    def url_publica(self):
        return str(self.cfg.get('url_publica') or '').rstrip('/')

    def fechar(self):
        self.db.close()


class _Transacao:
    def __init__(self, app):
        self.app = app

    def __enter__(self):
        self.app.lock.acquire()
        self.app.db.execute('BEGIN IMMEDIATE')
        return self.app

    def __exit__(self, tipo, valor, tb):
        try:
            if tipo is None:
                self.app.db.execute('COMMIT')
            else:
                self.app.sujo = False
                self.app.db.execute('ROLLBACK')
        finally:
            self.app.lock.release()
        return False


def novo_token():
    return secrets.token_urlsafe(18)


def depois(dt, minutos_):
    return dt + timedelta(minutes=minutos_)
