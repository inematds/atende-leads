"""1.10.8 — o atendente pede para mudar o próprio cadastro (nome e telefone); o gestor aprova ou recusa.
Com `permissoes.perfil_sem_aprovacao`, a mudança vale na hora. Código e id nunca mudam por aqui."""
import copy
import json
import re

from .core import Erro, iso, normalizar_telefone


def sem_aprovacao(c):
    return bool((c.cfg.get('permissoes') or {}).get('perfil_sem_aprovacao'))


def _limpar(c, colab, b):
    m = c.membro(colab)
    if not m:
        raise Erro(404, 'Colaborador não encontrado')
    if not isinstance(b, dict):
        raise Erro(422, 'Envie nome e/ou telefone')
    dados = {}
    if 'nome' in b:
        if not isinstance(b['nome'], str):
            raise Erro(422, 'Nome deve ser texto')
        nome = ' '.join(b['nome'].split())
        if not 1 <= len(nome) <= 80:
            raise Erro(422, 'Nome de 1 a 80 caracteres')
        if not re.fullmatch(r"[^\W\d_]+(?:[ '.-][^\W\d_]+)*\.?", nome):  # o nome vai para o cliente ("X vai te atender")
            raise Erro(422, 'Use só letras no nome')
        dados['nome'] = nome
    if 'telefone' in b:
        if b['telefone'] is not None and not isinstance(b['telefone'], str):
            raise Erro(422, 'Telefone deve ser texto')
        tel = (b['telefone'] or '').strip()
        dados['telefone'] = normalizar_telefone(tel) if tel else ''
        if dados['telefone'] and any(str(o.get('telefone') or '') == dados['telefone'] and o['id'] != colab
                                     for o in c.cfg.get('equipe', [])):
            raise Erro(422, 'Este telefone já é de outra pessoa da equipe')
    dados = {k: v for k, v in dados.items() if v != str(m.get(k) or '')}
    if not dados:
        raise Erro(422, 'Nada mudou')
    return dados


def _aplicar(c, colab, dados):
    from . import gestao
    cfg = copy.deepcopy(c.cfg)
    for m in cfg.get('equipe', []):
        if m['id'] == colab:
            m.update(dados)
    c.salvar_cfg(gestao.validar_config(c, cfg))
    c.sujo = True


def pendente(c, colab):
    r = c.db.execute("SELECT * FROM pedidos_perfil WHERE colaborador=? AND status='pendente' ORDER BY id DESC LIMIT 1",
                     (colab,)).fetchone()
    return {'id': r['id'], 'dados': json.loads(r['dados']), 'em': r['em']} if r else None


def ultimo_decidido(c, colab):
    r = c.db.execute("SELECT * FROM pedidos_perfil WHERE colaborador=? AND status IN ('aprovado','recusado') "
                     'ORDER BY id DESC LIMIT 1', (colab,)).fetchone()
    return {'id': r['id'], 'status': r['status'], 'dados': json.loads(r['dados']), 'decidido_em': r['decidido_em'],
            'motivo': r['motivo']} if r else None


def meu(c, colab):
    m = c.membro(colab) or {}
    return {'nome': m.get('nome', ''), 'telefone': str(m.get('telefone') or ''), 'pendente': pendente(c, colab),
            'ultimo': ultimo_decidido(c, colab), 'sem_aprovacao': sem_aprovacao(c)}


def pedir(c, colab, b):
    dados = _limpar(c, colab, b)
    agora = iso(c.agora())
    c.db.execute("UPDATE pedidos_perfil SET status='substituido', decidido_em=? WHERE colaborador=? AND status='pendente'",
                 (agora, colab))
    if sem_aprovacao(c):
        _aplicar(c, colab, dados)
        c.db.execute("INSERT INTO pedidos_perfil(colaborador,dados,em,status,decidido_em,motivo) VALUES (?,?,?,?,?,?)",
                     (colab, json.dumps(dados, ensure_ascii=False), agora, 'aprovado', agora, 'sem aprovação'))
        return {**meu(c, colab), 'aplicado': True}
    c.db.execute('INSERT INTO pedidos_perfil(colaborador,dados,em) VALUES (?,?,?)',
                 (colab, json.dumps(dados, ensure_ascii=False), agora))
    c.sujo = True
    return {**meu(c, colab), 'aplicado': False}


def cancelar(c, colab):
    c.db.execute("UPDATE pedidos_perfil SET status='cancelado', decidido_em=? WHERE colaborador=? AND status='pendente'",
                 (iso(c.agora()), colab))
    c.sujo = True
    return meu(c, colab)


def listar(c):
    out = []
    for r in c.db.execute("SELECT * FROM pedidos_perfil WHERE status='pendente' ORDER BY id"):
        m = c.membro(r['colaborador'])
        if not m:
            continue
        out.append({'id': r['id'], 'colaborador': r['colaborador'], 'em': r['em'], 'dados': json.loads(r['dados']),
                    'atual': {'nome': m.get('nome', ''), 'telefone': str(m.get('telefone') or '')}})
    return out


def decidir(c, ident, aprovar, motivo=None):
    if not isinstance(aprovar, bool):
        raise Erro(422, 'aprovar deve ser true ou false')
    r = c.db.execute('SELECT * FROM pedidos_perfil WHERE id=?', (ident,)).fetchone()
    if not r:
        raise Erro(404, 'Pedido não encontrado')
    if r['status'] != 'pendente':
        raise Erro(409, 'Este pedido já foi decidido')
    if not c.membro(r['colaborador']):
        raise Erro(409, 'Colaborador não está mais na equipe')
    if aprovar:
        _aplicar(c, r['colaborador'], json.loads(r['dados']))
    motivo = ' '.join(str(motivo or '').split())[:200] or None
    c.db.execute('UPDATE pedidos_perfil SET status=?, decidido_em=?, motivo=? WHERE id=?',
                 ('aprovado' if aprovar else 'recusado', iso(c.agora()), motivo, ident))
    c.sujo = True
    from . import equipe
    equipe.privado(c, r['colaborador'], '✅ O gestor aprovou a mudança no seu cadastro.' if aprovar else
                   '❌ O gestor recusou a mudança no seu cadastro' + (f': {motivo}' if motivo else '.'))
    return listar(c)
