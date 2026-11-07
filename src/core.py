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


def normalizar_telefone(valor, internacional=False):
    """internacional=True: número que já vem com o código do país (remoteJid do WhatsApp) — não ganha 55."""
    if not isinstance(valor, (str, int)) or isinstance(valor, bool):
        raise Erro(422, 'Telefone inválido')
    dig = re.sub(r'\D', '', str(valor))
    if internacional:
        if not 8 <= len(dig) <= 15:
            raise Erro(422, 'Telefone inválido')
        return dig
    if len(dig) in (10, 11):
        dig = '55' + dig
    if len(dig) < 12 or len(dig) > 13:
        raise Erro(422, 'Telefone inválido')
    return dig


def formatar_telefone(dig):
    dig = str(dig or '')
    if not dig.isdigit():
        return dig
    if not (dig.startswith('55') and len(dig) in (12, 13)):
        return '+' + dig if len(dig) >= 8 else dig
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
    """Primeiro nome para o grupo/painel; 'lead' se não houver ou se não parecer nome (dígito, sem letra)."""
    nome = (nome or '').strip()
    p = nome.split()[0] if nome else ''
    if not p or any(ch.isdigit() for ch in p) or not any(ch.isalpha() for ch in p):
        return 'lead'
    return p


def ddmm_hhmm(dt):
    return dt.strftime('%d/%m às %H:%M')


SCHEMA = '''
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, nome TEXT, telefone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'novo', status_antes TEXT, nota TEXT NOT NULL DEFAULT 'frio',
    interesse TEXT, urgencia INTEGER, nao_contatar INTEGER NOT NULL DEFAULT 0, canal TEXT,
    push_name TEXT, estado TEXT NOT NULL DEFAULT '{}', criado_em TEXT, ultimo_contato TEXT, sessao TEXT UNIQUE);
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
CREATE INDEX IF NOT EXISTS chamados_lead ON chamados(lead_id, status);
CREATE TABLE IF NOT EXISTS historico (id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL, dados TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS saida (
    id INTEGER PRIMARY KEY, lead_id INTEGER, telefone TEXT, texto TEXT, tipo TEXT, status TEXT, em TEXT,
    destino TEXT, tentativas INTEGER NOT NULL DEFAULT 0, proxima REAL NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS retornos (
    chamado_id INTEGER PRIMARY KEY, lead_id INTEGER, colaborador TEXT, em TEXT,
    enviado INTEGER NOT NULL DEFAULT 0, assumido INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS evolution_ids (id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS tg_msgs (chat_id TEXT, message_id TEXT, chamado_id INTEGER, tipo TEXT,
    PRIMARY KEY (chat_id, message_id));
CREATE TABLE IF NOT EXISTS tg_fluxo (colaborador TEXT PRIMARY KEY, dados TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tg_saida (
    id INTEGER PRIMARY KEY, chat_id TEXT, metodo TEXT NOT NULL, corpo TEXT NOT NULL, alvo TEXT,
    status TEXT NOT NULL DEFAULT 'pendente', tentativas INTEGER NOT NULL DEFAULT 0, proxima REAL NOT NULL DEFAULT 0,
    chave TEXT, chamado_id INTEGER, tipo TEXT, message_id TEXT);
CREATE INDEX IF NOT EXISTS tg_saida_pend ON tg_saida(status, id);
CREATE TABLE IF NOT EXISTS descartes (id INTEGER PRIMARY KEY, em TEXT, origem TEXT, motivo TEXT, detalhe TEXT);
CREATE TABLE IF NOT EXISTS vistos (colaborador TEXT NOT NULL, lead_id INTEGER NOT NULL, ate INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (colaborador, lead_id));
CREATE TABLE IF NOT EXISTS sugestoes (
    id INTEGER PRIMARY KEY, chamado_id INTEGER NOT NULL, lead_id INTEGER NOT NULL, msg_id INTEGER, dono TEXT,
    texto TEXT, status TEXT NOT NULL, origem TEXT, em TEXT, tg_ref TEXT, conflito TEXT, proposta_id INTEGER);
CREATE INDEX IF NOT EXISTS sugestoes_chamado ON sugestoes(chamado_id, id);
CREATE TABLE IF NOT EXISTS aprendizado (
    id INTEGER PRIMARY KEY, em TEXT, colaborador TEXT, lead_id INTEGER, chamado_id INTEGER, msg_lead TEXT,
    sugestao_id INTEGER, sugestao TEXT, enviado TEXT, origem TEXT, distancia REAL);
CREATE TABLE IF NOT EXISTS propostas (
    id INTEGER PRIMARY KEY, em TEXT, tipo TEXT, dados TEXT NOT NULL, origem TEXT, status TEXT NOT NULL DEFAULT 'nova');
CREATE TABLE IF NOT EXISTS fontes (
    id INTEGER PRIMARY KEY, em TEXT, tipo TEXT NOT NULL, fonte TEXT NOT NULL, status TEXT NOT NULL,
    paginas INTEGER NOT NULL DEFAULT 0, caracteres INTEGER NOT NULL DEFAULT 0, propostas INTEGER NOT NULL DEFAULT 0,
    erro TEXT, avisos TEXT);
'''

COLUNAS_LEADS = ('id, token, nome, telefone, status, status_antes, nota, interesse, urgencia, nao_contatar, canal, '
                 'push_name, estado, criado_em, ultimo_contato')


def migrar(db):
    """Bancos da 1.0.0: telefone era UNIQUE e não havia sessão web nem controle de reenvio."""
    cols = {r[1] for r in db.execute('PRAGMA table_info(leads)')}
    if 'sessao' not in cols:
        db.executescript(f'''
BEGIN;
CREATE TABLE leads_nova (
    id INTEGER PRIMARY KEY, token TEXT UNIQUE NOT NULL, nome TEXT, telefone TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'novo', status_antes TEXT, nota TEXT NOT NULL DEFAULT 'frio',
    interesse TEXT, urgencia INTEGER, nao_contatar INTEGER NOT NULL DEFAULT 0, canal TEXT,
    push_name TEXT, estado TEXT NOT NULL DEFAULT '{{}}', criado_em TEXT, ultimo_contato TEXT, sessao TEXT UNIQUE);
INSERT INTO leads_nova ({COLUNAS_LEADS}) SELECT {COLUNAS_LEADS} FROM leads;
DROP TABLE leads;
ALTER TABLE leads_nova RENAME TO leads;
COMMIT;''')
    cols = {r[1] for r in db.execute('PRAGMA table_info(saida)')}
    for nome, tipo in (('destino', 'TEXT'), ('tentativas', 'INTEGER NOT NULL DEFAULT 0'),
                       ('proxima', 'REAL NOT NULL DEFAULT 0')):
        if nome not in cols:
            db.execute(f'ALTER TABLE saida ADD COLUMN {nome} {tipo}')
    cols = {r[1] for r in db.execute('PRAGMA table_info(sugestoes)')}
    for nome, tipo in (('conflito', 'TEXT'), ('proposta_id', 'INTEGER')):  # 1.6.8
        if nome not in cols:
            db.execute(f'ALTER TABLE sugestoes ADD COLUMN {nome} {tipo}')
    # WhatsApp: um lead por telefone. Web: um lead por sessão (o telefone é só contato).
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS leads_telefone_whats ON leads(telefone) WHERE sessao IS NULL')


class ForaDoLock(BaseException):
    """Pede para rodar `fazer()` (rede/subprocesso) fora do lock e repetir a transação com o resultado.

    BaseException para não ser engolida pelos `except Exception` do caminho.
    """

    def __init__(self, chave, fazer):
        super().__init__(str(chave)[:80])
        self.chave, self.fazer = chave, fazer


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
        migrar(self.db)
        self.sujo = False
        self._local = threading.local()
        self.acordar = {'tg': threading.Event(), 'evo': threading.Event(), 'sug': threading.Event(),
                        'fonte': threading.Event()}
        self.fonte_mem = {}  # conteúdo das fontes em processamento (só em memória; sai ao terminar)
        fixo = os.environ.get('ATENDE_AGORA')
        self.modo_teste = bool(fixo)
        self._agora = datetime.strptime(fixo[:16], FMT) if fixo else None
        self.sincronizar_equipe()

    # ---- transação ----
    def transacao(self):
        return _Transacao(self)

    def executar(self, fn, depois=None):
        """Roda fn() numa transação curta. Rede/subprocesso pedidos por `pronto()` rodam fora do lock
        entre tentativas (a transação é desfeita e repetida com o resultado já pronto)."""
        self._local.prontos = {}
        self._local.ultimos = []
        try:
            for _ in range(6):
                self._local.abriu_publico = False  # marcado de novo se esta tentativa abrir chamado
                try:
                    with self.transacao():
                        r = fn()
                        if depois:
                            depois()
                        return r
                except ForaDoLock as p:
                    try:
                        self._local.prontos[p.chave] = p.fazer()
                    except Exception as e:
                        log(f'fora do lock: {type(e).__name__}: {e}')
                        self._local.prontos[p.chave] = None
            raise Erro(503, 'Tente de novo')
        finally:
            self._local.prontos = None

    def pronto(self, chave, fazer):
        """Resultado de uma chamada lenta (cérebro, áudio) feita fora do lock."""
        prontos = getattr(self._local, 'prontos', None)
        if prontos is None:
            return fazer()  # fora de executar(): não há lock a proteger
        if chave in prontos:
            return prontos[chave]
        raise ForaDoLock(chave, fazer)

    # ---- caixa de saída (outbox) ----
    def enfileirar(self, fila, ident):
        lst = getattr(self._local, 'fila', None)
        if lst is None:
            lst = self._local.fila = []
        lst.append((fila, ident))

    def enfileirados(self):
        """Itens que a última transação desta thread pôs na caixa de saída."""
        return list(getattr(self._local, 'ultimos', None) or [])

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
        os.chmod(tmp, 0o600)  # token do gestor e códigos da equipe: só o dono lê
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
        try:
            self.app.db.execute('BEGIN IMMEDIATE')
        except BaseException:
            self.app.lock.release()
            raise
        self.app._local.fila = []
        return self.app

    def __exit__(self, tipo, valor, tb):
        fila = getattr(self.app._local, 'fila', None) or []
        self.app._local.fila = []
        try:
            if tipo is None:
                self.app.db.execute('COMMIT')
                self.app._local.ultimos = fila
            else:
                self.app.sujo = False
                self.app.db.execute('ROLLBACK')
                fila = []
        finally:
            self.app.lock.release()
        for nome in {f for f, _ in fila}:
            self.app.acordar[nome].set()
        return False


def novo_token():
    return secrets.token_urlsafe(18)


def depois(dt, minutos_):
    return dt + timedelta(minutes=minutos_)
