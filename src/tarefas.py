"""Tarefas de tempo (seções 1, 7, 9, 10): rodam por POST /api/tarefas/rodar ou a cada 30 s."""
from .core import depois, formatar_telefone, iso, parse
from . import chamados, equipe, evolution, horario
from . import telegram as tg


def rodar(c, forcar=False):
    agora = c.agora()
    acoes = 0
    acoes += abrir_expediente(c, agora)
    acoes += vencer_ofertas(c, agora)
    acoes += alertas(c, agora)
    acoes += lembretes(c, agora)
    acoes += retornos(c, agora)
    acoes += fim_expediente(c, agora)
    acoes += evolution.reenviar(c, forcar)
    chamados.distribuir(c)  # rede de segurança: chamado ativo sem oferta e alguém livre
    return {'ok': True, 'acoes': acoes}


def abrir_expediente(c, agora):
    janela = horario.janela_atual(c, agora)
    if not janela:
        return 0
    n = 0
    for ch in c.db.execute("SELECT id FROM chamados WHERE status='aguardando' AND conta_desde IS NULL "
                           'ORDER BY aberto_em, id').fetchall():
        c.db.execute('UPDATE chamados SET conta_desde=? WHERE id=?', (iso(janela[0]), ch['id']))
        c.sujo = True
        chamados.ativar(c, ch['id'])
        n += 1
    return n


def vencer_ofertas(c, agora):
    prazo = c.prazo('oferta_min', 2)
    n = 0
    for ch in c.db.execute("SELECT * FROM chamados WHERE status IN ('aguardando','alerta') AND ofertado_a IS NOT NULL "
                           'ORDER BY aberto_em, id').fetchall():
        if ch['ofertado_em'] and depois(parse(ch['ofertado_em']), prazo) <= agora:
            chamados.vencer_oferta(c, ch)
            n += 1
    return n


def alertas(c, agora):
    n = 0
    for ch in c.db.execute("SELECT * FROM chamados WHERE status='aguardando' AND alertado=0 AND conta_desde IS NOT NULL "
                           'ORDER BY aberto_em, id').fetchall():
        prazo = c.prazo('alerta_quente_min', 2) if ch['prioridade'] == 'quente' else c.prazo('alerta_normal_min', 5)
        if depois(parse(ch['conta_desde']), prazo) <= agora:
            if chamados.alertar(c, ch):
                n += 1
    return n


def lembretes(c, agora):
    prazo = c.prazo('lembrete_min', 30)
    n = 0
    for ch in c.db.execute("SELECT * FROM chamados WHERE status='atendendo' AND lembrado=0").fetchall():
        base = ch['ultimo_mov'] or ch['assumido_em']
        if base and depois(parse(base), prazo) <= agora:
            lead = c.lead(ch['lead_id'])
            quem = lead['nome'] or formatar_telefone(lead['telefone'])
            ref = equipe.privado(c, ch['dono'], f'Ainda com {quem}?',
                                 [[tg.bt('Sim, continuo', f"lc:{ch['id']}"), tg.bt('Terminei', f"lt:{ch['id']}")]])
            chamados.guardar_msg(c, ref, ch['id'], 'lembrete')
            c.db.execute('UPDATE chamados SET lembrado=1 WHERE id=?', (ch['id'],))
            n += 1
    return n


def retornos(c, agora):
    n = 0
    for r in c.db.execute('SELECT * FROM retornos WHERE enviado=0 AND em<=? ORDER BY em', (iso(agora),)).fetchall():
        ch = c.chamado(r['chamado_id'])
        lead = c.lead(r['lead_id'])
        texto = f"📅 Retorno: {lead['nome'] or 'lead'} {formatar_telefone(lead['telefone'])}"
        if r['colaborador']:
            ref = equipe.privado(c, r['colaborador'], texto,
                                 [[tg.bt('✅ Assumir', f"ra:{r['chamado_id']}")], chamados.botoes_contato(c, ch)])
            chamados.guardar_msg(c, ref, r['chamado_id'], 'retorno')  # para o "apagar meus dados" editar
        c.db.execute('UPDATE retornos SET enviado=1 WHERE chamado_id=?', (r['chamado_id'],))
        n += 1
    return n


def fim_expediente(c, agora):
    fim = horario.fim_do_dia(c, agora.date())
    hoje = agora.date().isoformat()
    if not fim or agora < fim or c.meta('fim_expediente') == hoje:
        return 0
    c.meta('fim_expediente', hoje, gravar=True)
    abertos = c.db.execute("SELECT * FROM chamados WHERE status='atendendo' ORDER BY dono, id").fetchall()
    if not abertos:
        return 0
    donos = []
    for ch in abertos:
        if ch['dono'] not in donos:
            donos.append(ch['dono'])
    for d in donos:
        equipe.privado(c, d, 'Fim do expediente: feche seus atendimentos')
    gid = tg.grupo()
    if gid:
        from .core import primeiro_nome
        linhas = ['Fim do expediente — ainda abertos:']
        for ch in abertos:
            linhas.append(f"🟡 #{ch['id']} {primeiro_nome(c.lead(ch['lead_id'])['nome'])} · {c.nome_colab(ch['dono'])}")
        tg.enviar(c, gid, '\n'.join(linhas))
    return 1
