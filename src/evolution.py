"""WhatsApp pela Evolution API v2 (seção 15) e caixa de saída."""
import hmac
import json
import os

from .core import Erro, iso, log, normalizar_telefone
from . import rede


def configurado():
    return bool(os.environ.get('EVOLUTION_URL'))


def enviar_http(telefone, texto):
    """Chamada HTTP de verdade: só o despachante (src/saida.py) chama, fora do lock."""
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
    """Põe na caixa de saída; o despachante entrega. tipo: agente|humano|aviso.

    Lead do chat web (com sessão) não recebe WhatsApp: a mensagem fica no chat (status `web`).
    """
    if automatica and lead['nao_contatar']:
        return None
    destino = str(telefone or lead['telefone'])
    if lead['sessao']:
        status = 'web'
    elif not configurado() or not destino.isdigit():
        status = 'simulado'
    else:
        status = 'pendente'
    ident = c.db.execute('INSERT INTO saida(lead_id,telefone,texto,tipo,status,em,destino) VALUES (?,?,?,?,?,?,?)',
                         (lead['id'], lead['telefone'], texto, tipo, status, iso(c.agora()),
                          destino if status == 'pendente' else None)).lastrowid
    if status == 'pendente':
        c.enfileirar('evo', ident)
    return status


def reenviar(c, forcar=False):
    """Tarefa de tempo: acorda o despachante. forcar=True (POST /api/tarefas/rodar) adianta o backoff."""
    if not configurado():
        c.db.execute("UPDATE saida SET status='simulado', destino=NULL WHERE status='pendente'")
        return 0
    if forcar:
        c.db.execute("UPDATE saida SET proxima=0 WHERE status='pendente'")
    r = c.db.execute("SELECT id FROM saida WHERE status='pendente' LIMIT 1").fetchone()
    if r:
        c.enfileirar('evo', r['id'])
    return 0


def registrar_descarte(c, origem, motivo, detalhe):
    """Mensagem de entrada que não deu para atender: fica visível no gestor (últimas 20)."""
    c.db.execute('INSERT INTO descartes(em,origem,motivo,detalhe) VALUES (?,?,?,?)',
                 (iso(c.agora()), origem, motivo, json.dumps(detalhe, ensure_ascii=False)))
    c.db.execute('DELETE FROM descartes WHERE id NOT IN (SELECT id FROM descartes ORDER BY id DESC LIMIT 20)')


def descartes(c):
    out = []
    for r in c.db.execute('SELECT * FROM descartes ORDER BY id DESC LIMIT 20'):
        try:
            det = json.loads(r['detalhe'] or '{}')
        except ValueError:
            det = {}
        out.append({'em': r['em'], 'origem': r['origem'], 'motivo': r['motivo'], **det})
    return out


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
    if jid.endswith('@lid'):
        # Identificador oculto do WhatsApp: o número real vem em key.remoteJidAlt (Evolution 2.3+)
        # ou key.senderPn / data.senderPn (versões anteriores).
        alt = next((str(v) for v in (key.get('remoteJidAlt'), key.get('senderPn'), key.get('senderPN'),
                                      data.get('senderPn'), data.get('senderPN'))
                    if v and not str(v).endswith('@lid')), '')
        if not alt:
            registrar_descarte(c, 'evolution', 'remoteJid @lid sem número (remoteJidAlt/senderPn)',
                               {'remoteJid': jid, 'id': ident, 'pushName': data.get('pushName')})
            log('evolution: @lid sem telefone alternativo: descartado')
            return
        jid = alt
    try:
        # O remoteJid já traz o código do país: não acrescenta 55 (número estrangeiro com 10–11 dígitos).
        telefone = normalizar_telefone(jid.split('@')[0].split(':')[0], internacional=True)
    except Erro:
        registrar_descarte(c, 'evolution', 'remoteJid inválido', {'remoteJid': jid, 'id': ident})
        log('evolution: remoteJid inválido ignorado')
        return
    msg = data.get('message') or {}
    texto = msg.get('conversation') or (msg.get('extendedTextMessage') or {}).get('text')
    push = data.get('pushName')
    if isinstance(texto, str) and texto.strip():
        conversa.receber(c, telefone, texto, canal='whatsapp', push_name=push, internacional=True)
    else:
        conversa.sem_texto(c, telefone, push)
