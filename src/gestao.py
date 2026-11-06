"""Painel do gestor (seção 13): números do dia, leads, ficha, configuração e exportação."""
import copy
import csv
import io
import json
import re

from .core import DIAS, Erro, minutos, parse
from . import chamados, conversa, equipe, evolution


def ao_vivo(c):
    p = equipe.painel(c)
    p['agora'] = c.agora().strftime('%Y-%m-%dT%H:%M')
    p['alertas'] = [chamados.json_chamado(c, ch) for ch in
                    c.db.execute("SELECT * FROM chamados WHERE status='alerta' ORDER BY aberto_em, id")]
    p['atendendo'] = [chamados.json_chamado(c, ch) for ch in
                      c.db.execute("SELECT * FROM chamados WHERE status='atendendo' ORDER BY assumido_em, id")]
    p['descartes'] = evolution.descartes(c)
    return p


def hoje(c):
    dia = c.agora().date().isoformat()

    def no_dia(campo):
        return f"substr({campo},1,10)='{dia}'"
    q = c.db.execute
    leads_novos = q(f'SELECT COUNT(*) FROM leads WHERE {no_dia("criado_em")}').fetchone()[0]
    abertos = q(f'SELECT COUNT(*) FROM chamados WHERE {no_dia("aberto_em")}').fetchone()[0]
    assumidos = q(f'SELECT * FROM chamados WHERE assumido_em IS NOT NULL AND {no_dia("assumido_em")}').fetchall()
    vendas = q(f"SELECT * FROM chamados WHERE status='fechado' AND resultado='vendeu' AND {no_dia('fechado_em')}").fetchall()
    tempos = [minutos(ch['conta_desde'] or ch['aberto_em'], parse(ch['assumido_em'])) for ch in assumidos]
    por = []
    for m in c.cfg.get('equipe', []):
        meus_v = [v for v in vendas if v['dono'] == m['id']]
        por.append({'id': m['id'], 'nome': m['nome'],
                    'assumidos': sum(1 for a in assumidos if a['dono'] == m['id']),
                    'vendas': len(meus_v), 'valor': float(sum(v['valor'] or 0 for v in meus_v))})
    return {'dia': dia, 'leads_novos': leads_novos, 'chamados_abertos': abertos, 'assumidos': len(assumidos),
            'vendas': len(vendas), 'valor_vendido': float(sum(v['valor'] or 0 for v in vendas)),
            'tempo_medio_assumir_min': round(sum(tempos) / len(tempos), 1) if tempos else 0,
            'por_colaborador': por}


def _ultimo_chamado(c, lead_id):
    return c.db.execute('SELECT * FROM chamados WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()


def _linha_lead(c, lead):
    d = conversa.lead_json(c, lead)
    ult = _ultimo_chamado(c, lead['id'])
    d['colaborador'] = ult['dono'] if ult else None
    d['resultado'] = ult['resultado'] if ult else None
    d['valor'] = ult['valor'] if ult else None
    d['chamado_status'] = ult['status'] if ult else None
    return d


def leads(c, q):
    sql, args = 'SELECT * FROM leads WHERE 1=1', []
    if q.get('status'):
        sql += ' AND status=?'
        args.append(q['status'])
    if q.get('colaborador'):
        sql += (' AND (id IN (SELECT lead_id FROM chamados WHERE dono=?) OR id IN '
                "(SELECT lead_id FROM historico WHERE json_extract(dados, '$.colaborador')=?))")
        args += [q['colaborador'], q['colaborador']]
    if q.get('de'):
        sql += ' AND substr(criado_em,1,10)>=?'
        args.append(q['de'][:10])
    if q.get('ate'):
        sql += ' AND substr(criado_em,1,10)<=?'
        args.append(q['ate'][:10])
    return [_linha_lead(c, r) for r in c.db.execute(sql + ' ORDER BY id DESC', args)]


def ficha(c, lead_id):
    lead = c.lead(lead_id)
    msgs = [dict(r) for r in c.db.execute('SELECT id, chamado_id, de, autor, texto, em FROM mensagens WHERE lead_id=? '
                                          'ORDER BY id', (lead_id,))]
    chs = [chamados.json_chamado(c, ch) for ch in c.db.execute('SELECT * FROM chamados WHERE lead_id=? ORDER BY id',
                                                                (lead_id,))]
    hist = [json.loads(r['dados']) for r in c.db.execute('SELECT dados FROM historico WHERE lead_id=? ORDER BY id',
                                                          (lead_id,))]
    return {'lead': conversa.lead_json(c, lead), 'mensagens': msgs, 'chamados': chs, 'historico': hist}


CABECALHO = 'lead_id,nome,telefone,status,nota,interesse,colaborador,resultado,valor,criado_em,ultimo_contato'


PERIGOSOS = ('=', '+', '-', '@', '\t', '\r')


def celula(v):
    """Evita injeção de fórmula ao abrir o CSV numa planilha: texto que começa com = + - @ tab CR ganha '."""
    if isinstance(v, str) and v.startswith(PERIGOSOS):
        return "'" + v
    return v


def exportar_csv(c):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(CABECALHO.split(','))
    for lead in c.db.execute('SELECT * FROM leads ORDER BY id'):
        ult = _ultimo_chamado(c, lead['id'])
        w.writerow([celula(x) for x in [lead['id'], lead['nome'] or '', lead['telefone'], lead['status'], lead['nota'],
                    lead['interesse'] or '', (ult['dono'] or '') if ult else '', (ult['resultado'] or '') if ult else '',
                    '' if not ult or ult['valor'] is None else ult['valor'], lead['criado_em'] or '',
                    lead['ultimo_contato'] or '']])
    return buf.getvalue()


# ---------- configuração ----------
def config_publica(c):
    cfg = copy.deepcopy(c.cfg)
    cfg['token_gestor'] = '***'
    return cfg


HHMM = re.compile(r'^([01]\d|2[0-3]):[0-5]\d$')


def _erro(msg):
    raise Erro(422, msg)


def validar_config(c, novo):
    if not isinstance(novo, dict):
        _erro('Configuração deve ser um objeto')
    cfg = copy.deepcopy(c.cfg)
    cfg.update(novo)
    if cfg.get('token_gestor') in (None, '', '***'):
        cfg['token_gestor'] = c.cfg.get('token_gestor')
    if not isinstance(cfg.get('nome'), str) or not cfg['nome'].strip():
        _erro('nome obrigatório')
    if not isinstance(cfg.get('token_gestor'), str) or len(cfg['token_gestor']) < 4:
        _erro('token_gestor inválido')
    for lista in ('equipe', 'produtos', 'faq'):
        if not isinstance(cfg.get(lista, []), list):
            _erro(f'{lista} deve ser lista')
        ids = []
        for item in cfg.get(lista, []):
            if not isinstance(item, dict) or not isinstance(item.get('id'), str) or not item['id'].strip():
                _erro(f'{lista}: cada item precisa de id')
            ids.append(item['id'])
        if len(ids) != len(set(ids)):
            _erro(f'{lista}: ids repetidos')
    codigos = []
    for m in cfg.get('equipe', []):
        if not isinstance(m.get('nome'), str) or not m['nome'].strip():
            _erro('equipe: nome obrigatório')
        if not isinstance(m.get('codigo'), str) or not m['codigo'].strip():
            _erro('equipe: código obrigatório')
        if len(m['codigo']) < 12:  # código curto é adivinhável (o limite de tentativas não basta)
            _erro('equipe: código com pelo menos 12 caracteres')
        tel = m.get('telefone')
        if tel not in (None, '') and not re.fullmatch(r'\d+', str(tel)):
            _erro('equipe: telefone só com dígitos')
        codigos.append(m['codigo'])
    if len(codigos) != len(set(codigos)):
        _erro('equipe: códigos repetidos')
    for p in cfg.get('produtos', []):
        if not isinstance(p.get('nome'), str) or not p['nome'].strip():
            _erro('produtos: nome obrigatório')
        if not isinstance(p.get('palavras', []), list):
            _erro('produtos: palavras deve ser lista')
    for f in cfg.get('faq', []):
        if not isinstance(f.get('perguntas'), list) or not isinstance(f.get('resposta'), str):
            _erro('faq: perguntas (lista) e resposta obrigatórias')
    hor = cfg.get('horarios')
    if not isinstance(hor, dict):
        _erro('horarios deve ser objeto')
    for dia, janelas in hor.items():
        if dia not in DIAS or not isinstance(janelas, list):
            _erro(f'horarios: dia inválido {dia}')
        for j in janelas:
            if (not isinstance(j, list) or len(j) != 2 or not all(isinstance(x, str) and HHMM.match(x) for x in j)
                    or j[0] >= j[1]):
                _erro('horarios: use ["HH:MM","HH:MM"]')
    prazos = cfg.get('prazos')
    if not isinstance(prazos, dict):
        _erro('prazos deve ser objeto')
    for k in ('oferta_min', 'alerta_quente_min', 'alerta_normal_min', 'lembrete_min'):
        v = prazos.get(k)
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            _erro(f'prazos.{k} deve ser inteiro ≥ 1')
    for k, v in prazos.items():
        if isinstance(v, bool) or not isinstance(v, int) or v < 1:
            _erro(f'prazos.{k} deve ser inteiro ≥ 1')
    cer = cfg.get('cerebro', {'tipo': 'regras'})
    if not isinstance(cer, dict) or cer.get('tipo', 'regras') not in ('regras', 'ollama', 'openai'):
        _erro('cerebro.tipo deve ser regras, ollama ou openai')
    if any(k.lower() in ('api_key', 'chave', 'key') for k in cer):
        _erro('a chave do cérebro vai em CEREBRO_API_KEY, não no JSON')
    return cfg


def gravar_config(c, novo):
    cfg = validar_config(c, novo)
    c.salvar_cfg(cfg)
    c.sujo = True
    return config_publica(c)
