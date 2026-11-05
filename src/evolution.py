"""WhatsApp pela Evolution API v2 (seção 15) e caixa de saída."""
import hmac
import os

from .core import Erro, iso, log, normalizar_telefone
from . import rede


def configurado():
    return bool(os.environ.get('EVOLUTION_URL'))


def _enviar(telefone, texto):
    base = os.environ.get('EVOLUTION_URL', '').rstrip('/')
    if not base:
        return 'simulado'
    if not telefone or not str(telefone).isdigit():
        return 'simulado'
    url = f"{base}/message/sendText/{os.environ.get('EVOLUTION_INSTANCIA', '')}"
    ok, _ = rede.postar(url, {'number': telefone, 'text': texto},
                        {'apikey': os.environ.get('EVOLUTION_API_KEY', '')})
    return 'enviado' if ok else 'pendente'


def enviar_lead(c, lead, texto, tipo, automatica=False, telefone=None):
    """Põe na caixa de saída e tenta entregar. tipo: agente|humano|aviso."""
    if automatica and lead['nao_contatar']:
        return None
    ident = c.db.execute('INSERT INTO saida(lead_id,telefone,texto,tipo,status,em) VALUES (?,?,?,?,?,?)',
                         (lead['id'], lead['telefone'], texto, tipo, 'pendente', iso(c.agora()))).lastrowid
    status = _enviar(telefone or lead['telefone'], texto)
    c.db.execute('UPDATE saida SET status=? WHERE id=?', (status, ident))
    return status


def reenviar(c):
    n = 0
    for r in c.db.execute("SELECT * FROM saida WHERE status='pendente' ORDER BY id").fetchall():
        if not configurado():
            c.db.execute("UPDATE saida SET status='simulado' WHERE id=?", (r['id'],))
            continue
        status = _enviar(r['telefone'], r['texto'])
        c.db.execute('UPDATE saida SET status=? WHERE id=?', (status, r['id']))
        n += status == 'enviado'
    return n


def listar(c):
    return [{k: r[k] for k in ('id', 'telefone', 'texto', 'tipo', 'status', 'em')} | {'lead_id': r['lead_id']}
            for r in c.db.execute('SELECT * FROM saida ORDER BY id')]


def autorizar(segredo_rota):
    segredo = os.environ.get('WEBHOOK_SEGREDO', '')
    if not segredo or not hmac.compare_digest(str(segredo_rota).encode(), segredo.encode()):
        raise Erro(404, 'Não encontrado')


def receber(c, b):
    """Webhook messages.upsert. Sempre termina sem exceção para o chamador responder 200."""
    from . import conversa
    if not isinstance(b, dict) or b.get('event') not in ('messages.upsert', 'MESSAGES_UPSERT'):
        return
    data = b.get('data')
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return
    key = data.get('key') or {}
    jid = str(key.get('remoteJid') or '')
    ident = key.get('id')
    if key.get('fromMe') or jid.endswith('@g.us') or '@broadcast' in jid or not jid:
        return
    if ident:
        if c.db.execute('SELECT 1 FROM evolution_ids WHERE id=?', (str(ident),)).fetchone():
            return
        c.db.execute('INSERT INTO evolution_ids VALUES (?)', (str(ident),))
    try:
        telefone = normalizar_telefone(jid.split('@')[0].split(':')[0])
    except Erro:
        log('evolution: remoteJid inválido ignorado')
        return
    msg = data.get('message') or {}
    texto = msg.get('conversation') or (msg.get('extendedTextMessage') or {}).get('text')
    push = data.get('pushName')
    if isinstance(texto, str) and texto.strip():
        conversa.receber(c, telefone, texto, canal='whatsapp', push_name=push)
    else:
        conversa.sem_texto(c, telefone, push)
