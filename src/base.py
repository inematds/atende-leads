"""Base de conhecimento (seções 2, 4a e 14): informações do negócio (`info`), respostas automáticas e o
texto da base que o cérebro LLM recebe como contexto."""
import re

from .core import DIAS, ddmm_hhmm, normalizar
from . import horario

CAMPOS = ('horario_atendimento', 'endereco', 'pagamento', 'entrega', 'garantia', 'site', 'observacoes')
ROTULOS = {'horario_atendimento': 'Horário de atendimento humano', 'endereco': 'Endereço',
           'pagamento': 'Formas de pagamento', 'entrega': 'Entrega', 'garantia': 'Garantia e trocas',
           'site': 'Site', 'observacoes': 'Observações'}
DIA_NOME = {'seg': 'seg', 'ter': 'ter', 'qua': 'qua', 'qui': 'qui', 'sex': 'sex', 'sab': 'sáb', 'dom': 'dom'}


def info(c):
    i = c.cfg.get('info')
    return i if isinstance(i, dict) else {}


def campo(c, nome):
    v = info(c).get(nome)
    return v.strip() if isinstance(v, str) and v.strip() else ''


# ---------- horário ----------
def horario_gerado(c):
    """'Nosso atendimento: seg a sex 08:00–18:00; sáb 09:00–13:00.' a partir de `horarios`."""
    hor = c.cfg.get('horarios') or {}

    def janelas(d):
        return ' e '.join(f'{a}–{b}' for a, b in (hor.get(d) or []) if a and b)
    grupos = []  # [(primeiro, último, texto)]
    for d in DIAS:
        j = janelas(d)
        if not j:
            continue
        if grupos and grupos[-1][2] == j and DIAS.index(grupos[-1][1]) == DIAS.index(d) - 1:
            grupos[-1] = (grupos[-1][0], d, j)
        else:
            grupos.append((d, d, j))
    if not grupos:
        return 'No momento não temos horário de atendimento definido.'
    partes = []
    for a, b, j in grupos:
        dias = DIA_NOME[a] if a == b else (f'{DIA_NOME[a]} e {DIA_NOME[b]}' if DIAS.index(b) == DIAS.index(a) + 1
                                          else f'{DIA_NOME[a]} a {DIA_NOME[b]}')
        partes.append(f'{dias} {j}')
    return 'Nosso atendimento: ' + '; '.join(partes) + '.'


def texto_horario(c):
    return campo(c, 'horario_atendimento') or horario_gerado(c)


def agora_status(c):
    agora = c.agora()
    if horario.no_horario(c, agora):
        return 'Agora estamos atendendo.'
    prox = horario.proximo_inicio(c, agora)
    return f'Agora estamos fora do horário; voltamos {ddmm_hhmm(prox)}.' if prox else 'Agora estamos fora do horário.'


# ---------- detectores (texto já normalizado) ----------
def _re(*termos):
    return re.compile(r'(?<!\w)(' + '|'.join(termos) + r')(?!\w)')


HORARIO = _re(r'horarios?', r'que horas?', r'ate que horas?', r'expediente', r'funcionamento', r'abre', r'abrem',
              r'fecha', r'fecham', r'aberto', r'abertos', r'aberta')
DISPONIVEL = _re(r'tem alguem', r'alguem ai', r'estao atendendo', r'esta atendendo', r'tem atendimento',
                 r'atendendo agora', r'tem gente')
PEDIDO = _re(r'quero', r'preciso', r'falar com', r'me liga', r'me ligue', r'ligacao', r'chama', r'chamar', r'chame')
PAGAMENTO = _re(r'formas? de pagamento', r'pagamento', r'pix', r'cartao', r'cartoes', r'boleto', r'parcelar',
                r'parcelamento', r'parcelas?', r'aceitam', r'aceita', r'como pago', r'pagar')
TEMAS = (
    ('endereco', _re(r'endereco', r'onde fica', r'onde ficam', r'onde voces ficam', r'onde e a loja',
                     r'localizacao', r'como chego', r'onde estao'), 'Endereço'),
    ('entrega', _re(r'entregas?', r'entregam', r'entrega\w*', r'frete', r'envio', r'enviam', r'retirada',
                    r'retirar', r'delivery'), 'Entrega'),
    ('garantia', _re(r'garantia', r'trocas?', r'trocar', r'devolucao', r'devolver'), 'Garantia e trocas'),
    ('site', _re(r'site', r'website'), 'Site'),
)


def pergunta_horario(t):
    if PEDIDO.search(t):
        return False
    return bool(HORARIO.search(t) or DISPONIVEL.search(t))


def resposta_horario(c, t, faq=None):
    """Regra 4a: info → texto + agora; FAQ que casar → exato; senão gerado + agora."""
    if campo(c, 'horario_atendimento'):
        return f"{campo(c, 'horario_atendimento')} {agora_status(c)}"
    if faq is not None:
        return faq
    return f'{horario_gerado(c)} {agora_status(c)}'


def prefixo_pagamento(c):
    p = campo(c, 'pagamento')
    return f'Formas de pagamento: {p}. ' if p else ''


def resposta_info(c, t):
    """Regra 7a: endereço, pagamento, entrega, garantia, site — só com o campo preenchido."""
    if campo(c, 'pagamento') and PAGAMENTO.search(t):
        return f"Formas de pagamento: {campo(c, 'pagamento')}"
    for nome, rx, rotulo in TEMAS:
        if campo(c, nome) and rx.search(t):
            return f'{rotulo}: {campo(c, nome)}'
    return None


# ---------- preço vigente (promoção com validade) ----------
def promocao_ativa(c, p):
    """Promoção do produto vale se tem `preco_promocao` e (sem `promocao_ate` ou hoje ≤ `promocao_ate`)."""
    if not isinstance(p, dict) or not str(p.get('preco_promocao') or '').strip():
        return False
    ate = str(p.get('promocao_ate') or '').strip()
    return not ate or c.agora().strftime('%Y-%m-%d') <= ate


def preco_vigente(c, p):
    """O preço que o agente e o cérebro dizem: o promocional dentro da validade, senão o normal ('' se nenhum)."""
    if promocao_ativa(c, p):
        ate = str(p.get('promocao_ate') or '').strip()
        rotulo = str(p.get('promocao') or '').strip() or 'promoção'
        sufixo = f' até {ate[8:10]}/{ate[5:7]}' if len(ate) == 10 else ''
        return f"{p['preco_promocao'].strip()} ({rotulo}{sufixo})"
    v = p.get('preco') if isinstance(p, dict) else None
    return v.strip() if isinstance(v, str) else ''


# ---------- bastidores (recado interno que nunca vai para a base nem ao cliente) ----------
BASTIDOR = re.compile(r'vendedor(a)? (informou|disse|falou|passou)|a base (atual )?(diz|mostra|informa)|'
                      r'confirmar com a equipe|segundo o vendedor|base de conhecimento|informa[cç][aã]o interna',
                      re.I)


def tem_bastidor(texto):
    return bool(BASTIDOR.search(texto or ''))


# ---------- base para o cérebro ----------
def texto_base(c):
    linhas = [f"Negócio: {c.cfg.get('nome', '')}", f'{ROTULOS["horario_atendimento"]}: {texto_horario(c)}']
    for nome in CAMPOS[1:]:
        if campo(c, nome):
            linhas.append(f'{ROTULOS[nome]}: {campo(c, nome)}')
    faq = c.cfg.get('faq') or []
    if faq:
        linhas.append('\nPerguntas frequentes:')
        for f in faq:
            linhas.append(f"P: {' / '.join(f.get('perguntas') or [])}\nR: {f.get('resposta', '')}")
    prods = c.cfg.get('produtos') or []
    if prods:
        linhas.append('\nProdutos:')
        for p in prods:
            pv = preco_vigente(c, p)
            linhas.append(f"- {p.get('nome')}" + (f' — preço {pv}' if pv else ' — sem preço informado'))
    return '\n'.join(linhas)


INSTRUCOES = ('Você é o atendente virtual de {nome}. Responda em português do Brasil, de forma curta e cordial. '
              'Use SOMENTE a base de conhecimento abaixo. Nunca invente preço, prazo, condição, endereço ou horário '
              'que não esteja nela. Se a base não responder, diga que vai chamar alguém da equipe.')


def instrucoes(c):
    return INSTRUCOES.format(nome=c.cfg.get('nome') or 'uma empresa')


def sugestao_regras(c, texto):
    """Sem cérebro LLM: a resposta da 4a/7a ou do FAQ que casar; senão None."""
    from .conversa import casar_faq
    t = normalizar(texto)
    faq = casar_faq(c, t)
    if pergunta_horario(t):
        return resposta_horario(c, t, faq)
    return resposta_info(c, t) or faq
