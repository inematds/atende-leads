"""Cliente do Telegram (seção 16). Sem variáveis, nada sai do processo.

Nada aqui fala com a rede dentro da transação: enviar/editar/responder_callback/painel só gravam a
intenção em `tg_saida` (caixa de saída). O despachante (src/saida.py) manda fora do lock, na ordem,
por destino. `enviar` devolve a referência provisória `q:<id>`, trocada pelo message_id real na hora
do despacho (as edições da mesma conversa vêm depois na fila, então já acham o id).
"""
import json
import os

from . import rede

TRANSITORIOS = (0, 429)  # e >= 500: vale tentar de novo


def configurado():
    return bool(os.environ.get('TELEGRAM_API_URL') and os.environ.get('TELEGRAM_TOKEN'))


def grupo():
    return os.environ.get('TELEGRAM_GRUPO_ID') or None


# ---------- chamada direta (só fora do lock: despachante e download de áudio) ----------
def chamar_status(metodo, corpo, timeout=10):
    """Devolve (ok, transitório, resposta)."""
    if not configurado():
        return False, False, {}
    url = f"{os.environ['TELEGRAM_API_URL'].rstrip('/')}/bot{os.environ['TELEGRAM_TOKEN']}/{metodo}"
    st, r = rede.postar_status(url, corpo, timeout=timeout)
    r = r if isinstance(r, dict) else {}
    ok = 200 <= st < 300 and r.get('ok') is not False
    return ok, (not ok and (st in TRANSITORIOS or st >= 500)), r


def chamar(metodo, corpo):
    ok, _t, r = chamar_status(metodo, corpo)
    return ok, r


def baixar_arquivo(file_id, destino):
    ok, r = chamar('getFile', {'file_id': file_id})
    caminho = (r.get('result') or {}).get('file_path') if ok else None
    if not caminho:
        return False
    url = f"{os.environ['TELEGRAM_API_URL'].rstrip('/')}/file/bot{os.environ['TELEGRAM_TOKEN']}/{caminho}"
    return rede.baixar(url, destino)


# ---------- teclados ----------
def teclado(linhas):
    return {'inline_keyboard': [[b for b in linha if b] for linha in linhas if linha]}


def bt(texto, dados):
    return {'text': texto, 'callback_data': dados}


def bt_url(texto, url):
    return {'text': texto, 'url': url}


# ---------- caixa de saída ----------
def _enfileirar(c, chat_id, metodo, corpo, alvo=None, chave=None):
    if chave:
        c.db.execute("DELETE FROM tg_saida WHERE chave=? AND status='pendente'", (chave,))
    ident = c.db.execute('INSERT INTO tg_saida(chat_id,metodo,corpo,alvo,chave) VALUES (?,?,?,?,?)',
                         (str(chat_id) if chat_id is not None else None, metodo,
                          json.dumps(corpo, ensure_ascii=False), alvo, chave)).lastrowid
    c.enfileirar('tg', ident)
    return ident


def enviar(c, chat_id, texto, botoes=None, reply=None):
    """Põe na fila e devolve a referência provisória 'q:<id>' (ou None sem Telegram)."""
    if not configurado() or not chat_id:
        return None
    corpo = {'chat_id': chat_id, 'text': texto}
    if botoes:
        corpo['reply_markup'] = teclado(botoes)
    if reply:
        corpo['reply_to_message_id'] = int(reply) if str(reply).isdigit() else reply
    return f'q:{_enfileirar(c, chat_id, "sendMessage", corpo)}'


def chat_da_ref(c, ref):
    if not ref:
        return None
    if ref.startswith('q:'):
        r = c.db.execute('SELECT chat_id FROM tg_saida WHERE id=?', (ref[2:],)).fetchone()
        return r['chat_id'] if r else None
    return ref.rsplit(':', 1)[0]


def editar(c, ref, texto, botoes=None):
    """Agenda a edição da mensagem 'chat:msg' ou 'q:<id>'."""
    if not configurado() or not ref:
        return False
    corpo = {'text': texto, 'reply_markup': teclado(botoes or [])}
    _enfileirar(c, chat_da_ref(c, ref), 'editMessageText', corpo, alvo=ref)
    return True


def responder_callback(c, cid, texto=''):
    if cid and configurado():
        _enfileirar(c, None, 'answerCallbackQuery', {'callback_query_id': cid, 'text': texto})


def painel(c, gid, texto):
    """Painel fixo: só o último texto importa (coalesce)."""
    _enfileirar(c, gid, 'painel', {'text': texto}, chave='painel')


def resolver(c, ref):
    """'chat:msg' real de uma referência; None se ainda não saiu; '' se falhou."""
    if not ref:
        return ''
    if not ref.startswith('q:'):
        return ref
    r = c.db.execute('SELECT chat_id, status, message_id FROM tg_saida WHERE id=?', (ref[2:],)).fetchone()
    if not r:
        return ''
    if r['status'] in ('pendente', 'enviando'):
        return None
    return f"{r['chat_id']}:{r['message_id']}" if r['message_id'] else ''
