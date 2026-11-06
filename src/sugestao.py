"""Sugestão de resposta para a equipe, registro de aprendizado e propostas para a base (seções 7a e 13a).

A sugestão nasce dentro da transação da mensagem do lead (status `gerando` ou já `pronta` por regras); com
cérebro LLM, quem chama o modelo é o Trabalhador, em segundo plano e fora do lock. As propostas periódicas
também saem pelo Trabalhador (a tarefa de tempo só marca o pedido em `meta`).
"""
import difflib
import json
import re
import threading
from datetime import timedelta

from .core import Erro, iso, log, normalizar, parse
from . import base, cerebro, equipe
from . import telegram as tg

ORIGENS = ('sugestao_ok', 'sugestao_editada', 'livre')
PERIODOS = {'diario': 1, 'semanal': 7, 'desligado': None}
JA_USADA = 'Essa sugestão já foi usada ou substituída.'


# ---------- sugestão ----------
def criar(c, ch, lead, texto):
    c.db.execute("UPDATE sugestoes SET status='substituida' WHERE chamado_id=? AND status IN ('gerando','pronta')",
                 (ch['id'],))
    msg = c.db.execute("SELECT MAX(id) FROM mensagens WHERE lead_id=? AND de='lead'", (lead['id'],)).fetchone()[0]
    agora = iso(c.agora())
    if cerebro.ligado(c):
        sid = c.db.execute("INSERT INTO sugestoes(chamado_id,lead_id,msg_id,dono,status,em) VALUES (?,?,?,?,?,?)",
                           (ch['id'], lead['id'], msg, ch['dono'], 'gerando', agora)).lastrowid
        c.enfileirar('sug', sid)  # acorda o Trabalhador no commit
        return sid
    txt = base.sugestao_regras(c, texto)
    if not txt:
        return None
    sid = c.db.execute("INSERT INTO sugestoes(chamado_id,lead_id,msg_id,dono,texto,status,origem,em) "
                       "VALUES (?,?,?,?,?,?,?,?)", (ch['id'], lead['id'], msg, ch['dono'], txt, 'pronta', 'regras',
                                                     agora)).lastrowid
    publicar(c, sid)
    return sid


BT_BASE = '📚 Atualizar a base'


def botoes(sid, conflito=None):
    linhas = [[tg.bt('✅ Enviar', f'sg:{sid}:ok'), tg.bt('✏️ Editar', f'sg:{sid}:ed')]]
    if conflito:
        linhas.append([tg.bt(BT_BASE, f'sb:{sid}')])
    return linhas


def texto_tg(s):
    return f"💡 Sugestão: {s['texto']}" + (f"\n\n⚠️ {s['conflito']}" if s['conflito'] else '')


def publicar(c, sid):
    from .chamados import guardar_msg
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    ref = equipe.privado(c, s['dono'], texto_tg(s), botoes(sid, s['conflito']))
    if ref:
        guardar_msg(c, ref, s['chamado_id'], f'sg:{sid}')
        c.db.execute('UPDATE sugestoes SET tg_ref=? WHERE id=?', (ref, sid))


INSTR_SUG = (
    'Você escreve a PRÓXIMA MENSAGEM do vendedor de {nome} ao cliente, em primeira pessoa, como se fosse o próprio '
    'vendedor (ele vai revisar e enviar). Português do Brasil, curto e cordial, texto simples.\n'
    'Ordem de verdade:\n'
    '(a) o que o vendedor já afirmou nesta conversa (preço, promoção, prazo, condição) é o dado mais atual e vale '
    'sobre a base; se ele afirmou valores diferentes em momentos diferentes, vale o ÚLTIMO;\n'
    '(b) a base de conhecimento abaixo.\n'
    'Na mensagem ao cliente, nunca mencione base, sistema, IA, "o vendedor" ou "a equipe vai confirmar" por causa de '
    'divergência interna, e não peça desculpa por inconsistência. Não invente o que não está nem na conversa nem na '
    'base: se faltar, pergunte ao cliente ou diga, de forma natural, que vai verificar.\n'
    'Responda SOMENTE com JSON: {{"resposta": "<texto pronto para enviar>", "conflito": "<1 frase interna, para o '
    'vendedor, descrevendo divergência entre a base e o que ele disse na conversa, ex.: \'A base diz R$ 1.200 para o '
    'Plano anual; você informou R$ 670 (promoção Black).\'; vazio se não houver>"}}')
SUG_SCHEMA = {'type': 'object', 'properties': {'resposta': {'type': 'string'}, 'conflito': {'type': 'string'}},
              'required': ['resposta', 'conflito'], 'additionalProperties': False}


def ler_sugestao(texto):
    """(resposta, conflito) da saída do modelo: JSON puro, dentro de ```json``` ou texto livre (conflito '')."""
    if not isinstance(texto, str) or not texto.strip():
        return '', ''
    d = cerebro.ler_json(texto)
    if d is not None and isinstance(d.get('resposta'), str):
        conf = d.get('conflito')
        return d['resposta'].strip(), (conf.strip() if isinstance(conf, str) else '')
    t = texto.strip()
    if t.startswith('```'):  # cerca sem JSON válido: tira as marcas
        t = re.sub(r'^```\w*\s*|\s*```$', '', t).strip()
    return t, ''


def contexto(c, sid):
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    if not s or s['status'] != 'gerando':
        return None
    ch = c.chamado(s['chamado_id'])
    if ch['status'] != 'atendendo':
        c.db.execute("UPDATE sugestoes SET status='substituida' WHERE id=?", (sid,))
        return None
    lead = c.lead(s['lead_id'])
    prod = c.produto(lead['interesse']) if lead['interesse'] else None
    dados = (f"Cliente: {lead['nome'] or 'nome não informado'}; interesse: {prod['nome'] if prod else 'não informado'}; "
             f"nota: {lead['nota']}" + (f"; urgência: {cerebro.URGENCIA.get(lead['urgencia'])}"
                                         if lead['urgencia'] in cerebro.URGENCIA else ''))
    usuario = (f'{dados}\nVendedor: {c.nome_colab(ch["dono"])}\n\nConversa (mais recente por último):\n'
               f"{cerebro.conversa_texto(c, lead['id'], 10)}\n\nEscreva a próxima resposta do vendedor.")
    return INSTR_SUG.format(nome=c.cfg.get('nome') or 'uma empresa'), usuario, base.texto_base(c)


def concluir(c, sid, texto):
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    if not s or s['status'] != 'gerando':
        return
    origem = 'cerebro'
    texto, conflito = ler_sugestao(texto)
    texto = (cerebro.limpar_md(texto) or '').strip().strip('"').strip()
    conflito = (cerebro.limpar_md(conflito) or '').strip()[:500] if texto else ''
    if not texto:
        m = c.db.execute('SELECT texto FROM mensagens WHERE id=?', (s['msg_id'],)).fetchone()
        texto, origem = (base.sugestao_regras(c, m['texto']) if m else None), 'regras'
    if not texto:
        c.db.execute("UPDATE sugestoes SET status='vazia' WHERE id=?", (sid,))
        return
    c.db.execute("UPDATE sugestoes SET texto=?, conflito=?, status='pronta', origem=? WHERE id=?",
                 (texto[:2000], conflito or None, origem, sid))
    publicar(c, sid)


def pronta_do_chamado(c, chamado_id):
    r = c.db.execute("SELECT id, texto, em, conflito, proposta_id FROM sugestoes WHERE chamado_id=? AND status='pronta' "
                     'ORDER BY id DESC LIMIT 1', (chamado_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d['conflito'] = d['conflito'] or ''
    return d


def da_ficha(c, lead_id):
    ch = c.db.execute("SELECT id FROM chamados WHERE lead_id=? AND status='atendendo' ORDER BY id DESC LIMIT 1",
                      (lead_id,)).fetchone()
    return pronta_do_chamado(c, ch['id']) if ch else None


def obter(c, sid, colab):
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    if not s:
        raise Erro(404, 'Sugestão inexistente')
    ch = c.chamado(s['chamado_id'])
    if ch['dono'] != colab or ch['status'] != 'atendendo':
        raise Erro(409, 'Esse atendimento não está com você.')
    if s['status'] != 'pronta':
        raise Erro(409, JA_USADA)
    return s, ch


# ---------- conflito → proposta para a base (botão "Atualizar a base") ----------
PRECO_TXT = re.compile(r'R\$\s?\d[\d.]*(?:,\d{1,2})?')
PROMO_TXT = re.compile(r'promo[cç][aã]o\s+([A-ZÀ-Ú][\wÀ-ú-]*(?:\s+[A-ZÀ-Ú][\wÀ-ú-]*)?)')


def _produto_do_conflito(c, lead, conflito):
    t = normalizar(conflito)
    for p in c.cfg.get('produtos') or []:
        if p.get('nome') and normalizar(p['nome']) in t:
            return p
    return c.produto(lead['interesse']) if lead['interesse'] else None


def para_base(c, sid, colab):
    """Cria (uma vez por sugestão) a proposta para o gestor a partir do conflito. Nunca usa o conflito (recado
    interno) como texto da base: preço → proposta `preco` com o último R$ que o vendedor escreveu; senão `info`
    em observações com a última mensagem do vendedor ao cliente como rascunho. `colab` None = gestor."""
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    if not s:
        raise Erro(404, 'Sugestão inexistente')
    ch = c.chamado(s['chamado_id'])
    if colab is not None and ch['dono'] != colab:
        raise Erro(409, 'Esse atendimento não está com você.')
    if s['proposta_id']:
        return {'ok': True, 'proposta': s['proposta_id'], 'ja_enviada': True}
    if not s['conflito']:
        raise Erro(422, 'Essa sugestão não tem divergência com a base.')
    lead = c.lead(s['lead_id'])
    vend = [r['texto'] for r in c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='humano' "
                                             'ORDER BY id DESC LIMIT 10', (lead['id'],))]
    do_lead = [r['texto'] for r in c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' "
                                                'ORDER BY id DESC LIMIT 3', (lead['id'],))]
    trecho = cerebro.conversa_texto(c, lead['id'], 6)
    justificativa = (f"{s['conflito']}\n\nTrecho da conversa:\n{trecho}")[:1500]
    prod = _produto_do_conflito(c, lead, s['conflito'])
    preco = next((PRECO_TXT.findall(t)[-1].rstrip('.') for t in vend if PRECO_TXT.search(t)), None)  # vend: mais novo primeiro
    if prod and preco:
        promo = next((m.group(1) for t in vend + [s['conflito']] for m in [PROMO_TXT.search(t)] if m), '')
        tipo, d = 'preco', {'produto_id': prod['id'], 'preco_novo': preco.replace('R$', 'R$ ').replace('  ', ' '),
                            'resposta': f"{prod['nome']}: {preco}", 'promocao': f'Promoção {promo}' if promo else '',
                            'validade': '', 'perguntas': []}
    else:
        rasc = next((t for t in vend if not base.tem_bastidor(t)), '')
        tipo, d = 'info', {'campo': 'observacoes', 'resposta': rasc.strip()[:2000], 'perguntas': []}
    d.update({'justificativa': justificativa, 'exemplos': [x[:200] for x in reversed(do_lead)], 'sugestao_id': sid})
    pid = c.db.execute('INSERT INTO propostas(em,tipo,dados,origem,status) VALUES (?,?,?,?,?)',
                       (iso(c.agora()), tipo, json.dumps(d, ensure_ascii=False), 'vendedor', 'nova')).lastrowid
    c.db.execute('UPDATE sugestoes SET proposta_id=? WHERE id=?', (pid, sid))
    return {'ok': True, 'proposta': pid}


# ---------- aprendizado ----------
def similaridade(a, b):
    return round(difflib.SequenceMatcher(None, normalizar(a), normalizar(b)).ratio(), 3)


def registrar_resposta(c, ch, colab, texto, sugestao_id=None):
    """Antes de gravar a mensagem humana: liga a resposta às mensagens do lead pendentes e à sugestão."""
    sug = None
    if sugestao_id is not None:
        try:
            sugestao_id = int(sugestao_id)
        except (TypeError, ValueError):
            raise Erro(422, 'sugestao_id inválido')
        sug = c.db.execute('SELECT * FROM sugestoes WHERE id=? AND chamado_id=?', (sugestao_id, ch['id'])).fetchone()
        if not sug or not sug['texto']:
            raise Erro(422, 'sugestao_id inválido')
    ult = c.db.execute("SELECT MAX(id) FROM mensagens WHERE chamado_id=? AND de='humano'", (ch['id'],)).fetchone()[0]
    msgs = [r['texto'] for r in c.db.execute("SELECT texto FROM mensagens WHERE chamado_id=? AND de='lead' AND id>? "
                                             'ORDER BY id', (ch['id'], ult or 0))]
    livre_sug = None if sug else c.db.execute(
        "SELECT * FROM sugestoes WHERE chamado_id=? AND status='pronta' ORDER BY id DESC LIMIT 1", (ch['id'],)).fetchone()
    # sugestões que estavam na mesa: a usada vira 'usada', as outras 'ignorada' (botões do Telegram saem)
    for s in c.db.execute("SELECT * FROM sugestoes WHERE chamado_id=? AND status='pronta'", (ch['id'],)).fetchall():
        usada = sug is not None and s['id'] == sug['id']
        c.db.execute('UPDATE sugestoes SET status=? WHERE id=?', ('usada' if usada else 'ignorada', s['id']))
        if s['tg_ref']:
            resto = [[tg.bt(BT_BASE, f"sb:{s['id']}")]] if s['conflito'] and not s['proposta_id'] else None
            aviso = f"\n\n⚠️ {s['conflito']}" if s['conflito'] else ''
            tg.editar(c, s['tg_ref'], (f'✅ Enviada: {texto}' if usada else f"💡 Sugestão (não usada): {s['texto']}")
                      + aviso, resto)
    if not msgs:
        return None
    if sug is not None:
        origem = 'sugestao_ok' if texto.strip() == (sug['texto'] or '').strip() else 'sugestao_editada'
        s_txt = sug['texto']
    else:
        origem, s_txt = 'livre', (livre_sug['texto'] if livre_sug else None)
    return c.db.execute('INSERT INTO aprendizado(em,colaborador,lead_id,chamado_id,msg_lead,sugestao_id,sugestao,'
                        'enviado,origem,distancia) VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (iso(c.agora()), colab or ch['dono'], ch['lead_id'], ch['id'], '\n'.join(msgs)[:2000],
                         sug['id'] if sug else (livre_sug['id'] if livre_sug else None), s_txt, texto[:2000], origem,
                         similaridade(s_txt, texto) if s_txt else None)).lastrowid


def _filtro(q):
    sql, args = ' WHERE 1=1', []
    if q.get('de'):
        sql += ' AND substr(em,1,10)>=?'
        args.append(str(q['de'])[:10])
    if q.get('ate'):
        sql += ' AND substr(em,1,10)<=?'
        args.append(str(q['ate'])[:10])
    if q.get('colaborador'):
        sql += ' AND colaborador=?'
        args.append(q['colaborador'])
    if q.get('origem'):
        if q['origem'] not in ORIGENS:
            raise Erro(422, 'origem inválida')
        sql += ' AND origem=?'
        args.append(q['origem'])
    return sql, args


def contadores(itens):
    n = {o: sum(1 for i in itens if i['origem'] == o) for o in ORIGENS}
    ign = sum(1 for i in itens if i['origem'] == 'livre' and i['sugestao'])
    com = n['sugestao_ok'] + n['sugestao_editada'] + ign
    pct = (lambda x: round(100 * x / com, 1) if com else 0)
    return {'total': len(itens), **n, 'ignoradas': ign, 'com_sugestao': com, 'pct_ok': pct(n['sugestao_ok']),
            'pct_editadas': pct(n['sugestao_editada']), 'pct_ignoradas': pct(ign)}


def listar(c, q):
    sql, args = _filtro(q)
    itens = [dict(r) for r in c.db.execute('SELECT * FROM aprendizado' + sql + ' ORDER BY id DESC LIMIT 500', args)]
    for i in itens:
        i['colaborador_nome'] = c.nome_colab(i['colaborador'])
    return {'itens': itens, 'contadores': contadores(itens), 'periodo': periodo(c)}


# ---------- propostas ----------
def periodo(c):
    a = c.cfg.get('aprendizado')
    p = a.get('periodo') if isinstance(a, dict) else None
    return p if p in PERIODOS else 'semanal'


CHAVES = ('perguntas', 'resposta', 'campo', 'faq_id', 'justificativa', 'exemplos', 'produto_id', 'preco_novo',
          'promocao', 'validade', 'sugestao_id', 'nome', 'palavras', 'horarios')
TIPOS_PROP = ('faq', 'info', 'correcao', 'preco', 'produto', 'horario')
HHMM = re.compile(r'([01]\d|2[0-3]):[0-5]\d')
DIAS_ORDEM = ('seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom')
PRECO_OK = re.compile(r'R\$\s?\d[\d.]*(,\d{1,2})?')
DATA_OK = re.compile(r'\d{4}-\d{2}-\d{2}')


def _proposta_json(r, c=None):
    d = json.loads(r['dados'])
    out = {'id': r['id'], 'em': r['em'], 'tipo': r['tipo'], 'origem': r['origem'], 'status': r['status'],
           'perguntas': d.get('perguntas') or [], 'resposta': d.get('resposta') or '', 'campo': d.get('campo'),
           'faq_id': d.get('faq_id'), 'justificativa': d.get('justificativa') or '', 'exemplos': d.get('exemplos') or [],
           'produto_id': d.get('produto_id'), 'preco_novo': d.get('preco_novo') or '',
           'promocao': d.get('promocao') or '', 'validade': d.get('validade') or '', 'sugestao_id': d.get('sugestao_id'),
           'nome': d.get('nome') or '', 'palavras': d.get('palavras') or [], 'horarios': d.get('horarios') or {}}
    if c is not None:
        out['atual'] = _atual(c, out)
        out['destino'] = destino(c, out)
    return out


def _fmt_horarios(h):
    return '; '.join(f"{d} {' e '.join(f'{a}–{b}' for a, b in h[d]) or 'fechado'}" for d in DIAS_ORDEM if d in h) or '—'


def destino(c, p):
    """Onde a incorporação grava, em palavras: 'Cadastros → Produtos → Plano anual → preço: R$ 1.200 → R$ 670'."""
    t = p['tipo']
    if t == 'preco':
        prod = c.produto(p.get('produto_id')) if p.get('produto_id') else None
        if not prod:
            return 'Cadastros → Produtos → (produto não existe mais)'
        if p.get('promocao') or p.get('validade'):
            return (f"Cadastros → Produtos → {prod['nome']} → preço promocional: {prod.get('preco_promocao') or '—'} → "
                    f"{p.get('preco_novo')} ({p.get('promocao') or 'promoção'}{' até ' + p['validade'] if p.get('validade') else ''}); "
                    f"preço normal {prod.get('preco') or '—'} fica")
        return f"Cadastros → Produtos → {prod['nome']} → preço: {prod.get('preco') or '—'} → {p.get('preco_novo')}"
    if t == 'produto':
        return f"Cadastros → Produtos → novo: {p.get('nome')} ({p.get('preco_novo') or 'sem preço'})"
    if t == 'horario':
        hor = c.cfg.get('horarios') or {}
        return (f"Cadastros → Horários: {_fmt_horarios({d: hor.get(d) or [] for d in p.get('horarios') or {}})} → "
                f"{_fmt_horarios(p.get('horarios') or {})}")
    if t == 'info':
        return f"Base de conhecimento → Informações → {base.ROTULOS.get(p.get('campo'), p.get('campo'))} (acrescenta uma linha)"
    if t == 'correcao':
        return f"Base de conhecimento → FAQ → {p.get('faq_id')} (troca a resposta)"
    return 'Base de conhecimento → FAQ → item novo'


def _atual(c, p):
    """O que está na base hoje no alvo da proposta (para a prévia do gestor)."""
    if p['tipo'] == 'info':
        return base.campo(c, p['campo']) if p.get('campo') in base.CAMPOS else ''
    if p['tipo'] == 'correcao':
        f = next((f for f in c.cfg.get('faq') or [] if f.get('id') == p.get('faq_id')), None)
        return (f or {}).get('resposta') or ''
    if p['tipo'] == 'preco':
        prod = c.produto(p.get('produto_id')) if p.get('produto_id') else None
        return f"{prod['nome']}: {base.preco_vigente(c, prod) or 'sem preço'}" if prod else ''
    if p['tipo'] == 'horario':
        return base.texto_horario(c)
    return ''


def propostas(c, q=None):
    q = q or {}
    sql, args = 'SELECT * FROM propostas', []
    if q.get('status'):
        sql += ' WHERE status=?'
        args.append(q['status'])
    return [_proposta_json(r, c) for r in c.db.execute(sql + ' ORDER BY id DESC LIMIT 200', args)]


def _registros(c, de, ate):
    return [dict(r) for r in c.db.execute('SELECT * FROM aprendizado WHERE em>=? AND em<=? ORDER BY id LIMIT 300',
                                          (de, ate))]


INSTR_PROP = (
    'Você ajuda o gestor de {nome} a melhorar a base de conhecimento do atendimento. Leia os registros reais '
    '(mensagem do cliente, sugestão da IA, o que o vendedor mandou) e proponha itens novos de FAQ, informações do '
    'negócio, correções de respostas do FAQ ou preços, usando só fatos que os vendedores realmente escreveram.\n'
    'REGRA DURA: "resposta" é o texto FINAL que vai para a base e que o atendente dirá ao cliente — factual, voltado '
    'ao cliente, sem bastidores (nada de "o vendedor informou", "a base diz", "confirmar com a equipe", "segundo o '
    'vendedor"). O porquê, as dúvidas e as divergências vão SÓ em "justificativa" (para o gestor).\n'
    'Grave no CAMPO ESTRUTURADO certo: preço diferente do produto cadastrado → tipo "preco"; produto que não existe '
    'no cadastro → tipo "produto"; horário de atendimento → tipo "horario" (janelas por dia); endereço, pagamento, '
    'entrega, garantia, site → tipo "info" com o campo; pergunta recorrente → "faq" (ou "correcao" do item existente).\n'
    'Responda SOMENTE com JSON no formato {{"propostas": [{{"tipo": "faq|info|correcao|preco|produto|horario", "perguntas": ["..."], '
    '"resposta": "...", "campo": "endereco|pagamento|entrega|garantia|site|observacoes '
    '(só no tipo info)", "nome": "nome do produto novo (só no tipo produto)", "palavras": ["palavras que indicam '
    'interesse (só no tipo produto)"], "horarios": {{"seg": [["08:00", "18:00"]], "dom": []}} (só no tipo horario; '
    'só os dias que mudam; [] = fechado), "faq_id": "id do item do FAQ (só no tipo correcao)", "produto_id": "id do produto (só no '
    'tipo preco)", "preco_novo": "R$ ... (tipos preco e produto)", "promocao": "nome curto da promoção, opcional (só no '
    'tipo preco)", "validade": "AAAA-MM-DD, opcional (só no tipo preco)", "justificativa": "...", '
    '"exemplos": ["mensagens do cliente"]}}]}}. No máximo 8 propostas; lista vazia se nada valer a pena.')


def preparar(c, de, ate):
    regs = _registros(c, de, ate)
    if not regs:
        return None
    ids = '\n'.join(f"- {f.get('id')}: {' / '.join(f.get('perguntas') or [])}" for f in c.cfg.get('faq') or [])
    prods = '\n'.join(f"- {p.get('id')}: {p.get('nome')} — {base.preco_vigente(c, p) or 'sem preço'}"
                      for p in c.cfg.get('produtos') or [])
    linhas = [f"[{r['origem']}] cliente: {r['msg_lead']}\n  sugestão da IA: {r['sugestao'] or '—'}\n"
              f"  vendedor mandou: {r['enviado']}" for r in regs[-80:]]
    usuario = (f"IDs do FAQ atual:\n{ids or '(vazio)'}\n\nProdutos (id: nome — preço):\n{prods or '(nenhum)'}\n\n"
               f"Registros do período {de} a {ate}:\n") + '\n'.join(linhas)
    return INSTR_PROP.format(nome=c.cfg.get('nome') or 'uma empresa'), usuario, base.texto_base(c)


def _ler_json(texto):
    d = cerebro.ler_json(texto)
    itens = d.get('propostas') if isinstance(d, dict) else None
    return itens if isinstance(itens, list) else None


def _texto(v, n):
    return v.strip()[:n] if isinstance(v, str) else ''


def _limpar_preco(c, p):
    prod = c.produto(p.get('produto_id')) if isinstance(p.get('produto_id'), str) else None
    preco = _texto(p.get('preco_novo'), 60).rstrip('.')
    if not prod or not PRECO_OK.fullmatch(preco):
        return None
    val = _texto(p.get('validade'), 10)
    d = {'produto_id': prod['id'], 'preco_novo': preco, 'resposta': f"{prod['nome']}: {preco}",
         'promocao': _texto(p.get('promocao'), 80), 'validade': val if DATA_OK.fullmatch(val) else '',
         'justificativa': _texto(p.get('justificativa'), 500), 'perguntas': [],
         'exemplos': [str(x)[:200] for x in (p.get('exemplos') or []) if isinstance(x, str)][:5]}
    if tem_bastidor_lista(d['promocao']):
        d['promocao'] = ''
    return 'preco', d


def _limpar_produto(c, p):
    nome = _texto(p.get('nome'), 120)
    preco = _texto(p.get('preco_novo'), 60).rstrip('.')
    if not nome or base.tem_bastidor(nome) or any(normalizar(x.get('nome')) == normalizar(nome)
                                                  for x in c.cfg.get('produtos') or []):
        return None
    if preco and not PRECO_OK.fullmatch(preco):
        return None
    pal = [str(x).strip()[:60] for x in (p.get('palavras') or []) if isinstance(x, str) and x.strip()][:10]
    return 'produto', {'nome': nome, 'palavras': pal or [nome.lower()], 'preco_novo': preco,
                       'resposta': f'{nome}: {preco}' if preco else nome, 'perguntas': [],
                       'justificativa': _texto(p.get('justificativa'), 500),
                       'exemplos': [str(x)[:200] for x in (p.get('exemplos') or []) if isinstance(x, str)][:5]}


def horarios_validos(h):
    """{dia: [[ini, fim], ...]} válido (dias conhecidos, HH:MM, ini < fim) ou None."""
    if not isinstance(h, dict) or not h:
        return None
    out = {}
    for d, js in h.items():
        if d not in DIAS_ORDEM or not isinstance(js, list):
            return None
        jan = []
        for j in js:
            if (not isinstance(j, list) or len(j) != 2 or not all(isinstance(x, str) and HHMM.fullmatch(x) for x in j)
                    or j[0] >= j[1]):
                return None
            jan.append([j[0], j[1]])
        out[d] = jan
    return out


def _limpar_horario(c, p):
    h = horarios_validos(p.get('horarios'))
    if not h:
        return None
    resp = _texto(p.get('resposta'), 500)
    if base.tem_bastidor(resp):
        resp = ''
    return 'horario', {'horarios': h, 'resposta': resp or _fmt_horarios(h), 'perguntas': [],
                       'justificativa': _texto(p.get('justificativa'), 500),
                       'exemplos': [str(x)[:200] for x in (p.get('exemplos') or []) if isinstance(x, str)][:5]}


def tem_bastidor_lista(*textos):
    return any(base.tem_bastidor(t) for t in textos if t)


def _limpar(c, p):
    """Proposta do LLM validada (ou None). `resposta` com marca de bastidor (recado interno) é descartada."""
    if not isinstance(p, dict) or p.get('tipo') not in TIPOS_PROP:
        return None
    if p['tipo'] == 'preco':
        return _limpar_preco(c, p)
    if p['tipo'] == 'produto':
        return _limpar_produto(c, p)
    if p['tipo'] == 'horario':
        return _limpar_horario(c, p)
    resp = p.get('resposta')
    if not isinstance(resp, str) or not resp.strip():
        return None
    if base.tem_bastidor(resp):
        log(f"proposta descartada: resposta com bastidor ({p['tipo']})")
        return None
    perg = [str(x).strip()[:200] for x in (p.get('perguntas') or []) if isinstance(x, str) and x.strip()][:5]
    d = {'perguntas': perg, 'resposta': resp.strip()[:2000],
         'justificativa': str(p.get('justificativa') or '')[:500],
         'exemplos': [str(x)[:200] for x in (p.get('exemplos') or []) if isinstance(x, str)][:5]}
    if p['tipo'] == 'faq' and not perg:
        return None
    if p['tipo'] == 'info':
        if p.get('campo') not in base.CAMPOS:
            return None
        d['campo'] = p['campo']
    if p['tipo'] == 'correcao':
        if not any(f.get('id') == p.get('faq_id') for f in c.cfg.get('faq') or []):
            return None
        d['faq_id'] = p['faq_id']
    return p['tipo'], d


def por_regras(c, regs):
    """Agrupa respostas livres/editadas parecidas (≥ 0,8) com 2+ ocorrências → proposta de FAQ."""
    grupos = []
    for r in regs:
        if (r['origem'] not in ('livre', 'sugestao_editada') or not (r['enviado'] or '').strip()
                or base.tem_bastidor(r['enviado'])):
            continue
        for g in grupos:
            if similaridade(g[0]['enviado'], r['enviado']) >= 0.8:
                g.append(r)
                break
        else:
            grupos.append([r])
    out = []
    for g in grupos:
        if len(g) < 2:
            continue
        contagem = {}
        for r in g:
            contagem[r['enviado'].strip()] = contagem.get(r['enviado'].strip(), 0) + 1
        resposta = max(contagem, key=contagem.get)
        perguntas = []
        for r in g:
            for linha in (r['msg_lead'] or '').split('\n'):
                if linha.strip() and linha.strip()[:200] not in perguntas:
                    perguntas.append(linha.strip()[:200])
        out.append(('faq', {'perguntas': perguntas[:5], 'resposta': resposta[:2000],
                            'justificativa': f'{len(g)} respostas parecidas dos vendedores no período',
                            'exemplos': perguntas[:5]}))
    return out


def gravar(c, regs, texto):
    itens, origem = None, 'regras'
    lidos = _ler_json(texto) if texto else None
    if lidos is not None:
        itens = [x for x in (_limpar(c, p) for p in lidos[:8]) if x]
        origem = 'cerebro'
    if itens is None:
        itens = por_regras(c, regs)
    existentes = {normalizar(_proposta_json(r)['resposta']) for r in
                  c.db.execute("SELECT * FROM propostas WHERE status='nova'")}
    return _inserir(c, itens, origem, existentes)


def _inserir(c, itens, origem, existentes):
    faq_resps = {normalizar(f.get('resposta') or '') for f in c.cfg.get('faq') or []}
    criadas = []
    for tipo, d in itens:
        n = normalizar(d['resposta'])
        if n in existentes or (tipo == 'faq' and n in faq_resps):
            continue
        existentes.add(n)
        pid = c.db.execute('INSERT INTO propostas(em,tipo,dados,origem,status) VALUES (?,?,?,?,?)',
                           (iso(c.agora()), tipo, json.dumps(d, ensure_ascii=False), origem, 'nova')).lastrowid
        criadas.append(pid)
    return criadas


def gerar(c, de=None, ate=None):
    """Botão 'Gerar propostas agora' (o cérebro roda fora do lock por c.pronto)."""
    ate = ate or iso(c.agora())
    de = de or iso(c.agora() - timedelta(days=7))
    if len(de) == 10:
        de += 'T00:00'
    if len(ate) == 10:
        ate += 'T23:59'
    prep = preparar(c, de, ate)
    if not prep:
        return {'criadas': 0, 'propostas': []}
    texto = (cerebro.perguntar(c, prep[0], prep[1], prep[2], papel='curadoria', limpar=False)
             if cerebro.ligado(c, 'curadoria') else None)
    ids = gravar(c, _registros(c, de, ate), texto)
    todas = {p['id']: p for p in propostas(c)}
    return {'criadas': len(ids), 'propostas': [todas[i] for i in ids if i in todas]}


def periodico(c):
    """Tarefa de tempo: gera quando o período venceu. Com LLM, só marca o pedido para o Trabalhador."""
    dias = PERIODOS.get(periodo(c))
    if not dias:
        return 0
    ultima = c.meta('propostas_ultima')
    if not ultima:
        ultima = c.db.execute('SELECT MIN(em) FROM aprendizado').fetchone()[0]
    if not ultima or c.agora() < parse(ultima) + timedelta(days=dias):
        return 0
    agora = iso(c.agora())
    c.meta('propostas_ultima', agora, gravar=True)
    if cerebro.ligado(c, 'curadoria'):
        c.meta('propostas_pedido', json.dumps({'de': ultima, 'ate': agora}), gravar=True)
        c.enfileirar('sug', 0)
        return 1
    gravar(c, _registros(c, ultima, agora), None)
    return 1


def incorporar(c, pid, b):
    """Grava a proposta (com o texto que o gestor revisou) na base. info ACRESCENTA uma linha ao campo; preco
    atualiza o produto (com promoção: preco_promocao/promocao/promocao_ate, o preço normal fica)."""
    from . import gestao
    r = c.db.execute('SELECT * FROM propostas WHERE id=?', (pid,)).fetchone()
    if not r:
        raise Erro(404, 'Proposta inexistente')
    if r['status'] != 'nova':
        raise Erro(409, 'Proposta já tratada')
    p = _proposta_json(r)
    b = b if isinstance(b, dict) else {}
    for k in ('resposta', 'preco_novo', 'promocao', 'validade'):
        if k in b and b[k] is not None and not isinstance(b[k], str):
            raise Erro(422, f'{k} deve ser texto')
    if 'resposta' in b and p['tipo'] != 'preco':
        if not b['resposta'] or not b['resposta'].strip():
            raise Erro(422, 'resposta obrigatória')
        p['resposta'] = b['resposta'].strip()
    if 'perguntas' in b:
        if not isinstance(b['perguntas'], list) or not all(isinstance(x, str) for x in b['perguntas']):
            raise Erro(422, 'perguntas deve ser lista de textos')
        p['perguntas'] = [x.strip() for x in b['perguntas'] if x.strip()]
    for k in ('preco_novo', 'promocao', 'validade', 'nome'):
        if k in b and b[k] is not None:
            if not isinstance(b[k], str):
                raise Erro(422, f'{k} deve ser texto')
            p[k] = b[k].strip()
    if 'palavras' in b:
        if not isinstance(b['palavras'], list) or not all(isinstance(x, str) for x in b['palavras']):
            raise Erro(422, 'palavras deve ser lista de textos')
        p['palavras'] = [x.strip() for x in b['palavras'] if x.strip()]
    if 'horarios' in b:
        p['horarios'] = b['horarios']
    if p['tipo'] in ('produto', 'horario'):
        return _incorporar_cadastro(c, pid, p, b)
    if p['tipo'] != 'preco' and not (p['resposta'] or '').strip():
        raise Erro(422, 'resposta obrigatória')
    if p['tipo'] != 'preco' and base.tem_bastidor(p['resposta']):
        raise Erro(422, 'O texto parece um recado interno ("o vendedor informou", "a base diz"…). Escreva a '
                        'resposta como ela deve aparecer para o cliente.')
    faq = [dict(f) for f in c.cfg.get('faq') or []]
    if p['tipo'] == 'faq':
        if not p['perguntas']:
            raise Erro(422, 'perguntas obrigatórias')
        ident, n = f'apr-{pid}', 1
        while any(f.get('id') == ident for f in faq):
            n += 1
            ident = f'apr-{pid}-{n}'
        faq.append({'id': ident, 'perguntas': p['perguntas'], 'resposta': p['resposta']})
        gestao.gravar_config(c, {'faq': faq})
    elif p['tipo'] == 'correcao':
        alvo = next((f for f in faq if f.get('id') == p['faq_id']), None)
        if not alvo:
            raise Erro(422, 'faq_id não existe mais')
        alvo['resposta'] = p['resposta']
        alvo['perguntas'] = list(alvo.get('perguntas') or []) + [x for x in p['perguntas']
                                                                 if x not in (alvo.get('perguntas') or [])]
        gestao.gravar_config(c, {'faq': faq})
    elif p['tipo'] == 'preco':
        if not PRECO_OK.fullmatch(p['preco_novo'] or ''):
            raise Erro(422, 'preco_novo no formato "R$ 670" ou "R$ 1.200,00"')
        if p['validade'] and not DATA_OK.fullmatch(p['validade']):
            raise Erro(422, 'validade no formato AAAA-MM-DD')
        prods = [dict(x) for x in c.cfg.get('produtos') or []]
        alvo = next((x for x in prods if x.get('id') == p['produto_id']), None)
        if not alvo:
            raise Erro(422, 'produto não existe mais')
        if p['promocao'] or p['validade']:
            alvo['preco_promocao'] = p['preco_novo']
            alvo['promocao'] = p['promocao']
            alvo['promocao_ate'] = p['validade']
        else:
            alvo['preco'] = p['preco_novo']
            for k in ('preco_promocao', 'promocao', 'promocao_ate'):
                alvo.pop(k, None)
        p['resposta'] = f"{alvo['nome']}: {p['preco_novo']}"
        gestao.gravar_config(c, {'produtos': prods})
    else:
        info = dict(base.info(c))
        atual = (info.get(p['campo']) or '').strip()
        linhas = [x.strip() for x in atual.splitlines() if x.strip()]
        if normalizar(p['resposta']) not in {normalizar(x) for x in linhas} and normalizar(p['resposta']) != normalizar(atual):
            novo = (atual + '\n' + p['resposta']) if atual else p['resposta']
            if len(novo) > 2000:
                raise Erro(422, f"info.{p['campo']} passaria de 2000 caracteres; encurte o texto ou edite o campo "
                                'na Base de conhecimento')
            info[p['campo']] = novo
            gestao.gravar_config(c, {'info': info})
    return _marcar(c, pid, p)


def _marcar(c, pid, p):
    c.db.execute("UPDATE propostas SET status='incorporada', dados=? WHERE id=?",
                 (json.dumps({k: p.get(k) for k in CHAVES}, ensure_ascii=False), pid))
    return {'ok': True, 'proposta': _proposta_json(c.db.execute('SELECT * FROM propostas WHERE id=?', (pid,)).fetchone(), c)}


def _incorporar_cadastro(c, pid, p, b):
    """produto → produtos[] (id, nome, palavras, preco); horario → horarios (só os dias da proposta) e, se havia
    texto em info.horario_atendimento, troca pelo texto da proposta (o texto livre manda sobre os horários)."""
    from . import gestao
    if p['tipo'] == 'produto':
        if not p['nome'] or base.tem_bastidor(p['nome']):
            raise Erro(422, 'nome do produto obrigatório')
        if p['preco_novo'] and not PRECO_OK.fullmatch(p['preco_novo']):
            raise Erro(422, 'preco_novo no formato "R$ 670" ou "R$ 1.200,00"')
        prods = [dict(x) for x in c.cfg.get('produtos') or []]
        if any(normalizar(x.get('nome')) == normalizar(p['nome']) for x in prods):
            raise Erro(409, 'Já existe um produto com esse nome')
        ident = re.sub(r'[^a-z0-9]+', '-', normalizar(p['nome'])).strip('-') or 'produto'
        n, base_id = 2, ident
        while any(x.get('id') == ident for x in prods):
            ident, n = f'{base_id}-{n}', n + 1
        novo = {'id': ident, 'nome': p['nome'], 'palavras': p['palavras'] or [p['nome'].lower()]}
        if p['preco_novo']:
            novo['preco'] = p['preco_novo']
        prods.append(novo)
        p['produto_id'] = ident
        gestao.gravar_config(c, {'produtos': prods})
        return _marcar(c, pid, p)
    h = horarios_validos(p['horarios'])
    if not h:
        raise Erro(422, 'horarios: {"seg": [["08:00", "18:00"]], ...} com HH:MM e início antes do fim')
    if 'resposta' in b and base.tem_bastidor(p['resposta']):
        raise Erro(422, 'O texto parece um recado interno. Escreva como o cliente deve ler.')
    hor = dict(c.cfg.get('horarios') or {})
    hor.update(h)
    novo = {'horarios': hor}
    if base.campo(c, 'horario_atendimento'):
        info = dict(base.info(c))
        info['horario_atendimento'] = p['resposta'] if 'resposta' in b else ''
        novo['info'] = info
    gestao.gravar_config(c, novo)
    return _marcar(c, pid, p)


def descartar(c, pid):
    r = c.db.execute('SELECT * FROM propostas WHERE id=?', (pid,)).fetchone()
    if not r:
        raise Erro(404, 'Proposta inexistente')
    if r['status'] != 'nova':
        raise Erro(409, 'Proposta já tratada')
    c.db.execute("UPDATE propostas SET status='descartada' WHERE id=?", (pid,))
    return {'ok': True}


# ---------- trabalhador em segundo plano ----------
class Trabalhador:
    """Gera as sugestões e as propostas periódicas com o cérebro LLM, fora do lock."""

    def __init__(self, app):
        self.app = app
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self._rodar, daemon=True)

    def iniciar(self):
        self.app.acordar['sug'].set()
        self.thread.start()
        return self

    def encerrar(self):
        self.parar.set()
        self.app.acordar['sug'].set()
        self.thread.join(1)

    def _rodar(self):
        ev = self.app.acordar['sug']
        while not self.parar.is_set():
            ev.wait(10)
            ev.clear()
            if self.parar.is_set():
                break
            try:
                self.rodada()
            except Exception as e:
                log(f'sugestões: {type(e).__name__}: {e}')

    def rodada(self):
        app = self.app
        ids = app.executar(lambda: [r['id'] for r in app.db.execute(
            "SELECT id FROM sugestoes WHERE status='gerando' ORDER BY id LIMIT 20")])
        for sid in ids:
            if self.parar.is_set():
                return
            try:
                ctx = app.executar(lambda: contexto(app, sid))
                texto = (cerebro.perguntar(app, ctx[0], ctx[1], ctx[2], formato=SUG_SCHEMA, limpar=False)
                         if ctx else None)
                if ctx:
                    app.executar(lambda: concluir(app, sid, texto))
            except Exception as e:  # uma sugestão com problema não trava as próximas
                log(f'sugestão {sid}: {type(e).__name__}: {e}')
                app.executar(lambda: app.db.execute("UPDATE sugestoes SET status='erro' WHERE id=?", (sid,)))
        pedido = app.executar(lambda: app.meta('propostas_pedido'))
        if pedido:
            try:
                p = json.loads(pedido)
            except ValueError:
                p = None
            prep = app.executar(lambda: preparar(app, p['de'], p['ate'])) if p else None
            texto = (cerebro.perguntar(app, prep[0], prep[1], prep[2], papel='curadoria', limpar=False)
                     if prep and cerebro.ligado(app, 'curadoria') else None)

            def fim():
                if p:
                    gravar(app, _registros(app, p['de'], p['ate']), texto)
                app.meta('propostas_pedido', None, gravar=True)
            app.executar(fim)
