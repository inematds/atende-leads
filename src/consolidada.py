"""Base consolidada (seção 13b): o texto exato que a IA recebe, por seção, conflitos achados por regra (sem LLM),
exportar (Markdown/JSON) e importar (prévia do que muda; `aplicar` grava pela validação do PUT config, com backup)."""
import json
import re
import shutil
import time
import unicodedata

from .core import DIAS, Erro, normalizar
from . import base

DIA_NOMES = {'segunda': 'seg', 'seg': 'seg', 'terca': 'ter', 'ter': 'ter', 'quarta': 'qua', 'qua': 'qua',
             'quinta': 'qui', 'qui': 'qui', 'sexta': 'sex', 'sex': 'sex', 'sabado': 'sab', 'sab': 'sab',
             'domingo': 'dom', 'dom': 'dom'}
_DIA = r'(segunda|terca|quarta|quinta|sexta|sabado|domingo|seg|ter|qua|qui|sex|sab|dom)(?:-feira)?s?'
FAIXA_DIAS = re.compile(rf'(?<!\w){_DIA}\s*(?:a|ate|-|–)\s*{_DIA}(?!\w)')
UM_DIA = re.compile(r'(?<!\w)(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?s?(?!\w)')
NEGA = re.compile(r'(nao|exceto|menos|fechad\w*|sem)\W+(\w+\W+){0,3}$')
TODOS = re.compile(r'todos os dias|diariamente|todo dia|24 ?h|24 horas|7 dias por semana')
HORAS = re.compile(r'(?<![\d,.])(\d{1,2})(?:(h|:)(\d{2})?|h)?\s*(?:as|a|ate|-|–)\s*(\d{1,2})(?:(h|:)(\d{2})?|h)?(?![\d,])')
PRECO = re.compile(r'R\$\s?(\d[\d.]*(?:,\d{1,2})?)')


# ---------- leitura de horário em texto livre ----------
def _hhmm(h, m):
    h, m = int(h), int(m or 0)
    if h > 24 or m > 59:
        return None
    return f'{h:02d}:{m:02d}'


def _plano(texto):
    """Minúsculas sem acento, mantendo a pontuação (':' e '–' importam para horas)."""
    t = unicodedata.normalize('NFD', str(texto or '').lower())
    return ''.join(ch for ch in t if unicodedata.category(ch) != 'Mn')


def horario_do_texto(texto):
    """(dias citados: set, janela (ini, fim) ou None). Só lê o que estiver claro; nada → (set(), None)."""
    t = _plano(texto)
    dias = set()
    completo = bool(TODOS.search(t) or FAIXA_DIAS.search(t))  # afirma a semana toda, não só um dia
    if TODOS.search(t):
        dias = set(DIAS)
    for m in FAIXA_DIAS.finditer(t):
        a, b = DIAS.index(DIA_NOMES[m.group(1)]), DIAS.index(DIA_NOMES[m.group(2)])
        dias |= set(DIAS[a:b + 1] if a <= b else DIAS[a:] + DIAS[:b + 1])
    resto = FAIXA_DIAS.sub(' ', t)
    for m in UM_DIA.finditer(resto):
        if not NEGA.search(resto[:m.start()]):  # "não abrimos aos domingos"
            dias.add(DIA_NOMES[m.group(1)])
    janela = None
    for m in HORAS.finditer(t):
        if not (m.group(2) or m.group(5) or 'h' in m.group(0)):
            continue  # "1 a 3" sem h/: não é hora
        ini, fim = _hhmm(m.group(1), m.group(3)), _hhmm(m.group(4), m.group(6))
        if ini and fim:
            janela = (ini, '23:59' if fim == '24:00' else fim)
            break
    if re.search(r'24 ?h|24 horas', t) and not janela:
        janela = ('00:00', '23:59')
    return dias, janela, completo


def _janelas(c):
    hor = c.cfg.get('horarios') or {}
    return {d: [tuple(j) for j in (hor.get(d) or []) if j and len(j) == 2] for d in DIAS}


def divergencia_horario(c, texto):
    """Frase curta do que diverge entre o texto e os `horarios` cadastrados, ou None."""
    dias, janela, completo = horario_do_texto(texto)
    if not dias and not janela:
        return None
    jan = _janelas(c)
    abertos = {d for d in DIAS if jan[d]}
    probs = []
    if (completo and dias and dias != abertos) or (not completo and dias - abertos):
        probs.append('dias diferentes')
    alvo = dias or abertos
    if janela and any(jan[d] and jan[d] != [janela] for d in alvo):
        probs.append('horas diferentes')
    return ' e '.join(probs) if probs else None


# ---------- preço ----------
def _valor(txt):
    try:
        return float(txt.replace('.', '').replace(',', '.'))
    except ValueError:
        return None


def _precos_validos(c, p):
    vs = {_valor(PRECO.search(p['preco']).group(1))} if PRECO.search(str(p.get('preco') or '')) else set()
    if base.promocao_ativa(c, p) and PRECO.search(p['preco_promocao']):
        vs.add(_valor(PRECO.search(p['preco_promocao']).group(1)))
    return vs


def divergencia_preco(c, texto):
    """[(produto, valores citados)] quando o texto cita um produto e R$ que não batem com o cadastrado."""
    citados = {_valor(v) for v in PRECO.findall(texto or '')}
    citados.discard(None)
    if not citados:
        return []
    t = normalizar(texto)
    out = []
    for p in c.cfg.get('produtos') or []:
        validos = _precos_validos(c, p)
        if p.get('nome') and normalizar(p['nome']) in t and validos and not (citados & validos):
            out.append((p, sorted(citados)))
    return out


def _brl(v):
    s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return 'R$ ' + (s[:-3] if s.endswith(',00') else s)


def _fala_de_horario(c, alvo, txt):
    """FAQ de horário: a pergunta é sobre horário, ou a resposta traz uma janela de horas."""
    f = next((x for x in c.cfg.get('faq') or [] if f"faq:{x.get('id')}" == alvo), {})
    perg = normalizar(' '.join(f.get('perguntas') or []))
    return base.pergunta_horario(perg) or horario_do_texto(txt)[1] is not None


# ---------- conflitos ----------
def conflitos(c):
    out = []

    def add(tipo, alvo, msg):
        out.append({'tipo': tipo, 'alvo': alvo, 'mensagem': msg})
    ref_horario = base.horario_gerado(c)
    info = base.info(c)
    textos = [(f'info:{k}', f'Informação "{base.ROTULOS[k]}"', v) for k, v in info.items()
              if k in base.CAMPOS and isinstance(v, str) and v.strip()]
    textos += [(f"faq:{f.get('id')}", f"FAQ \"{' / '.join(f.get('perguntas') or [])[:60]}\"", f.get('resposta') or '')
               for f in c.cfg.get('faq') or []]
    for alvo, rotulo, txt in textos:
        if alvo == 'info:horario_atendimento' or (alvo.startswith('faq:') and _fala_de_horario(c, alvo, txt)):
            d = divergencia_horario(c, txt)
            if d:
                add('horario', alvo, f'{rotulo} diz "{txt[:120]}" — {d} do horário cadastrado ({ref_horario})')
        for p, vals in divergencia_preco(c, txt):
            add('preco', alvo, f"{rotulo} cita {', '.join(_brl(v) for v in vals)} para {p['nome']}; o cadastrado é "
                               f"{base.preco_vigente(c, p)}")
        if base.tem_bastidor(txt):
            add('bastidor', alvo, f'{rotulo} tem recado interno ("{base.BASTIDOR.search(txt).group(0)}…"): o cliente '
                                  'ouviria isso. Reescreva como texto para o cliente.')
    hoje = c.agora().strftime('%Y-%m-%d')
    for p in c.cfg.get('produtos') or []:
        ate = str(p.get('promocao_ate') or '')
        if str(p.get('preco_promocao') or '').strip() and ate and ate < hoje:
            add('promocao_vencida', f"produto:{p.get('id')}",
                f"Promoção de {p.get('nome')} ({p.get('preco_promocao')}) venceu em {ate[8:10]}/{ate[5:7]}/{ate[:4]}; "
                f"o agente já usa o preço normal ({p.get('preco') or 'sem preço'}). Apague ou renove a promoção.")
    faq = c.cfg.get('faq') or []
    por_perg, por_resp = {}, {}
    for f in faq:
        for q in f.get('perguntas') or []:
            por_perg.setdefault(normalizar(q), []).append(f)
        por_resp.setdefault(normalizar(f.get('resposta') or ''), []).append(f)
    vistos = set()
    for q, fs in por_perg.items():
        resps = {normalizar(f.get('resposta') or '') for f in fs}
        ids = tuple(sorted({f.get('id') for f in fs}))
        if q and len(ids) > 1 and len(resps) > 1 and ids not in vistos:
            vistos.add(ids)
            add('faq_contraditoria', f'faq:{ids[1]}', f'A pergunta "{q}" aparece em {", ".join(ids)} com respostas diferentes.')
    for r, fs in por_resp.items():
        ids = [f.get('id') for f in fs]
        if r and len(ids) > 1:
            add('faq_duplicada', f'faq:{ids[1]}', f'{", ".join(ids)} têm a mesma resposta: junte as perguntas num item só.')
    return out


# ---------- leitura, exportar, importar ----------
def _produtos(c):
    return [{'id': p.get('id'), 'nome': p.get('nome'), 'preco': p.get('preco') or '',
             'preco_vigente': base.preco_vigente(c, p), 'preco_promocao': p.get('preco_promocao') or '',
             'promocao': p.get('promocao') or '', 'promocao_ate': p.get('promocao_ate') or '',
             'promocao_ativa': base.promocao_ativa(c, p)} for p in c.cfg.get('produtos') or []]


def ler(c):
    info = base.info(c)
    return {'texto': base.texto_base(c),
            'secoes': {'negocio': c.cfg.get('nome', ''), 'horario': base.texto_horario(c),
                       'horario_gerado': base.horario_gerado(c),
                       'info': {k: info.get(k) or '' for k in base.CAMPOS[1:]},
                       'faq': [{'id': f.get('id'), 'perguntas': f.get('perguntas') or [], 'resposta': f.get('resposta') or ''}
                               for f in c.cfg.get('faq') or []],
                       'produtos': _produtos(c)},
            'conflitos': conflitos(c)}


def exportar_json(c):
    return {'versao': 1, 'negocio': c.cfg.get('nome', ''), 'info': dict(base.info(c)),
            'faq': [dict(f) for f in c.cfg.get('faq') or []], 'produtos': [dict(p) for p in c.cfg.get('produtos') or []]}


def exportar_md(c):
    d = ler(c)
    s = d['secoes']
    l = [f"# Base de conhecimento — {s['negocio']}", '', '## Horário', '', s['horario'], '', '## Informações', '']
    l += [f"- **{base.ROTULOS[k]}:** {v}" for k, v in s['info'].items() if v] or ['(nenhuma)']
    l += ['', '## Perguntas frequentes', '']
    for f in s['faq']:
        l += [f"### {' / '.join(f['perguntas'])}", '', f['resposta'], '']
    if not s['faq']:
        l += ['(nenhuma)', '']
    l += ['## Produtos', '']
    for p in s['produtos']:
        extra = f" (normal {p['preco']})" if p['promocao_ativa'] and p['preco'] else ''
        l.append(f"- **{p['nome']}** (`{p['id']}`): {p['preco_vigente'] or 'sem preço informado'}{extra}")
    if d['conflitos']:
        l += ['', '## Conflitos encontrados', ''] + [f"- {x['mensagem']}" for x in d['conflitos']]
    l += ['', '---', '', 'Texto exato que a IA recebe:', '', '```', d['texto'], '```', '']
    return '\n'.join(l)


def _diff(c, novo):
    mud = []
    info_a, info_n = base.info(c), novo.get('info')
    if isinstance(info_n, dict):
        for k in sorted(set(info_a) | set(info_n)):
            a, b = info_a.get(k) or '', info_n.get(k) or ''
            if a != b:
                mud.append({'onde': f'info.{k}', 'antes': a, 'depois': b})
    for nome in ('faq', 'produtos'):
        if not isinstance(novo.get(nome), list):
            continue
        ant = {x.get('id'): x for x in c.cfg.get(nome) or [] if isinstance(x, dict)}
        nov = {x.get('id'): x for x in novo[nome] if isinstance(x, dict)}
        for i in list(ant) + [i for i in nov if i not in ant]:
            a, b = ant.get(i), nov.get(i)
            if a != b:
                mud.append({'onde': f'{nome}.{i}', 'antes': json.dumps(a, ensure_ascii=False) if a else '',
                            'depois': json.dumps(b, ensure_ascii=False) if b else ''})
    return mud


def importar(c, b, aplicar=False):
    """Prévia (`mudancas`) do JSON exportado; com `aplicar` grava info/faq/produtos pela validação do PUT config."""
    from . import gestao
    if not isinstance(b, dict) or not any(k in b for k in ('info', 'faq', 'produtos')):
        raise Erro(422, 'JSON da base: objeto com info, faq e/ou produtos (o mesmo formato do base.json)')
    novo = {k: b[k] for k in ('info', 'faq', 'produtos') if k in b}
    gestao.validar_config(c, novo)  # 422 sem gravar se algo estiver inválido
    mud = _diff(c, novo)
    if not aplicar or not mud:
        return {'ok': True, 'aplicado': False, 'mudancas': mud}
    arq = c.pasta / 'negocio.json'
    bak = arq.with_name(f"negocio.json.{time.strftime('%Y%m%d-%H%M%S')}.bak")
    shutil.copy2(arq, bak)
    bak.chmod(0o600)
    gestao.gravar_config(c, novo)
    return {'ok': True, 'aplicado': True, 'mudancas': mud, 'backup': bak.name}
