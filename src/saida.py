"""Despachante da caixa de saída (outbox): Telegram (`tg_saida`) e WhatsApp/Evolution (`saida`).

Uma thread por canal. Dentro do lock só lê o que está devido e grava o resultado (transações curtas);
a chamada HTTP acontece fora. Ordem por destino: só a mensagem mais antiga pendente de cada destino
é tentada; se ela está esperando o backoff, as seguintes daquele destino esperam também.
Falha transitória → backoff exponencial (5, 10, 20… s, teto 300 s), no máximo MAX_TENTATIVAS, depois `falhou`.
"""
import json
import threading
import time

from .core import log
from . import evolution
from . import telegram as tg

MAX_TENTATIVAS = 8
LOTE = 20
TETO_BACKOFF = 300


def backoff(tentativas):
    return min(5 * 2 ** max(tentativas - 1, 0), TETO_BACKOFF)


class Despachante:
    def __init__(self, app, nome):
        self.app, self.nome = app, nome
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self._rodar, name=f'saida-{nome}', daemon=True)

    def iniciar(self):
        self.thread.start()
        return self

    def encerrar(self):
        self.parar.set()
        self.app.acordar[self.nome].set()
        self.thread.join(1)

    def _rodar(self):
        ev = self.app.acordar[self.nome]
        espera = 0.0
        while not self.parar.is_set():
            ev.wait(espera if espera > 0 else None)
            ev.clear()
            if self.parar.is_set():
                return
            try:
                espera = self.rodada()
            except Exception as e:
                log(f'saida {self.nome}: {type(e).__name__}: {e}')
                espera = 1.0

    # ---- uma rodada: devolve quanto esperar até a próxima (0 = só quando acordarem) ----
    def rodada(self):
        while not self.parar.is_set():
            agora = time.time()
            with self.app.transacao() as c:
                cabecas, prox = self.devidos(c, agora)
            if not cabecas:
                return max(0.05, prox - agora) if prox else 0
            for item in cabecas[:LOTE]:
                if self.parar.is_set():
                    return 0
                self.despachar(item)
        return 0

    def devidos(self, c, agora):
        tabela = 'tg_saida' if self.nome == 'tg' else 'saida'
        destino = 'chat_id' if self.nome == 'tg' else 'COALESCE(destino, telefone)'
        rows = c.db.execute(f"SELECT *, {destino} AS _dest FROM {tabela} WHERE status='pendente' ORDER BY id "
                            'LIMIT 500').fetchall()
        vistos, cabecas, prox = set(), [], None
        for r in rows:
            d = r['_dest'] or f"_{r['metodo'] if self.nome == 'tg' else ''}"
            if d in vistos:
                continue
            vistos.add(d)
            if r['proxima'] <= agora:
                cabecas.append(dict(r))
            elif prox is None or r['proxima'] < prox:
                prox = r['proxima']
        if self.nome == 'tg' and cabecas:
            ids = [r['id'] for r in cabecas[:LOTE]]
            c.db.execute(f"UPDATE tg_saida SET status='enviando' WHERE id IN ({','.join('?' * len(ids))})", ids)
        return cabecas, prox

    def despachar(self, item):
        if self.nome == 'tg':
            self._tg(item)
        else:
            self._evo(item)

    # ---------- Telegram ----------
    def _fim_tg(self, item, ok, transitorio, message_id=None):
        with self.app.transacao() as c:
            if ok:
                # corpo='{}': o texto (nome, telefone, mensagens do lead) só vive no Telegram, não fica aqui
                c.db.execute("UPDATE tg_saida SET status='enviado', corpo='{}', message_id=? WHERE id=?",
                             (None if message_id is None else str(message_id), item['id']))
                if message_id is not None and item['metodo'] == 'sendMessage':
                    # troca a referência provisória pelo id real (as linhas antigas da fila podem ser podadas)
                    q, real = f"q:{item['id']}", f"{item['chat_id']}:{message_id}"
                    for campo in ('tg_linha', 'tg_alerta', 'tg_oferta', 'tg_cartao'):
                        c.db.execute(f'UPDATE chamados SET {campo}=? WHERE {campo}=?', (real, q))
                    c.db.execute("UPDATE tg_saida SET alvo=? WHERE alvo=? AND status='pendente'", (real, q))
                if message_id is not None and item.get('tipo') and item.get('chamado_id'):
                    c.db.execute('INSERT OR REPLACE INTO tg_msgs VALUES (?,?,?,?)',
                                 (item['chat_id'], str(message_id), item['chamado_id'], item['tipo']))
                return
            n = item['tentativas'] + 1
            if transitorio and n < MAX_TENTATIVAS:
                c.db.execute("UPDATE tg_saida SET status='pendente', tentativas=?, proxima=? WHERE id=?",
                             (n, time.time() + backoff(n), item['id']))
                self.app.acordar['tg'].set()
            else:
                c.db.execute("UPDATE tg_saida SET status='falhou', corpo='{}', tentativas=? WHERE id=?", (n, item['id']))

    def _resolver(self, ref):
        """(chat, message_id) da referência; None = ainda pendente; () = não tem como."""
        with self.app.transacao() as c:
            real = tg.resolver(c, ref)
        if real is None:
            return None
        if not real:
            return ()
        chat, mid = real.rsplit(':', 1)
        return chat, (int(mid) if mid.lstrip('-').isdigit() else mid)

    def _tg(self, item):
        corpo = json.loads(item['corpo'])
        metodo = item['metodo']
        if metodo == 'painel':
            return self._painel(item, corpo['text'])
        if metodo == 'editMessageText':
            alvo = self._resolver(item['alvo'])
            if alvo is None:  # a mensagem original ainda não saiu (não deveria: vem antes na fila)
                with self.app.transacao() as c:
                    c.db.execute("UPDATE tg_saida SET status='pendente', proxima=? WHERE id=?",
                                 (time.time() + 0.2, item['id']))
                self.app.acordar['tg'].set()
                return
            if not alvo:
                return self._fim_tg(item, False, False)
            corpo['chat_id'], corpo['message_id'] = alvo
        ok, trans, r = tg.chamar_status(metodo, corpo)
        if not ok and metodo == 'editMessageText' and 'not modified' in str(r.get('description', '')):
            ok = True
        mid = (r.get('result') or {}).get('message_id') if ok and isinstance(r.get('result'), dict) else None
        self._fim_tg(item, ok, trans, mid)

    def _painel(self, item, texto):
        with self.app.transacao() as c:
            ref, antigo = c.meta('painel_ref'), c.meta('painel_texto')
        gid = item['chat_id']
        if ref and ref.split(':', 1)[0] == str(gid):
            if antigo == texto:
                return self._fim_tg(item, True, False)
            chat, mid = ref.rsplit(':', 1)
            ok, _t, r = tg.chamar_status('editMessageText', {
                'chat_id': chat, 'message_id': int(mid) if mid.lstrip('-').isdigit() else mid, 'text': texto,
                'reply_markup': tg.teclado([])})
            if ok or 'not modified' in str(r.get('description', '')):
                with self.app.transacao() as c:
                    c.meta('painel_texto', texto, gravar=True)
                return self._fim_tg(item, True, False)
        ok, trans, r = tg.chamar_status('sendMessage', {'chat_id': gid, 'text': texto})
        mid = (r.get('result') or {}).get('message_id') if ok else None
        if mid is None:
            return self._fim_tg(item, False, trans)
        novo = f'{gid}:{mid}'
        with self.app.transacao() as c:
            c.meta('painel_ref', novo, gravar=True)
            c.meta('painel_texto', texto, gravar=True)
        tg.chamar_status('pinChatMessage', {'chat_id': gid, 'message_id': mid, 'disable_notification': True})
        self._fim_tg(item, True, False, mid)

    # ---------- WhatsApp (Evolution) ----------
    def _evo(self, item):
        if item['tentativas'] > 0 or not evolution.configurado():
            with self.app.transacao() as c:
                if not evolution.configurado():
                    c.db.execute("UPDATE saida SET status='simulado', destino=NULL WHERE id=?", (item['id'],))
                    return
                lead = c.db.execute('SELECT nao_contatar FROM leads WHERE id=?', (item['lead_id'],)).fetchone()
                if lead and lead['nao_contatar']:  # §4.1: quem pediu PARAR não recebe reenvio
                    c.db.execute("UPDATE saida SET status='cancelado', destino=NULL WHERE id=?", (item['id'],))
                    return
        status = evolution.enviar_http(item['destino'] or item['telefone'], item['texto'])
        with self.app.transacao() as c:
            if status == 'enviado' or status == 'simulado':
                c.db.execute('UPDATE saida SET status=?, destino=NULL WHERE id=?', (status, item['id']))
                return
            n = item['tentativas'] + 1
            if n >= MAX_TENTATIVAS:
                c.db.execute("UPDATE saida SET status='falhou', tentativas=?, destino=NULL WHERE id=?",
                             (n, item['id']))
            else:
                c.db.execute('UPDATE saida SET tentativas=?, proxima=? WHERE id=?',
                             (n, time.time() + backoff(n), item['id']))
                self.app.acordar['evo'].set()


PODAR_ACIMA = 5000


def podar(app):
    """Mantém só as últimas PODAR_ACIMA linhas já resolvidas da fila do Telegram."""
    with app.transacao() as c:
        c.db.execute("DELETE FROM tg_saida WHERE status IN ('enviado','falhou') AND id < "
                     '(SELECT COALESCE(MAX(id), 0) FROM tg_saida) - ?', (PODAR_ACIMA,))


def iniciar(app):
    with app.transacao() as c:  # envio interrompido por queda do processo volta para a fila
        c.db.execute("UPDATE tg_saida SET status='pendente' WHERE status='enviando'")
    podar(app)
    app.acordar['tg'].set()
    app.acordar['evo'].set()
    return [Despachante(app, 'tg').iniciar(), Despachante(app, 'evo').iniciar()]


def aguardar(app, itens, teto=2.0):
    """Espera (fora do lock) os itens desta requisição saírem, até `teto` segundos."""
    if not itens:
        return
    tg_ids = [i for f, i in itens if f == 'tg']
    evo_ids = [i for f, i in itens if f == 'evo']
    fim = time.time() + teto
    while time.time() < fim:
        with app.lock:
            falta = 0
            if tg_ids:
                falta += app.db.execute(
                    f"SELECT COUNT(*) FROM tg_saida WHERE status IN ('pendente','enviando') AND tentativas=0 AND id IN "
                    f"({','.join('?' * len(tg_ids))})", tg_ids).fetchone()[0]
            if evo_ids:
                falta += app.db.execute(
                    f"SELECT COUNT(*) FROM saida WHERE status='pendente' AND tentativas=0 AND id IN "
                    f"({','.join('?' * len(evo_ids))})", evo_ids).fetchone()[0]
        if not falta:
            return
        time.sleep(0.02)


def ocioso_tg(app, teto=1.0):
    """Espera não haver envio ao Telegram em andamento (para o reply achar o message_id gravado)."""
    fim = time.time() + teto
    while time.time() < fim:
        with app.lock:
            n = app.db.execute("SELECT COUNT(*) FROM tg_saida WHERE status IN ('pendente','enviando') "
                               'AND tentativas=0').fetchone()[0]
        if not n:
            return
        time.sleep(0.02)
