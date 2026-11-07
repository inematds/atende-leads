"""1.9.8 — retomar contato, gestor passa conversa do robô a um atendente, robô cobre (seção 7b)."""
from datetime import timedelta

from .core import Erro, iso, minutos, novo_token
from . import chamados, conversa, equipe, evolution

AVISO_ROBO = ('Nossa equipe está ocupada neste momento. Enquanto ninguém fica livre, eu sigo com você: pode perguntar '
              'à vontade. Assim que alguém da equipe estiver disponível, assume a conversa daqui.')


def _apagado(lead):
    return str(lead['telefone'] or '').startswith('apagado-')


def _novo_atendimento(c, lead, colab, motivo, avisar_lead):
    """Abre um chamado já assumido por `colab`, sem oferta nem alerta (quem decidiu foi uma pessoa)."""
    if _apagado(lead):
        raise Erro(409, 'Este lead pediu para apagar os dados')
    aberto = chamados.aberto_do_lead(c, lead['id'])
    if aberto:
        if aberto['status'] == 'atendendo' and aberto['dono'] == colab:
            return chamados.json_chamado(c, aberto)
        if aberto['status'] == 'atendendo':
            raise Erro(409, f"Este cliente já está com {c.nome_colab(aberto['dono'])}")
        return chamados.transferir(c, aberto['id'], colab)  # estava na fila: vai direto para a pessoa
    if c.colab(colab)['status'] == 'fora':
        raise Erro(409, 'Quem está fora não pode assumir')
    agora = iso(c.agora())
    ident = c.db.execute(
        'INSERT INTO chamados(lead_id,motivo,prioridade,status,aberto_em,conta_desde,assumido_em,dono,ultimo_mov,'
        'token,resumo) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (lead['id'], motivo, chamados.prioridade(motivo, lead), 'aguardando', agora, agora, None, None, agora,
         novo_token(), None)).lastrowid
    c.db.execute("UPDATE chamados SET status='atendendo', dono=?, assumido_em=? WHERE id=?", (colab, agora, ident))
    chamados._pos_assumir(c, c.chamado(ident), colab, avisar_lead=avisar_lead)
    return chamados.json_chamado(c, c.chamado(ident))


def retomar(c, lead_id, colab):
    """O atendente volta a falar com um cliente que já atendeu (encerrado ou com o robô)."""
    lead = c.lead(lead_id)
    if lead['nao_contatar']:
        raise Erro(409, 'Este cliente pediu para não ser mais contatado')
    if not c.db.execute('SELECT 1 FROM chamados WHERE lead_id=? AND dono=? LIMIT 1', (lead_id, colab)).fetchone():
        raise Erro(403, 'Você não atendeu este cliente')
    aberto = chamados.aberto_do_lead(c, lead_id)
    if aberto and aberto['status'] in ('aguardando', 'alerta') and aberto['ofertado_a'] not in (None, colab) \
            and aberto['status'] != 'alerta':
        raise Erro(409, f"Este cliente está sendo oferecido a {c.nome_colab(aberto['ofertado_a'])}")
    r = _novo_atendimento(c, lead, colab, 'retomada', avisar_lead=False)
    equipe.privado(c, colab, f"🔁 Você retomou {lead['nome'] or 'o contato'} (#{r['id']}). Responda pelo painel.")
    return r


def atribuir(c, lead_id, colab):
    """Gestor passa a conversa (com o robô, encerrada ou na fila) para um atendente."""
    lead = c.lead(lead_id)
    if lead['nao_contatar']:
        raise Erro(409, 'Este cliente pediu para não ser mais contatado')
    r = _novo_atendimento(c, lead, colab, 'gestor', avisar_lead=True)
    equipe.privado(c, colab, f"📌 O gestor passou {lead['nome'] or 'um cliente'} para você (#{r['id']}). "
                             'Abra o painel para conversar.')
    return r


# ---------- robô cobre ----------
def robo_por_mim(c, colab, ativo):
    if not isinstance(ativo, bool):
        raise Erro(422, 'ativo deve ser true ou false')
    c.colab(colab)
    c.db.execute('UPDATE colaboradores SET robo_por_mim=? WHERE id=?', (1 if ativo else 0, colab))
    c.sujo = True
    return {'id': colab, 'robo_por_mim': ativo}


def cobre_dono(c, ch):
    r = c.db.execute('SELECT robo_por_mim FROM colaboradores WHERE id=?', (ch['dono'],)).fetchone()
    return bool(r and r['robo_por_mim'])


def cfg_robo(c):
    r = c.cfg.get('robo') or {}
    return {'assume_espera': bool(r.get('assume_espera')), 'apos_min': int(r.get('apos_min') or 10)}


def assumir_esperas(c, agora):
    """Tarefa: com `robo.assume_espera`, o chamado esperando há `apos_min` ganha o aviso do robô (uma vez)."""
    cfg = cfg_robo(c)
    if not cfg['assume_espera']:
        return 0
    n = 0
    # chamado silencioso (1.10.8) fica de fora: o cliente não sabe que a equipe foi chamada
    for ch in c.db.execute("SELECT * FROM chamados WHERE status IN ('aguardando','alerta') AND robo_assumiu IS NULL "
                           'AND conta_desde IS NOT NULL AND silencioso=0').fetchall():
        if minutos(ch['conta_desde'], agora) < cfg['apos_min']:
            continue
        lead = c.lead(ch['lead_id'])
        c.db.execute('UPDATE chamados SET robo_assumiu=? WHERE id=?', (iso(agora), ch['id']))
        conversa.registrar(c, lead['id'], 'agente', AVISO_ROBO, ch['id'])
        evolution.enviar_lead(c, lead, AVISO_ROBO, 'aviso', automatica=True)
        c.sujo = True
        n += 1
    return n


def resposta_robo(c, t, texto, lead_id, ch, fallback):
    """O robô responde no lugar da pessoa ("robô responde por mim"). A frase pronta (`fallback`) sai no máximo
    uma vez a cada 30 min por atendimento e nunca para "ok"/"obrigado" (uma palavra)."""
    r = conversa._duvida_em_espera(c, t, texto, lead_id)
    if r:
        return [r]
    if not fallback or len(t.split()) < 2:
        return []
    desde = iso(c.agora() - timedelta(minutes=30))
    ja = c.db.execute("SELECT 1 FROM mensagens WHERE chamado_id=? AND de='agente' AND texto=? AND em>=? LIMIT 1",
                      (ch['id'], fallback, desde)).fetchone()
    return [] if ja else [fallback]
