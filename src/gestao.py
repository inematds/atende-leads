"""Painel do gestor (seção 13): números do dia, leads, ficha, configuração e exportação."""
import copy
import csv
import io
import json
import re

from datetime import timedelta

from .core import DIAS, ROOT, Erro, iso, minutos, parse
from . import base, cerebro, chamados, contatos, conversa, equipe, evolution, sugestao


def sem_resposta_min(c, ch):
    """Minutos que o cliente espera resposta da equipe neste atendimento (None = respondido).
    Ninguém respondeu desde o assumir → conta do assumir; já respondeu → da 1ª mensagem do lead depois da última resposta.
    Só conta resposta enviada pelo sistema (painel/Telegram): ligação ou mensagem por fora não aparece aqui."""
    q = c.db.execute
    ult_h = q("SELECT MAX(id) FROM mensagens WHERE chamado_id=? AND de='humano'", (ch['id'],)).fetchone()[0]
    if not ult_h:
        return minutos(ch['assumido_em'], c.agora()) if ch['assumido_em'] else None
    r = q("SELECT em FROM mensagens WHERE lead_id=? AND de='lead' AND id>? ORDER BY id LIMIT 1",
          (ch['lead_id'], ult_h)).fetchone()
    return minutos(r['em'], c.agora()) if r and r['em'] else None


def _atendendo_json(c, ch):
    d = chamados.json_chamado(c, ch)
    d['sem_resposta_min'] = sem_resposta_min(c, ch)
    return d


def _ativo_desde(c):
    """Corte da "conversa ativa": contato do lead nas últimas `prazos.conversa_ativa_h` horas (padrão 24)."""
    return iso(c.agora() - timedelta(hours=c.prazo('conversa_ativa_h', 24)))


def _robo_ativo(c, lead, aberto=False):
    """Sem chamado aberto, contato recente e (nenhum chamado fechado ou o lead falou depois do último fechamento)."""
    if not lead['ultimo_contato'] or lead['ultimo_contato'] < _ativo_desde(c):
        return False
    if (chamados.aberto_do_lead(c, lead['id']) if aberto is False else aberto):
        return False
    fech = c.db.execute("SELECT MAX(fechado_em) FROM chamados WHERE lead_id=? AND status='fechado'",
                        (lead['id'],)).fetchone()[0]
    if not fech:
        return True
    # a mensagem do lead que vem depois da última mensagem registrada no chamado fechado (por id: o minuto empata)
    ult_ch = c.db.execute("SELECT MAX(m.id) FROM mensagens m JOIN chamados ch ON ch.id=m.chamado_id "
                          "WHERE ch.lead_id=? AND ch.status='fechado'", (lead['id'],)).fetchone()[0]
    if ult_ch is None:
        ult = c.db.execute("SELECT MAX(em) FROM mensagens WHERE lead_id=? AND de='lead'", (lead['id'],)).fetchone()[0]
        return bool(ult) and ult > fech
    return bool(c.db.execute("SELECT 1 FROM mensagens WHERE lead_id=? AND de='lead' AND id>? AND chamado_id IS NULL LIMIT 1",
                             (lead['id'], ult_ch)).fetchone())


def situacao(c, lead):
    """atendendo | espera | robo | encerrado | parado — a coluna do lead no Ao vivo."""
    aberto = chamados.aberto_do_lead(c, lead['id'])
    if aberto:
        return 'atendendo' if aberto['status'] == 'atendendo' else 'espera'
    if _robo_ativo(c, lead, None):
        return 'robo'
    if c.db.execute("SELECT 1 FROM chamados WHERE lead_id=? AND status='fechado' LIMIT 1", (lead['id'],)).fetchone():
        return 'encerrado'
    return 'parado'


def robo(c):
    out = []
    for lead in c.db.execute("SELECT * FROM leads WHERE telefone NOT LIKE 'apagado-%' AND ultimo_contato>=? "
                             'ORDER BY ultimo_contato DESC, id DESC', (_ativo_desde(c),)).fetchall():
        if not _robo_ativo(c, lead):
            continue
        u = c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' ORDER BY id DESC LIMIT 1",
                         (lead['id'],)).fetchone()
        out.append({'lead_id': lead['id'], 'nome': lead['nome'], 'telefone': lead['telefone'], 'nota': lead['nota'],
                    'status': lead['status'], 'ultimo_contato': lead['ultimo_contato'],
                    'minutos_desde_contato': minutos(lead['ultimo_contato'], c.agora()),
                    'ultima_mensagem': (u['texto'] or '')[:120] if u else None})
    return out


def encerrados_hoje(c):
    dia = c.agora().date().isoformat()
    return [chamados.json_chamado(c, ch) for ch in
            c.db.execute("SELECT * FROM chamados WHERE status='fechado' AND substr(fechado_em,1,10)=? "
                         'ORDER BY fechado_em DESC, id DESC', (dia,))]


def _grupos(c):
    """Os quatro grupos do Ao vivo e do Hoje (1.8.8)."""
    extr = c.prazo('assumir_extremo_min', 10)
    espera = [chamados.json_chamado(c, ch) for ch in
              c.db.execute("SELECT * FROM chamados WHERE status IN ('aguardando','alerta') ORDER BY aberto_em, id")]
    atend = [_atendendo_json(c, ch) for ch in
             c.db.execute("SELECT * FROM chamados WHERE status='atendendo' ORDER BY assumido_em, id")]
    atrasos = sorted([a for a in atend if (a['sem_resposta_min'] or 0) > extr], key=lambda a: -a['sem_resposta_min'])
    return {'robo': robo(c), 'espera': espera, 'atendendo': atend, 'encerrados': encerrados_hoje(c),
            'sem_resposta': atrasos, 'conversa_ativa_h': c.prazo('conversa_ativa_h', 24)}


def ao_vivo(c):
    p = equipe.painel(c)
    p['agora'] = c.agora().strftime('%Y-%m-%dT%H:%M')
    p['alertas'] = [chamados.json_chamado(c, ch) for ch in
                    c.db.execute("SELECT * FROM chamados WHERE status='alerta' ORDER BY aberto_em, id")]
    for f in p['fila']:  # o gestor vê o telefone e o nome inteiro (a equipe e o grupo continuam com o primeiro nome)
        lead = c.lead(f['lead_id'])
        f['telefone'], f['lead_nome'], f['nota'] = lead['telefone'], lead['nome'], lead['nota']
    p.update(_grupos(c))
    p['descartes'] = evolution.descartes(c)
    return p


def faixas_assumir(c, tempos):
    """Faixas do tempo para assumir (seção 13): imediatos ≤ assumir_imediato_min < médios ≤ assumir_extremo_min < extremos."""
    imed = c.prazo('assumir_imediato_min', 1)
    extr = c.prazo('assumir_extremo_min', 10)
    return {'imediatos': sum(1 for t in tempos if t <= imed),
            'medios': sum(1 for t in tempos if imed < t <= extr),
            'extremos': sum(1 for t in tempos if t > extr),
            'maior_min': max(tempos) if tempos else 0,
            'media_min': round(sum(tempos) / len(tempos), 1) if tempos else 0,
            'imediato_min': imed, 'extremo_min': extr, 'tempos': sorted(tempos)}


def hoje(c):
    dia = c.agora().date().isoformat()

    def no_dia(campo):
        return f"substr({campo},1,10)='{dia}'"
    q = c.db.execute
    leads_novos = q(f'SELECT COUNT(*) FROM leads WHERE {no_dia("criado_em")}').fetchone()[0]
    abertos = q(f'SELECT COUNT(*) FROM chamados WHERE {no_dia("aberto_em")}').fetchone()[0]
    assumidos = q(f'SELECT * FROM chamados WHERE assumido_em IS NOT NULL AND {no_dia("assumido_em")}').fetchall()
    vendas = q(f"SELECT * FROM chamados WHERE status='fechado' AND resultado='vendeu' AND {no_dia('fechado_em')}").fetchall()
    def tempo(ch):
        return minutos(ch['conta_desde'] or ch['aberto_em'], parse(ch['assumido_em']))
    tempos = [tempo(ch) for ch in assumidos]
    por = []
    for m in c.cfg.get('equipe', []):
        meus_v = [v for v in vendas if v['dono'] == m['id']]
        por.append({'id': m['id'], 'nome': m['nome'],
                    'assumidos': sum(1 for a in assumidos if a['dono'] == m['id']),
                    'vendas': len(meus_v), 'valor': float(sum(v['valor'] or 0 for v in meus_v)),
                    'assumir': faixas_assumir(c, [tempo(a) for a in assumidos if a['dono'] == m['id']])})
    agora_ = q("SELECT * FROM chamados WHERE status IN ('aguardando','alerta','atendendo') ORDER BY aberto_em, id").fetchall()
    de_hoje = q(f"SELECT * FROM leads WHERE telefone NOT LIKE 'apagado-%' AND ({no_dia('criado_em')} OR "
                f"{no_dia('ultimo_contato')})").fetchall()
    faixas = faixas_assumir(c, tempos)
    return {'dia': dia, 'agora': c.agora().strftime('%Y-%m-%dT%H:%M'), 'leads_novos': leads_novos,
            'chamados_abertos': abertos, 'abertos_agora': len(agora_), 'assumidos': len(assumidos),
            'vendas': len(vendas), 'valor_vendido': float(sum(v['valor'] or 0 for v in vendas)),
            'tempo_medio_assumir_min': faixas['media_min'], 'assumir': faixas,
            'por_colaborador': por,
            'chamados_abertos_agora': [chamados.json_chamado(c, ch) for ch in agora_],
            'grupos': _grupos(c),
            'leads_hoje': contatos.ordenar([_linha_lead(c, r) for r in de_hoje])}


def _ultimo_chamado(c, lead_id):
    return c.db.execute('SELECT * FROM chamados WHERE lead_id=? ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()


def _linha_lead(c, lead):
    d = conversa.lead_json(c, lead)
    ult = _ultimo_chamado(c, lead['id'])
    d['colaborador'] = ult['dono'] if ult else None
    d['resultado'] = ult['resultado'] if ult else None
    d['valor'] = ult['valor'] if ult else None
    d['chamado_status'] = ult['status'] if ult else None
    d.update(contatos.extras(c, lead))
    d['situacao'] = situacao(c, lead)
    return d


FAIXA_CONTATO = {'1h': (0, 60), '24h': (0, 24 * 60), '1a7d': (24 * 60, 7 * 24 * 60), 'mais7d': (7 * 24 * 60, None)}


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
    linhas = [_linha_lead(c, r) for r in c.db.execute(sql + ' ORDER BY id DESC', args)]
    if q.get('situacao'):
        linhas = [d for d in linhas if d['situacao'] == q['situacao']]
    faixa = FAIXA_CONTATO.get(q.get('contato') or '')
    if faixa:
        de, ate = faixa
        linhas = [d for d in linhas if d['minutos_desde_contato'] is not None and d['minutos_desde_contato'] >= de
                  and (ate is None or d['minutos_desde_contato'] < ate)]
    return contatos.ordenar(linhas)


def ficha(c, lead_id):
    lead = c.lead(lead_id)
    msgs = [dict(r) for r in c.db.execute('SELECT id, chamado_id, de, autor, texto, em FROM mensagens WHERE lead_id=? '
                                          'ORDER BY id', (lead_id,))]
    chs = [chamados.json_chamado(c, ch) for ch in c.db.execute('SELECT * FROM chamados WHERE lead_id=? ORDER BY id',
                                                                (lead_id,))]
    hist = [json.loads(r['dados']) for r in c.db.execute('SELECT dados FROM historico WHERE lead_id=? ORDER BY id',
                                                          (lead_id,))]
    return {'lead': contatos.ficha_lead(c, lead), 'mensagens': msgs, 'chamados': chs, 'historico': hist}


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


def tokens_de_exemplo():
    try:
        ex = json.loads((ROOT / 'exemplos' / 'negocio.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        ex = {}
    return {'TROQUE-ESTE-TOKEN', str(ex.get('token_gestor') or 'TROQUE-ESTE-TOKEN')}


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
    if cfg['token_gestor'] != c.cfg.get('token_gestor'):
        # Token novo: 16+ caracteres e nunca o do exemplo (o atual, mantido com "***", não é revalidado).
        if len(cfg['token_gestor']) < 16 or cfg['token_gestor'] in tokens_de_exemplo():
            _erro('token_gestor: use 16+ caracteres e não o do exemplo')
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
        for k in ('preco', 'preco_promocao', 'promocao'):
            if p.get(k) not in (None, '') and (not isinstance(p[k], str) or len(p[k]) > 200):
                _erro(f'produtos: {k} deve ser texto (até 200 caracteres)')
        if p.get('promocao_ate') not in (None, '') and (not isinstance(p['promocao_ate'], str)
                                                         or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', p['promocao_ate'])):
            _erro('produtos: promocao_ate no formato AAAA-MM-DD')
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
    if prazos.get('assumir_imediato_min', 1) >= prazos.get('assumir_extremo_min', 10):
        _erro('prazos: assumir_imediato_min deve ser menor que assumir_extremo_min')
    _validar_cerebro(cfg.get('cerebro', {'tipo': 'regras'}), 'cerebro')
    cur = cfg.get('cerebro_curadoria')
    if cur not in (None, {}):  # ausente/vazio = usa o cerebro principal
        if not isinstance(cur, dict):
            _erro('cerebro_curadoria deve ser objeto')
        _validar_cerebro(cur, 'cerebro_curadoria', vazio_ok=True)
    info = cfg.get('info', {})
    if not isinstance(info, dict):
        _erro('info deve ser objeto')
    for k, v in info.items():
        if k not in base.CAMPOS:
            _erro(f'info: campo desconhecido {k}')
        if not isinstance(v, str) or len(v) > 2000:
            _erro(f'info.{k} deve ser texto (até 2000 caracteres)')
    validar_aparencia(cfg.get('aparencia', {}))
    apr = cfg.get('aprendizado', {})
    if not isinstance(apr, dict) or apr.get('periodo', 'semanal') not in sugestao.PERIODOS:
        _erro('aprendizado.periodo deve ser diario, semanal ou desligado')
    return cfg


# ---------- aparência do chat do lead (seção 2 `aparencia`, seção 11) ----------
TEMAS = ('claro', 'escuro', 'marinho')
HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
TINTAS = ('#1a1206', '#ffffff')  # letra sobre a cor de destaque: a de maior contraste


def _luminancia(hexa):
    def canal(v):
        v = int(v, 16) / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (canal(hexa[i:i + 2]) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contraste(a, b):
    """Razão de contraste WCAG 2.x entre duas cores #RRGGBB."""
    la, lb = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def tinta_sobre(cor):
    """(letra, razão): a tinta de TINTAS com maior contraste sobre `cor`."""
    return max(((t, contraste(cor, t)) for t in TINTAS), key=lambda x: x[1])


def validar_aparencia(ap):
    if not isinstance(ap, dict):
        _erro('aparencia deve ser objeto')
    for k in ap:
        if k not in ('tema', 'cor_destaque', 'nome_exibido'):
            _erro(f'aparencia: campo desconhecido {k}')
    if ap.get('tema', 'claro') not in TEMAS:
        _erro('aparencia.tema deve ser claro, escuro ou marinho')
    cor = ap.get('cor_destaque')
    if cor not in (None, ''):
        if not isinstance(cor, str) or not HEX.match(cor):
            _erro('aparencia.cor_destaque deve ser uma cor #RRGGBB')
        _tinta, razao = tinta_sobre(cor)
        if razao < 4.5:
            _erro(f'aparencia.cor_destaque: contraste {razao:.2f}:1 com o texto'.replace(f'{razao:.2f}', f'{razao:.2f}'.replace('.', ',')) + ', abaixo do mínimo 4,5:1 (AA). '
                  'Escolha uma cor mais clara ou mais escura.')
    nome = ap.get('nome_exibido')
    if nome not in (None, '') and (not isinstance(nome, str) or len(nome) > 80):
        _erro('aparencia.nome_exibido deve ser texto (até 80 caracteres)')


def aparencia(c):
    """GET /api/aparencia (pública): só tema, cor de destaque (e a letra sobre ela) e nome exibido."""
    ap = c.cfg.get('aparencia') or {}
    cor = ap.get('cor_destaque') or None
    return {'tema': ap.get('tema') or 'claro', 'cor_destaque': cor,
            'cor_destaque_texto': tinta_sobre(cor)[0] if cor else None,
            'nome_exibido': (ap.get('nome_exibido') or '').strip() or c.cfg.get('nome', '')}


def testar(c, texto):
    """Roda a conversa num lead fictício e desfaz tudo (seção 4a): banco, caixa de saída e Telegram."""
    if not isinstance(texto, str) or not texto.strip():
        _erro('Texto obrigatório')
    fila = getattr(c._local, 'fila', None)
    n_fila = len(fila) if fila is not None else 0
    sujo = c.sujo
    c.db.execute('SAVEPOINT testar')
    try:
        lead = conversa.novo_lead_web(c, '5500000000000')
        c.db.execute("UPDATE leads SET nome='Cliente Teste' WHERE id=?", (lead['id'],))
        conversa.registrar(c, lead['id'], 'lead', 'oi')
        conversa.registrar(c, lead['id'], 'agente', 'Olá! Como posso ajudar?')
        _l, respostas = conversa.receber(c, None, texto.strip()[:2000], 'web', sessao=lead['sessao'])
        ch = c.db.execute('SELECT motivo FROM chamados WHERE lead_id=? ORDER BY id DESC LIMIT 1',
                          (lead['id'],)).fetchone()
        return {'respostas': respostas, 'chamado': ch['motivo'] if ch else None}
    finally:
        c.db.execute('ROLLBACK TO testar')
        c.db.execute('RELEASE testar')
        if fila is not None:
            del fila[n_fila:]
        c.sujo = sujo


def _validar_cerebro(cer, nome, vazio_ok=False):
    if not isinstance(cer, dict):
        _erro(f'{nome} deve ser objeto')
    t = cer.get('tipo', 'regras')
    if not (vazio_ok and t in (None, '')) and t not in cerebro.TIPOS:
        _erro(f'{nome}.tipo deve ser ' + ', '.join(cerebro.TIPOS))
    if any(k.lower() in ('api_key', 'apikey', 'chave', 'key', 'token', 'x-api-key') for k in cer):
        _erro('a chave do cérebro vai em CEREBRO_API_KEY (.env), não no JSON')
    if cer.get('modelo') not in (None, '') and (not isinstance(cer['modelo'], str)
                                                or not cerebro.MODELO_OK.match(cer['modelo'])):
        _erro(f'{nome}.modelo: só letras, dígitos e .:/@_- (até 100, sem começar com -)')
    if cer.get('esforco') not in (None, '') and cer['esforco'] not in cerebro.ESFORCOS:
        _erro(f'{nome}.esforco deve ser ' + ', '.join(cerebro.ESFORCOS))
    if cer.get('url') not in (None, '') and (not isinstance(cer['url'], str)
                                             or not re.match(r'^https?://[^\s]+$', cer['url'])):
        _erro(f'{nome}.url deve começar com http:// ou https://')


def gravar_config(c, novo):
    cfg = validar_config(c, novo)
    c.salvar_cfg(cfg)
    c.sujo = True
    return config_publica(c)
