"""Cérebro do agente (seção 14). 'regras' cobre tudo; ollama/openai só resumem e tiram dúvida.

Qualquer erro, timeout (15 s) ou resposta vazia cai na regra. A URL vem só do negocio.json
e a chave só de CEREBRO_API_KEY. Nenhuma chamada acontece dentro do lock do banco.
"""
import os

from . import rede

URGENCIA = {1: 'hoje', 2: 'este mês', 3: 'pesquisando'}
ASSUNTO = {'pediu_humano': 'falar com alguém', 'venda': 'comprar', 'precisa': 'resolver um problema'}
TIMEOUT = 15


def tipo(c):
    t = (c.cfg.get('cerebro') or {}).get('tipo') or 'regras'
    return t if t in ('regras', 'ollama', 'openai') else 'regras'


def _ultima(c, lead_id):
    r = c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' ORDER BY id DESC LIMIT 1",
                     (lead_id,)).fetchone()
    return r['texto'] if r else ''


def resumo_regras(c, lead, motivo):
    linhas = []
    prod = c.produto(lead['interesse']) if lead['interesse'] else None
    linhas.append(f"Quer: {prod['nome'] if prod else ASSUNTO.get(motivo, 'atendimento')}")
    if lead['urgencia'] in URGENCIA:
        linhas.append(f"Urgência: {URGENCIA[lead['urgencia']]}")
    ultima = _ultima(c, lead['id'])
    if ultima:
        linhas.append(f'Disse: "{ultima[:120]}"')
    return '\n'.join(linhas)


def resumo(c, lead, motivo):
    base = resumo_regras(c, lead, motivo)
    if tipo(c) == 'regras':
        return base
    hist = c.db.execute('SELECT de, texto FROM mensagens WHERE lead_id=? ORDER BY id DESC LIMIT 10',
                        (lead['id'],)).fetchall()
    conversa = '\n'.join(f"{r['de']}: {r['texto']}" for r in reversed(hist))
    texto = perguntar(c, 'Resuma em até 3 linhas curtas, em português, o que o cliente quer e a urgência. '
                         'Não invente nada que não esteja na conversa.', conversa)
    if not texto:
        return base
    return '\n'.join(texto.strip().splitlines()[:3])


def responder_duvida(c, texto):
    """Usado quando caiu em 'não entendi'. Devolve texto ou None (→ regra)."""
    if tipo(c) == 'regras':
        return None
    base = []
    for f in c.cfg.get('faq', []):
        base.append(f"P: {' / '.join(f.get('perguntas', []))}\nR: {f.get('resposta', '')}")
    for p in c.cfg.get('produtos', []):
        base.append(f"Produto: {p.get('nome')}" + (f" — preço {p['preco']}" if p.get('preco') else ' — sem preço informado'))
    sistema = (f"Você atende clientes de {c.cfg.get('nome', 'uma empresa')}. Responda curto, em português, "
               'usando SOMENTE a base abaixo. Nunca invente preço, prazo de entrega ou condição. '
               'Se a base não responder, diga exatamente: SEM_RESPOSTA.\n\n' + '\n\n'.join(base))
    r = perguntar(c, sistema, texto)
    if not r or 'SEM_RESPOSTA' in r:
        return None
    return r.strip()


def perguntar(c, sistema, usuario):
    """A chamada ao modelo roda FORA do lock: c.pronto desfaz a transação, chama e repete com o resultado."""
    cfg = dict(c.cfg.get('cerebro') or {})
    t = tipo(c)
    if not str(cfg.get('url') or '') or not cfg.get('modelo'):
        return None
    return c.pronto(('cerebro', t, str(cfg.get('url')), str(cfg.get('modelo')), sistema, usuario),
                    lambda: _perguntar(t, cfg, sistema, usuario))


def _perguntar(t, cfg, sistema, usuario):
    """Só rede: não toca no banco."""
    url = str(cfg.get('url') or '').rstrip('/')
    modelo = cfg.get('modelo')
    msgs = [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': usuario}]
    try:
        if t == 'ollama':
            ok, r = rede.postar(url + '/api/chat', {'model': modelo, 'messages': msgs, 'stream': False},
                                timeout=TIMEOUT)
            texto = ((r.get('message') or {}).get('content') if ok else None)
        else:
            if url.endswith('/chat/completions'):
                destino = url
            elif url.endswith('/v1'):
                destino = url + '/chat/completions'
            else:
                destino = url + '/v1/chat/completions'
            headers = {}
            chave = os.environ.get('CEREBRO_API_KEY')
            if chave:
                headers['Authorization'] = f'Bearer {chave}'
            ok, r = rede.postar(destino, {'model': modelo, 'messages': msgs, 'temperature': 0.2}, headers,
                                timeout=TIMEOUT)
            escolhas = r.get('choices') if ok else None
            texto = (escolhas[0].get('message') or {}).get('content') if escolhas else None
    except Exception:
        return None
    if not isinstance(texto, str) or not texto.strip():
        return None
    return texto
