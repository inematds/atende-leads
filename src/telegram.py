"""Cliente do Telegram (seção 16). Sem variáveis, nada sai do processo."""
import os

from . import rede


def configurado():
    return bool(os.environ.get('TELEGRAM_API_URL') and os.environ.get('TELEGRAM_TOKEN'))


def grupo():
    return os.environ.get('TELEGRAM_GRUPO_ID') or None


def chamar(metodo, corpo):
    if not configurado():
        return False, {}
    url = f"{os.environ['TELEGRAM_API_URL'].rstrip('/')}/bot{os.environ['TELEGRAM_TOKEN']}/{metodo}"
    ok, r = rede.postar(url, corpo)
    if ok and isinstance(r, dict) and r.get('ok') is False:
        ok = False
    return ok, r if isinstance(r, dict) else {}


def teclado(linhas):
    return {'inline_keyboard': [[b for b in linha if b] for linha in linhas if linha]}


def bt(texto, dados):
    return {'text': texto, 'callback_data': dados}


def bt_url(texto, url):
    return {'text': texto, 'url': url}


def enviar(chat_id, texto, botoes=None, reply=None):
    """Envia e devolve a referência 'chat:msg' (ou None)."""
    if not configurado() or not chat_id:
        return None
    corpo = {'chat_id': chat_id, 'text': texto}
    if botoes:
        corpo['reply_markup'] = teclado(botoes)
    if reply:
        corpo['reply_to_message_id'] = int(reply) if str(reply).isdigit() else reply
    ok, r = chamar('sendMessage', corpo)
    mid = (r.get('result') or {}).get('message_id') if ok else None
    return f'{chat_id}:{mid}' if mid is not None else None


def editar(ref, texto, botoes=None):
    """Edita a mensagem 'chat:msg'. Devolve True se o Telegram aceitou (ou se já estava igual)."""
    if not configurado() or not ref:
        return False
    chat_id, mid = ref.rsplit(':', 1)
    corpo = {'chat_id': chat_id, 'message_id': int(mid) if mid.isdigit() else mid, 'text': texto,
             'reply_markup': teclado(botoes or [])}
    ok, r = chamar('editMessageText', corpo)
    if not ok and 'not modified' in str(r.get('description', '')):
        return True
    return ok


def responder_callback(cid, texto=''):
    if cid:
        chamar('answerCallbackQuery', {'callback_query_id': cid, 'text': texto})


def fixar(ref):
    if ref:
        chat_id, mid = ref.rsplit(':', 1)
        chamar('pinChatMessage', {'chat_id': chat_id, 'message_id': int(mid) if mid.isdigit() else mid,
                                  'disable_notification': True})


def baixar_arquivo(file_id, destino):
    ok, r = chamar('getFile', {'file_id': file_id})
    caminho = (r.get('result') or {}).get('file_path') if ok else None
    if not caminho:
        return False
    url = f"{os.environ['TELEGRAM_API_URL'].rstrip('/')}/file/bot{os.environ['TELEGRAM_TOKEN']}/{caminho}"
    return rede.baixar(url, destino)
