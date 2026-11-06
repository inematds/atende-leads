"""Sugestão de resposta para a equipe, registro de aprendizado e propostas para a base (seções 7a e 13a).

A sugestão nasce dentro da transação da mensagem do lead (status `gerando` ou já `pronta` por regras); com
cérebro LLM, quem chama o modelo é o Trabalhador, em segundo plano e fora do lock. As propostas periódicas
também saem pelo Trabalhador (a tarefa de tempo só marca o pedido em `meta`).
"""
import difflib
import json
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


def botoes(sid):
    return [[tg.bt('✅ Enviar', f'sg:{sid}:ok'), tg.bt('✏️ Editar', f'sg:{sid}:ed')]]


def publicar(c, sid):
    from .chamados import guardar_msg
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    ref = equipe.privado(c, s['dono'], f"💡 Sugestão: {s['texto']}", botoes(sid))
    if ref:
        guardar_msg(c, ref, s['chamado_id'], f'sg:{sid}')
        c.db.execute('UPDATE sugestoes SET tg_ref=? WHERE id=?', (ref, sid))


INSTR_SUG = (' Você está ajudando um vendedor humano que já atende este cliente: escreva SÓ o texto da próxima '
             'resposta dele, pronta para enviar, sem aspas, sem rótulos e sem comentários.')


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
    return base.instrucoes(c) + INSTR_SUG, usuario, base.texto_base(c)


def concluir(c, sid, texto):
    s = c.db.execute('SELECT * FROM sugestoes WHERE id=?', (sid,)).fetchone()
    if not s or s['status'] != 'gerando':
        return
    origem = 'cerebro'
    texto = (texto or '').strip().strip('"').strip()
    if not texto:
        m = c.db.execute('SELECT texto FROM mensagens WHERE id=?', (s['msg_id'],)).fetchone()
        texto, origem = (base.sugestao_regras(c, m['texto']) if m else None), 'regras'
    if not texto:
        c.db.execute("UPDATE sugestoes SET status='vazia' WHERE id=?", (sid,))
        return
    c.db.execute("UPDATE sugestoes SET texto=?, status='pronta', origem=? WHERE id=?", (texto[:2000], origem, sid))
    publicar(c, sid)


def pronta_do_chamado(c, chamado_id):
    r = c.db.execute("SELECT id, texto, em FROM sugestoes WHERE chamado_id=? AND status='pronta' ORDER BY id DESC "
                     'LIMIT 1', (chamado_id,)).fetchone()
    return dict(r) if r else None


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
            tg.editar(c, s['tg_ref'], f'✅ Enviada: {texto}' if usada else f"💡 Sugestão (não usada): {s['texto']}")
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


def _proposta_json(r):
    d = json.loads(r['dados'])
    return {'id': r['id'], 'em': r['em'], 'tipo': r['tipo'], 'origem': r['origem'], 'status': r['status'],
            'perguntas': d.get('perguntas') or [], 'resposta': d.get('resposta') or '', 'campo': d.get('campo'),
            'faq_id': d.get('faq_id'), 'justificativa': d.get('justificativa') or '', 'exemplos': d.get('exemplos') or []}


def propostas(c, q=None):
    q = q or {}
    sql, args = 'SELECT * FROM propostas', []
    if q.get('status'):
        sql += ' WHERE status=?'
        args.append(q['status'])
    return [_proposta_json(r) for r in c.db.execute(sql + ' ORDER BY id DESC LIMIT 200', args)]


def _registros(c, de, ate):
    return [dict(r) for r in c.db.execute('SELECT * FROM aprendizado WHERE em>=? AND em<=? ORDER BY id LIMIT 300',
                                          (de, ate))]


INSTR_PROP = (
    'Você ajuda o gestor de {nome} a melhorar a base de conhecimento do atendimento. Leia os registros reais '
    '(mensagem do cliente, sugestão da IA, o que o vendedor mandou) e proponha itens novos de FAQ, informações do '
    'negócio ou correções de respostas do FAQ, usando só fatos que os vendedores realmente escreveram. Responda '
    'SOMENTE com JSON no formato {{"propostas": [{{"tipo": "faq|info|correcao", "perguntas": ["..."], '
    '"resposta": "...", "campo": "endereco|pagamento|entrega|garantia|site|horario_atendimento|observacoes '
    '(só no tipo info)", "faq_id": "id do item do FAQ (só no tipo correcao)", "justificativa": "...", '
    '"exemplos": ["mensagens do cliente"]}}]}}. No máximo 8 propostas; lista vazia se nada valer a pena.')


def preparar(c, de, ate):
    regs = _registros(c, de, ate)
    if not regs:
        return None
    ids = '\n'.join(f"- {f.get('id')}: {' / '.join(f.get('perguntas') or [])}" for f in c.cfg.get('faq') or [])
    linhas = [f"[{r['origem']}] cliente: {r['msg_lead']}\n  sugestão da IA: {r['sugestao'] or '—'}\n"
              f"  vendedor mandou: {r['enviado']}" for r in regs[-80:]]
    usuario = f"IDs do FAQ atual:\n{ids or '(vazio)'}\n\nRegistros do período {de} a {ate}:\n" + '\n'.join(linhas)
    return INSTR_PROP.format(nome=c.cfg.get('nome') or 'uma empresa'), usuario, base.texto_base(c)


def _ler_json(texto):
    if not isinstance(texto, str) or '{' not in texto:
        return None
    try:
        d = json.loads(texto[texto.index('{'):texto.rindex('}') + 1])
    except ValueError:
        return None
    itens = d.get('propostas') if isinstance(d, dict) else None
    return itens if isinstance(itens, list) else None


def _limpar(c, p):
    """Proposta do LLM validada (ou None)."""
    if not isinstance(p, dict) or p.get('tipo') not in ('faq', 'info', 'correcao'):
        return None
    resp = p.get('resposta')
    if not isinstance(resp, str) or not resp.strip():
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
        if r['origem'] not in ('livre', 'sugestao_editada') or not (r['enviado'] or '').strip():
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
    texto = cerebro.perguntar(c, prep[0], prep[1], prep[2]) if cerebro.ligado(c) else None
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
    if cerebro.ligado(c):
        c.meta('propostas_pedido', json.dumps({'de': ultima, 'ate': agora}), gravar=True)
        c.enfileirar('sug', 0)
        return 1
    gravar(c, _registros(c, ultima, agora), None)
    return 1


def incorporar(c, pid, b):
    from . import gestao
    r = c.db.execute('SELECT * FROM propostas WHERE id=?', (pid,)).fetchone()
    if not r:
        raise Erro(404, 'Proposta inexistente')
    if r['status'] != 'nova':
        raise Erro(409, 'Proposta já tratada')
    p = _proposta_json(r)
    b = b if isinstance(b, dict) else {}
    if 'resposta' in b:
        if not isinstance(b['resposta'], str) or not b['resposta'].strip():
            raise Erro(422, 'resposta obrigatória')
        p['resposta'] = b['resposta'].strip()
    if 'perguntas' in b:
        if not isinstance(b['perguntas'], list) or not all(isinstance(x, str) for x in b['perguntas']):
            raise Erro(422, 'perguntas deve ser lista de textos')
        p['perguntas'] = [x.strip() for x in b['perguntas'] if x.strip()]
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
    else:
        info = dict(base.info(c))
        info[p['campo']] = p['resposta']
        gestao.gravar_config(c, {'info': info})
    c.db.execute("UPDATE propostas SET status='incorporada', dados=? WHERE id=?",
                 (json.dumps({k: p[k] for k in ('perguntas', 'resposta', 'campo', 'faq_id', 'justificativa',
                                               'exemplos')}, ensure_ascii=False), pid))
    return {'ok': True, 'proposta': _proposta_json(c.db.execute('SELECT * FROM propostas WHERE id=?', (pid,)).fetchone())}


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
                texto = cerebro.perguntar(app, ctx[0], ctx[1], ctx[2]) if ctx else None
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
            texto = cerebro.perguntar(app, prep[0], prep[1], prep[2]) if prep else None

            def fim():
                if p:
                    gravar(app, _registros(app, p['de'], p['ate']), texto)
                app.meta('propostas_pedido', None, gravar=True)
            app.executar(fim)
