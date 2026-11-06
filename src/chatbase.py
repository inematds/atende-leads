"""Chat da base (seção 13b, 1.7.8): o gestor pergunta e a resposta vem SÓ do que está na base, com a seção citada.

Com cérebro LLM (o principal, rápido): saída JSON {resposta, fontes:[{secao, trecho}], lacuna, contradicao,
proposta} (json_schema no anthropic; leitura tolerante nos outros). Sem LLM: busca por palavras, como o FAQ, e
devolve os trechos que casam. Falta na base → `lacuna: true` + rascunho de proposta (o front abre o formulário).
Contradição → os conflitos da Base consolidada ligados às seções citadas. Nada é gravado (histórico só na tela).
"""
from .core import Erro, normalizar
from . import base, cerebro, consolidada
from .conversa import casar_produto, palavras_significativas

NAO_ESTA = 'Isso não está na base.'
TIPOS_PROP = ('faq', 'info', 'produto', 'preco')
_STR = {'type': 'string'}
SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'required': ['resposta', 'fontes', 'lacuna', 'contradicao', 'proposta'],
    'properties': {
        'resposta': _STR,
        'fontes': {'type': 'array', 'items': {'type': 'object', 'additionalProperties': False,
                                              'required': ['secao', 'trecho'],
                                              'properties': {'secao': _STR, 'trecho': _STR}}},
        'lacuna': {'type': 'boolean'}, 'contradicao': _STR,
        'proposta': {'type': 'object', 'additionalProperties': False,
                     'required': ['tipo', 'perguntas', 'resposta', 'campo', 'nome', 'preco_novo', 'produto_id'],
                     'properties': {'tipo': {'type': 'string', 'enum': ['', *TIPOS_PROP]},
                                    'perguntas': {'type': 'array', 'items': _STR}, 'resposta': _STR, 'campo': _STR,
                                    'nome': _STR, 'preco_novo': _STR, 'produto_id': _STR}},
    },
}
INSTR = (
    'Você responde ao GESTOR de {nome}, que está conferindo a base de conhecimento do atendimento (abaixo). '
    'Responda SÓ com o que está na base, em português do Brasil, curto e direto, texto simples. Nunca complete com '
    'conhecimento geral nem invente.\n'
    'Em "fontes", cite cada parte da base usada: "secao" = "Produtos", "FAQ: <pergunta do item>", "Informações: '
    '<campo>" (endereco, pagamento, entrega, garantia, site, observacoes, horario_atendimento) ou "Horários"; '
    '"trecho" = o texto da base.\n'
    'Se a base não responde, a resposta começa com "Isso não está na base." , "lacuna": true e, em "proposta", o '
    'item que faltaria (tipo faq|info|produto|preco; "perguntas" com a pergunta do gestor; "resposta" vazia se a base '
    'não traz o fato — nunca invente). Sem lacuna: proposta com tipo "".\n'
    'Se a base se contradiz sobre o assunto (ex.: o FAQ diz um horário e os Horários outro), descreva em '
    '"contradicao" (senão ""). Conflitos já achados pelas regras:\n{conflitos}\n'
    'Responda SOMENTE com JSON {{"resposta", "fontes", "lacuna", "contradicao", "proposta"}}.')


def _rotulo_info(campo):
    return {'horario_atendimento': 'Horário de atendimento'}.get(campo) or base.ROTULOS.get(campo) or campo


def _trechos(c):
    """Pedaços da base: (secao, trecho, texto para busca, alvo do conflito)."""
    out = [('Horários', base.texto_horario(c), 'horario horarios atendimento abre fecha funcionamento expediente',
            'horario')]
    for k in base.CAMPOS:
        v = base.campo(c, k)
        if v and k != 'horario_atendimento':
            out.append((f'Informações: {k}', v, f'{_rotulo_info(k)} {k} {v}', f'info:{k}'))
    for f in c.cfg.get('faq') or []:
        perg = f.get('perguntas') or []
        out.append((f"FAQ: {perg[0] if perg else f.get('id')}", f.get('resposta') or '',
                    ' '.join(perg) + ' ' + (f.get('resposta') or ''), f"faq:{f.get('id')}"))
    for p in c.cfg.get('produtos') or []:
        pv = base.preco_vigente(c, p)
        out.append(('Produtos', f"{p.get('nome')}: {pv or 'sem preço informado'}",
                    f"{p.get('nome')} {' '.join(p.get('palavras') or [])} preco valor custa", f"produto:{p.get('id')}"))
    return out


def _alvo_da_secao(c, secao, trecho):
    s = normalizar(secao)
    if s.startswith('faq'):
        resto = normalizar(secao.split(':', 1)[1] if ':' in secao else '')
        for f in c.cfg.get('faq') or []:
            if any(normalizar(x) == resto or (resto and resto in normalizar(x)) for x in f.get('perguntas') or []):
                return f"faq:{f.get('id')}"
            if normalizar(trecho) and normalizar(trecho) == normalizar(f.get('resposta') or ''):
                return f"faq:{f.get('id')}"
    if s.startswith('informac'):
        for k in base.CAMPOS:
            if k in s.replace(' ', '_') or normalizar(_rotulo_info(k)) in s:
                return f'info:{k}'
    if s.startswith('produto'):
        t = normalizar(trecho)
        for p in c.cfg.get('produtos') or []:
            if p.get('nome') and normalizar(p['nome']) in t:
                return f"produto:{p.get('id')}"
    if s.startswith('horario'):
        return 'horario'
    return None


def _conflitos_ligados(c, alvos):
    out = []
    for i, x in enumerate(consolidada.conflitos(c)):
        if x['alvo'] in alvos or (x['tipo'] == 'horario' and 'horario' in alvos):
            out.append(dict(x, indice=i))
    return out


def por_regras(c, pergunta):
    t = normalizar(pergunta)
    pp = palavras_significativas(pergunta)
    achados = []
    for secao, trecho, busca, alvo in _trechos(c):
        if alvo == 'horario' and base.pergunta_horario(t):
            achados.append((1.0, secao, trecho, alvo))
            continue
        if alvo.startswith('produto:'):
            prod = casar_produto(c, t)
            if prod and alvo == f"produto:{prod['id']}":
                achados.append((1.0, secao, trecho, alvo))
                continue
        if not pp:
            continue
        nota = len(pp & palavras_significativas(busca)) / len(pp)
        if nota >= 0.34:
            achados.append((nota, secao, trecho, alvo))
    achados.sort(key=lambda x: -x[0])
    achados = achados[:4]
    fontes = [{'secao': s, 'trecho': tr} for _n, s, tr, _a in achados]
    if not fontes:
        return {'resposta': f'{NAO_ESTA} Não achei nada sobre isso nas informações, no FAQ, nos produtos nem nos horários.',
                'fontes': [], 'lacuna': True, 'contradicao': '',
                'proposta': {'tipo': 'faq', 'perguntas': [pergunta.strip()[:200]], 'resposta': ''},
                'conflitos': [], 'origem': 'regras'}
    alvos = {a for _n, _s, _t, a in achados}
    return {'resposta': 'Encontrei na base:\n' + '\n'.join(f'• {f["secao"]} — {f["trecho"]}' for f in fontes),
            'fontes': fontes, 'lacuna': False, 'contradicao': '', 'proposta': None,
            'conflitos': _conflitos_ligados(c, alvos), 'origem': 'regras'}


def _proposta(p, pergunta):
    if not isinstance(p, dict) or p.get('tipo') not in TIPOS_PROP:
        return {'tipo': 'faq', 'perguntas': [pergunta.strip()[:200]], 'resposta': ''}
    out = {'tipo': p['tipo']}
    perg = [str(x).strip()[:200] for x in (p.get('perguntas') or []) if isinstance(x, str) and x.strip()][:5]
    out['perguntas'] = perg or [pergunta.strip()[:200]]
    for k in ('resposta', 'campo', 'nome', 'preco_novo', 'produto_id'):
        v = p.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:2000]
    if base.tem_bastidor(out.get('resposta')):
        out['resposta'] = ''
    return out


def perguntar(c, b):
    pergunta = b.get('pergunta') if isinstance(b, dict) else None
    if not isinstance(pergunta, str) or not pergunta.strip():
        raise Erro(422, 'pergunta obrigatória')
    if len(pergunta) > 1000:
        raise Erro(422, 'pergunta até 1000 caracteres')
    hist = b.get('historico') or []
    if not isinstance(hist, list):
        raise Erro(422, 'historico deve ser lista')
    if not cerebro.ligado(c):
        return por_regras(c, pergunta)
    conf = consolidada.conflitos(c)
    instr = INSTR.format(nome=c.cfg.get('nome') or 'o negócio',
                         conflitos='\n'.join(f"- [{x['alvo']}] {x['mensagem']}" for x in conf) or '(nenhum)')
    linhas = []
    for h in hist[-6:]:
        if isinstance(h, dict) and isinstance(h.get('texto'), str):
            quem = 'Gestor' if h.get('de') == 'gestor' else 'Resposta'
            linhas.append(f"{quem}: {h['texto'][:600]}")
    usuario = (('Conversa até aqui:\n' + '\n'.join(linhas) + '\n\n') if linhas else '') + f'Pergunta do gestor: {pergunta.strip()}'
    r = cerebro.perguntar(c, instr, usuario, base.texto_base(c), formato=SCHEMA, limpar=False)
    if not r:
        out = por_regras(c, pergunta)
        out['aviso'] = 'O cérebro não respondeu; busca por palavras.'
        return out
    d = cerebro.ler_json(r)
    if not isinstance(d, dict) or not isinstance(d.get('resposta'), str):
        return {'resposta': cerebro.limpar_md(r.strip()), 'fontes': [], 'lacuna': NAO_ESTA.lower() in r.lower(),
                'contradicao': '', 'proposta': None, 'conflitos': [], 'origem': 'cerebro'}
    fontes = []
    for f in d.get('fontes') or []:
        if isinstance(f, dict) and isinstance(f.get('secao'), str) and f['secao'].strip():
            fontes.append({'secao': f['secao'].strip()[:200], 'trecho': str(f.get('trecho') or '').strip()[:600]})
    fontes = fontes[:10]
    lacuna = bool(d.get('lacuna')) or d['resposta'].strip().lower().startswith(NAO_ESTA.lower()[:-1])
    resposta = cerebro.limpar_md(d['resposta'].strip())
    if lacuna and NAO_ESTA.lower()[:-1] not in resposta.lower():
        resposta = f'{NAO_ESTA} {resposta}'.strip()
    contradicao = str(d.get('contradicao') or '').strip()[:500]
    alvos = {a for a in (_alvo_da_secao(c, f['secao'], f['trecho']) for f in fontes) if a}
    ligados = _conflitos_ligados(c, alvos)
    return {'resposta': resposta, 'fontes': fontes, 'lacuna': lacuna, 'contradicao': contradicao,
            'proposta': _proposta(d.get('proposta'), pergunta) if lacuna else None,
            'conflitos': ligados, 'origem': 'cerebro'}
