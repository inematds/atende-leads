"""Meus contatos (seção 12), ordem por nível e tempos do lead (seções 12 e 13)."""
from .core import minutos, parse
from . import chamados, conversa

NIVEL = {'em_atendimento': 0, 'retornar': 1, 'negociando': 2, 'novo': 3, 'ganho': 4, 'perdido': 5, 'invalido': 6}


def apagado(lead):
    return str(lead['telefone'] or '').startswith('apagado-')


def metricas(c, lead_id):
    """Tempo de conversa humana, dias distintos com mensagem do lead e o dia anterior mais recente."""
    agora = c.agora()
    total = 0
    for ch in c.db.execute('SELECT assumido_em, fechado_em FROM chamados WHERE lead_id=? AND assumido_em IS NOT NULL',
                           (lead_id,)):
        total += minutos(ch['assumido_em'], parse(ch['fechado_em']) or agora)
    dias = [r[0] for r in c.db.execute("SELECT DISTINCT substr(em,1,10) FROM mensagens WHERE lead_id=? AND de='lead' "
                                       'AND em IS NOT NULL ORDER BY 1 DESC', (lead_id,))]
    return {'minutos_conversa': total, 'dias_contato': len(dias), 'dia_anterior': dias[1] if len(dias) > 1 else None}


def retornar_em(c, lead):
    if lead['status'] != 'retornar':
        return None
    r = c.db.execute('SELECT em FROM retornos WHERE lead_id=? ORDER BY chamado_id DESC LIMIT 1', (lead['id'],)).fetchone()
    return r['em'] if r else None


def extras(c, lead):
    """Campos comuns à lista da equipe e à do gestor."""
    aberto = chamados.aberto_do_lead(c, lead['id'])
    d = {'retornar_em': retornar_em(c, lead), 'chamado_aberto': aberto['id'] if aberto else None,
         'minutos_desde_contato': minutos(lead['ultimo_contato'], c.agora()) if lead['ultimo_contato'] else None}
    d.update(metricas(c, lead['id']))
    return d


def ordenar(itens):
    """Ordem por nível: status, depois (retornar) retorno mais próximo / (novo) com chamado aberto antes;
    dentro do nível, ultimo_contato mais recente primeiro."""
    itens = sorted(itens, key=lambda d: d.get('ultimo_contato') or '', reverse=True)

    def chave(d):
        nivel = NIVEL.get(d.get('status'), 7)
        if d.get('status') == 'retornar':
            sub = (0, d['retornar_em']) if d.get('retornar_em') else (1, '')
        elif d.get('status') == 'novo':
            sub = (0 if d.get('chamado_aberto') else 1, '')
        else:
            sub = (0, '')
        return (nivel, sub)
    return sorted(itens, key=chave)


def _ultima_do_lead(c, lead_id):
    r = c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' ORDER BY id DESC LIMIT 1",
                     (lead_id,)).fetchone()
    return (r['texto'] or '')[:120] if r else None


def _base_vista(c, colab, lead_id):
    """Até qual mensagem (id) o colaborador já viu; None se ele nunca fechou/devolveu chamado do lead."""
    fech = c.db.execute("SELECT MAX(fechado_em) FROM chamados WHERE lead_id=? AND dono=? AND status='fechado'",
                        (lead_id, colab)).fetchone()[0]
    if not fech:
        return None
    v = c.db.execute('SELECT ate FROM vistos WHERE colaborador=? AND lead_id=?', (colab, lead_id)).fetchone()
    if v:
        return v['ate']
    # banco anterior à 1.3.4 (sem `vistos`): o que chegou até o minuto do fechamento conta como visto
    r = c.db.execute('SELECT MAX(id) FROM mensagens WHERE lead_id=? AND em<=?', (lead_id, fech)).fetchone()[0]
    return r or 0


def novas(c, colab, lead_id):
    base = _base_vista(c, colab, lead_id)
    if base is None:
        return 0
    return c.db.execute("SELECT COUNT(*) FROM mensagens WHERE lead_id=? AND de='lead' AND id>?",
                        (lead_id, base)).fetchone()[0]


def marcar_visto(c, colab, lead_id):
    """Fechamento, devolução ou ficha aberta pelo colaborador: o que chegou até agora está visto."""
    if not colab:
        return
    ate = c.db.execute('SELECT COALESCE(MAX(id),0) FROM mensagens WHERE lead_id=?', (lead_id,)).fetchone()[0]
    c.db.execute('INSERT INTO vistos(colaborador,lead_id,ate) VALUES (?,?,?) ON CONFLICT(colaborador,lead_id) '
                 'DO UPDATE SET ate=MAX(ate, excluded.ate)', (colab, lead_id, ate))


def de_colaborador(c, colab, q):
    sql = ("SELECT * FROM leads WHERE telefone NOT LIKE 'apagado-%' AND (id IN (SELECT lead_id FROM chamados WHERE dono=? "
           "OR (ofertado_a=? AND status IN ('aguardando','alerta'))) OR id IN "
           "(SELECT lead_id FROM historico WHERE json_extract(dados, '$.colaborador')=?))")
    args = [colab, colab, colab]
    if q.get('status'):
        sql += ' AND status=?'
        args.append(q['status'])
    out = []
    for lead in c.db.execute(sql, args).fetchall():
        d = {k: lead[k] for k in ('id', 'nome', 'telefone', 'status', 'nota', 'interesse', 'ultimo_contato')}
        d['ultima_mensagem'] = _ultima_do_lead(c, lead['id'])
        d['nao_contatar'] = bool(lead['nao_contatar'])
        d['novas'] = novas(c, colab, lead['id'])
        d.update(extras(c, lead))
        out.append(d)
    return ordenar(out)


def ficha_lead(c, lead):
    d = conversa.lead_json(c, lead)
    d.update(metricas(c, lead['id']))
    d['minutos_desde_contato'] = minutos(lead['ultimo_contato'], c.agora()) if lead['ultimo_contato'] else None
    return d
