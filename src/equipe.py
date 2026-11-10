"""Status da equipe, ordem de vez e painel fixo do grupo (seções 6 e 8)."""
from .core import Erro, iso, log, minutos, parse, primeiro_nome
from . import telegram as tg

STATUS_MANUAIS = ('livre', 'ocupado', 'fora')


def ordem_de_vez(c):
    """Livres por livre_desde crescente; empate pela ordem do negocio.json."""
    posicao = {m['id']: i for i, m in enumerate(c.cfg.get('equipe', []))}
    livres = [r for r in c.db.execute("SELECT * FROM colaboradores WHERE status='livre'") if r['id'] in posicao]
    return [r['id'] for r in sorted(livres, key=lambda r: (r['livre_desde'] or '', posicao[r['id']]))]


def atendendo_de(c, colab):
    return c.db.execute("SELECT * FROM chamados WHERE dono=? AND status='atendendo' ORDER BY assumido_em, id",
                        (colab,)).fetchall()


def vinculado(c, colab):
    r = c.db.execute('SELECT telegram_id FROM colaboradores WHERE id=?', (colab,)).fetchone()
    return r['telegram_id'] if r and r['telegram_id'] else None


def colab_por_telegram(c, from_id):
    r = c.db.execute('SELECT id FROM colaboradores WHERE telegram_id=?', (str(from_id),)).fetchone()
    return r['id'] if r and c.membro(r['id']) else None


def privado(c, colab, texto, botoes=None, reply=None):
    chat = vinculado(c, colab)
    return tg.enviar(c, chat, texto, botoes, reply) if chat else None


def _definir(c, colab, status):
    agora = iso(c.agora())
    atual = c.colab(colab)
    if status == 'livre' and atual['status'] != 'livre':
        c.db.execute('UPDATE colaboradores SET status=?, livre_desde=?, status_desde=? WHERE id=?',
                     ('livre', agora, agora, colab))
    elif status != atual['status']:
        c.db.execute('UPDATE colaboradores SET status=?, status_desde=? WHERE id=?', (status, agora, colab))
    c.sujo = True


def mudar_status(c, colab, status):
    """Mudança manual (painel, Telegram, gestor)."""
    from . import chamados
    if status not in STATUS_MANUAIS:
        raise Erro(422, 'Status deve ser livre, ocupado ou fora')
    c.colab(colab)
    tem = atendendo_de(c, colab)
    if tem:
        if status == 'fora':
            raise Erro(409, 'Feche seus atendimentos antes de sair')
        _definir(c, colab, 'atendendo')
    else:
        _definir(c, colab, status)
        if status == 'livre':
            chamados.distribuir(c)
    return dados_colab(c, colab)


def ficou_atendendo(c, colab):
    _definir(c, colab, 'atendendo')


def liberar_se_vazio(c, colab):
    """Ao fechar o último atendimento: volta a livre com livre_desde = agora (fim da fila)."""
    from . import chamados
    if not colab or not c.membro(colab):
        return
    if atendendo_de(c, colab):
        return
    agora = iso(c.agora())
    c.db.execute('UPDATE colaboradores SET status=?, livre_desde=?, status_desde=? WHERE id=?',
                 ('livre', agora, agora, colab))
    c.sujo = True
    chamados.distribuir(c)


def dados_colab(c, colab):
    r = c.colab(colab)
    m = c.membro(colab)
    return {'id': colab, 'nome': m['nome'], 'status': r['status'], 'livre_desde': r['livre_desde'],
            'telegram': bool(r['telegram_id'])}


def _min_status(c, r, agora):
    if r['status'] == 'livre':
        return minutos(r['livre_desde'], agora)
    if r['status'] == 'atendendo':
        ch = atendendo_de(c, r['id'])
        if ch:
            return minutos(ch[0]['assumido_em'], agora)
    return minutos(r['status_desde'], agora)


def painel(c):
    agora = c.agora()
    ordem = ordem_de_vez(c)
    proximo = ordem[0] if ordem else None
    equipe = []
    for m in c.cfg.get('equipe', []):
        r = c.db.execute('SELECT * FROM colaboradores WHERE id=?', (m['id'],)).fetchone()
        if not r:
            continue
        equipe.append({'id': m['id'], 'nome': m['nome'], 'status': r['status'], 'livre_desde': r['livre_desde'],
                       'minutos': _min_status(c, r, agora), 'proximo': m['id'] == proximo,
                       'robo_por_mim': bool(r['robo_por_mim'])})
    fila = []
    for ch in c.db.execute("SELECT * FROM chamados WHERE status IN ('aguardando','alerta') ORDER BY aberto_em, id"):
        lead = c.lead(ch['lead_id'])
        fila.append({'id': ch['id'], 'lead': primeiro_nome(lead['nome']), 'lead_id': ch['lead_id'],
                     'prioridade': ch['prioridade'], 'status': ch['status'], 'motivo': ch['motivo'],
                     'minutos': minutos(ch['conta_desde'] or ch['aberto_em'], agora),
                     'ofertado_a': ch['ofertado_a'], 'nota': lead['nota'], 'silencioso': bool(ch['silencioso'])})
    atend = [{'id': ch['id'], 'lead': primeiro_nome(c.lead(ch['lead_id'])['nome']), 'lead_id': ch['lead_id'],
              'dono': ch['dono'], 'minutos': minutos(ch['assumido_em'], agora)}
             for ch in c.db.execute("SELECT * FROM chamados WHERE status='atendendo' ORDER BY assumido_em, id")]
    return {'equipe': equipe, 'fila': fila, 'atendendo': atend}


def texto_painel(c):
    """1.12.8: resumo na 2ª linha e, com gente esperando, a FILA vem antes da equipe (é o que pede ação)."""
    p = painel(c)
    eq = []
    for e in p['equipe']:
        if e['status'] == 'livre':
            eq.append(f"🟢 {e['nome']} livre há {e['minutos']} min" + (' (próxima da vez)' if e['proximo'] else ''))
        elif e['status'] == 'atendendo':
            ch = atendendo_de(c, e['id'])
            quem = primeiro_nome(c.lead(ch[0]['lead_id'])['nome']) if ch else 'lead'
            extra = f' (+{len(ch) - 1})' if len(ch) > 1 else ''
            eq.append(f"🟡 {e['nome']} atendendo {quem} · {e['minutos']} min{extra}")
        elif e['status'] == 'ocupado':
            eq.append(f"🔴 {e['nome']} ocupado")
        else:
            eq.append(f"⚫ {e['nome']} fora")
    fila = ['FILA']
    if not p['fila']:
        fila.append('(vazia)')
    for f in p['fila']:
        icone = '🔥' if f['prioridade'] == 'quente' else '🙋'
        fila.append(f"{icone} {f['lead']} · esperando {f['minutos']} min" +
                    (' ⚠️ sem dono' if f['status'] == 'alerta' else ''))
    conta = lambda st: sum(1 for e in p['equipe'] if e['status'] == st)
    resumo = f"{len(p['fila'])} na fila · {conta('livre')} livre(s) · {conta('atendendo')} atendendo"
    topo = [f"EQUIPE AGORA · {c.agora().strftime('%H:%M')}", resumo, '']
    return '\n'.join(topo + (fila + [''] + eq if p['fila'] else eq + [''] + fila))


def atualizar_painel(c):
    """Nunca derruba a operação que mudou o estado."""
    try:
        _atualizar_painel(c)
    except Exception as e:
        c.sujo = False
        log(f'painel: {type(e).__name__}: {e}')


def _atualizar_painel(c):
    """Agenda o painel (coalescido: só o último texto vale). O despachante cria na primeira vez,
    depois edita; erro na edição → envia novo, guarda o id e tenta fixar."""
    c.sujo = False
    gid = tg.grupo()
    if not tg.configurado() or not gid:
        return
    texto = texto_painel(c)
    pendente = c.db.execute("SELECT 1 FROM tg_saida WHERE chave='painel' AND status='pendente' LIMIT 1").fetchone()
    ref = c.meta('painel_ref')
    if not pendente and ref and ref.split(':', 1)[0] == str(gid) and c.meta('painel_texto') == texto:
        return
    tg.painel(c, gid, texto)


def livre_desde_dt(r):
    return parse(r['livre_desde']) if r and r['livre_desde'] else None
