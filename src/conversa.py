"""Agente por regras: lead, conversa e qualificação (seções 4 e 5)."""
import json
import re

from .core import Erro, formatar_telefone, iso, normalizar, normalizar_telefone, novo_token, primeiro_nome
from . import cerebro, chamados, equipe, evolution

PARAR = ('parar', 'sair', 'pare')
APAGAR = 'apagar meus dados'
HUMANO = ('atendente', 'humano', 'falar com alguem', 'falar com uma pessoa', 'vendedor', 'me liga', 'me ligue',
          'ligacao')
VENDA = ('quero comprar', 'quero contratar', 'como faco para comprar', 'como faco para contratar', 'fechar',
         'quanto custa', 'qual o valor', 'qual o preco', 'forma de pagamento', 'parcela', 'orcamento')
PRECISA = ('reclamacao', 'reclamar', 'problema', 'nao funciona', 'defeito', 'cancelar', 'reembolso', 'absurdo',
           'pessimo', 'procon')
SIM = {'sim', 'quero', 'pode', 's', 'claro', 'ok', 'isso', 'bora', 'beleza', 'yes'}
NAO = {'nao', 'n', 'agora nao', 'depois'}
SAUDACOES = {'oi', 'ola', 'oie', 'oii', 'opa', 'e ai', 'eai', 'bom dia', 'boa tarde', 'boa noite', 'hey', 'hello',
             'alo', 'tudo bem', 'oi tudo bem'}
COMUNS = set('''a o as os um uma uns umas de da do das dos em na no nas nos ao aos e ou que qual quais como onde
quando para pra pro por com sem se seu sua seus suas meu minha meus minhas eu voce voces vcs ele ela eles elas nos
isso isto esse essa este esta aquele aquela tem ter mais menos muito pelo pela pelos pelas me te lhe vos ja nao sim
the and'''.split())
URG_OPCOES = '1 - Hoje / esta semana\n2 - Este mês\n3 - Só pesquisando'

SEM_TEXTO = 'Por enquanto só consigo ler mensagens de texto.'


def tem(t, termos):
    return any(normalizar(x) in t for x in termos)


# ---------- lead ----------
def obter_lead(c, telefone, criar=True):
    r = c.db.execute('SELECT * FROM leads WHERE telefone=?', (telefone,)).fetchone()
    if r or not criar:
        return r, False
    agora = iso(c.agora())
    ident = c.db.execute('INSERT INTO leads(token,telefone,status,nota,criado_em,ultimo_contato) VALUES (?,?,?,?,?,?)',
                         (novo_token(), telefone, 'novo', 'frio', agora, agora)).lastrowid
    return c.lead(ident), True


def lead_resumo(lead):
    return {'id': lead['id'], 'token': lead['token'], 'status': lead['status'], 'nota': lead['nota'],
            'nome': lead['nome'], 'interesse': lead['interesse'], 'nao_contatar': bool(lead['nao_contatar'])}


def lead_json(c, lead):
    d = dict(lead)
    d['nao_contatar'] = bool(d['nao_contatar'])
    d.pop('estado', None)
    d.pop('status_antes', None)
    return d


def estado(lead):
    try:
        e = json.loads(lead['estado'] or '{}')
        return e if isinstance(e, dict) else {}
    except ValueError:
        return {}


def gravar_estado(c, lead_id, e):
    c.db.execute('UPDATE leads SET estado=? WHERE id=?', (json.dumps(e, ensure_ascii=False), lead_id))


def registrar(c, lead_id, de, texto, chamado_id=None, autor=None):
    c.db.execute('INSERT INTO mensagens(lead_id,chamado_id,de,autor,texto,em) VALUES (?,?,?,?,?,?)',
                 (lead_id, chamado_id, de, autor, texto, iso(c.agora())))


def anonimizar(c, lead_id):
    lead = c.lead(lead_id)
    c.db.execute("UPDATE leads SET nome='apagado', telefone=?, push_name=NULL, estado='{}', interesse=NULL, "
                 'urgencia=NULL WHERE id=?', (f'apagado-{lead_id}', lead_id))
    c.db.execute('DELETE FROM mensagens WHERE lead_id=?', (lead_id,))
    c.db.execute('DELETE FROM saida WHERE lead_id=?', (lead_id,))
    for h in c.db.execute('SELECT id, dados FROM historico WHERE lead_id=?', (lead_id,)).fetchall():
        d = json.loads(h['dados'])
        d['nota'] = None
        c.db.execute('UPDATE historico SET dados=? WHERE id=?', (json.dumps(d, ensure_ascii=False), h['id']))
    c.db.execute('UPDATE chamados SET resumo=NULL, nota_fechamento=NULL WHERE lead_id=?', (lead_id,))
    c.sujo = True
    return lead['telefone']


# ---------- produtos e FAQ ----------
def casar_produto(c, t):
    for p in c.cfg.get('produtos', []):
        termos = list(p.get('palavras') or []) + [p.get('nome', '')]
        for termo in termos:
            n = normalizar(termo)
            if n and n in t:
                return p
    return None


def palavras_significativas(texto):
    return {w for w in normalizar(texto).split() if len(w) >= 3 and w not in COMUNS}


def casar_faq(c, t):
    palavras = set(t.split())
    melhor, resposta = 0.0, None
    for item in c.cfg.get('faq', []):
        for pergunta in item.get('perguntas') or []:
            pp = palavras_significativas(pergunta)
            if not pp:
                continue
            nota = len(pp & palavras) / len(pp)
            if nota >= 0.6 and nota > melhor:
                melhor, resposta = nota, item.get('resposta')
    return resposta


def opcoes_produtos(c):
    linhas = [f"{i} - {p['nome']}" for i, p in enumerate(c.cfg.get('produtos', []), 1)]
    return '\n'.join(linhas + ['0 - Outro assunto'])


def _numero(t):
    m = re.fullmatch(r'(?:opcao\s*)?(\d+)', t.strip())
    return int(m[1]) if m else None


def extrair_nome(texto):
    nome = re.sub(r'^\s*(meu nome (é|e)|me chamo|eu sou|sou o|sou a|sou|aqui é|aqui e|é o|é a)\s+', '', texto.strip(),
                  flags=re.I)
    nome = re.sub(r'[^\w\s\'-]', '', nome).strip()
    nome = ' '.join(nome.split())[:60]
    if nome and nome == nome.lower():
        nome = ' '.join(p.capitalize() for p in nome.split())
    return nome


# ---------- entrada ----------
def receber(c, telefone, texto, canal='web', nome=None, push_name=None):
    tel = normalizar_telefone(telefone)
    if not isinstance(texto, str) or not texto.strip():
        raise Erro(422, 'Texto obrigatório')
    if canal not in ('web', 'whatsapp'):
        canal = 'web'
    lead, _novo = obter_lead(c, tel)
    agora = iso(c.agora())
    c.db.execute('UPDATE leads SET ultimo_contato=?, canal=? WHERE id=?', (agora, canal, lead['id']))
    if isinstance(push_name, str) and push_name.strip():
        c.db.execute('UPDATE leads SET push_name=? WHERE id=?', (push_name.strip()[:60], lead['id']))
    if isinstance(nome, str) and nome.strip() and not lead['nome']:
        c.db.execute('UPDATE leads SET nome=? WHERE id=?', (nome.strip()[:80], lead['id']))
    lead = c.lead(lead['id'])
    t = normalizar(texto)
    primeiro = not c.db.execute("SELECT 1 FROM mensagens WHERE lead_id=? AND de='lead' LIMIT 1",
                                (lead['id'],)).fetchone()
    aberto = chamados.aberto_do_lead(c, lead['id'])
    registrar(c, lead['id'], 'lead', texto.strip(), aberto['id'] if aberto else None)

    if t == APAGAR:
        telefone_original = lead['telefone']
        anonimizar(c, lead['id'])
        resposta = 'Pronto: seus dados foram apagados. Obrigado pelo contato.'
        if canal == 'whatsapp':
            evolution.enviar_lead(c, c.lead(lead['id']), resposta, 'agente', telefone=telefone_original)
        return lead_resumo(c.lead(lead['id'])), [resposta]

    respostas = decidir(c, lead, texto.strip(), t, primeiro, aberto)
    lead = c.lead(lead['id'])
    aberto = chamados.aberto_do_lead(c, lead['id'])
    for r in respostas:
        registrar(c, lead['id'], 'agente', r, aberto['id'] if aberto else None)
        if canal == 'whatsapp':
            evolution.enviar_lead(c, lead, r, 'agente')
    return lead_resumo(lead), respostas


def sem_texto(c, telefone, push_name=None):
    lead, _ = obter_lead(c, telefone)
    if isinstance(push_name, str) and push_name.strip():
        c.db.execute('UPDATE leads SET push_name=? WHERE id=?', (push_name.strip()[:60], lead['id']))
    c.db.execute('UPDATE leads SET ultimo_contato=?, canal=? WHERE id=?', (iso(c.agora()), 'whatsapp', lead['id']))
    registrar(c, lead['id'], 'sistema', '[mensagem sem texto]')
    registrar(c, lead['id'], 'agente', SEM_TEXTO)
    evolution.enviar_lead(c, c.lead(lead['id']), SEM_TEXTO, 'agente')


def decidir(c, lead, texto, t, primeiro, aberto):
    lid = lead['id']
    # 1. parar
    if t in PARAR:
        c.db.execute('UPDATE leads SET nao_contatar=1 WHERE id=?', (lid,))
        return ['Tudo bem, você não vai mais receber mensagens automáticas. Se quiser voltar a falar, é só mandar '
                'uma mensagem.']
    if lead['nao_contatar']:
        c.db.execute('UPDATE leads SET nao_contatar=0 WHERE id=?', (lid,))
    # 3. em atendimento humano
    if aberto and aberto['status'] == 'atendendo':
        quem = lead['nome'] or formatar_telefone(lead['telefone'])
        ref = equipe.privado(c, aberto['dono'], f'💬 {quem}: {texto}')
        chamados.guardar_msg(c, ref, aberto['id'], 'lead')
        c.db.execute('UPDATE chamados SET ultimo_mov=?, lembrado=0 WHERE id=?', (iso(c.agora()), aberto['id']))
        return []
    # 4. chamado aguardando
    if aberto:
        return ['Eu já avisei a equipe; logo alguém fala com você por aqui.']
    e = estado(lead)
    # 5–7. pedidos que abrem chamado
    if tem(t, HUMANO):
        return _abrir(c, lid, 'pediu_humano')
    if tem(t, VENDA):
        c.db.execute("UPDATE leads SET nota='quente' WHERE id=?", (lid,))
        prod = casar_produto(c, t)
        prefixo = ''
        if prod:
            c.db.execute('UPDATE leads SET interesse=? WHERE id=?', (prod['id'], lid))
            if prod.get('preco'):
                prefixo = f"{prod['nome']}: {prod['preco']}. "
        return _abrir(c, lid, 'venda', prefixo)
    if tem(t, PRECISA):
        return _abrir(c, lid, 'precisa')
    # 8. qualificação em andamento
    etapa = e.get('etapa')
    if etapa:
        r = qualificar(c, c.lead(lid), e, texto, t)
        if r is not None:
            return r
        e = estado(c.lead(lid))
    # 9. FAQ
    resposta = casar_faq(c, t)
    if resposta is not None:
        _zerar_falhas(c, lid)
        return [resposta]
    # 10. interesse em produto
    prod = casar_produto(c, t)
    if prod:
        nota = c.lead(lid)['nota']
        c.db.execute('UPDATE leads SET interesse=?, nota=? WHERE id=?',
                     (prod['id'], nota if nota == 'quente' else 'morno', lid))
        lead = c.lead(lid)
        if not lead['nome']:
            return [f"Ótimo, {prod['nome']}! " + _pergunta_nome(c, lead, {'falhas': 0})]
        gravar_estado(c, lid, {'etapa': 'quer_falar', 'falhas': 0})
        preco = f" ({prod['preco']})" if prod.get('preco') else ''
        return [f"Temos o {prod['nome']}{preco}. Quer que eu chame alguém para te atender?"]
    # 11. primeiro contato
    if primeiro:
        lead = c.lead(lid)
        negocio = c.cfg.get('nome', '')
        if not lead['nome']:
            return [f'Olá! Aqui é o atendimento da {negocio}. ' + _pergunta_nome(c, lead, {'falhas': 0})]
        gravar_estado(c, lid, {'etapa': 'procura', 'falhas': 0})
        return [f"Olá, {primeiro_nome(lead['nome'])}! Aqui é o atendimento da {negocio}. "
                f"O que você procura?\n{opcoes_produtos(c)}"]
    # 12. não entendi
    duvida = cerebro.responder_duvida(c, texto)
    if duvida:
        _zerar_falhas(c, lid)
        return [duvida]
    falhas = int(e.get('falhas', 0)) + 1
    if falhas >= 2:
        gravar_estado(c, lid, {})
        return _abrir(c, lid, 'precisa', 'Desculpe, não entendi. ')
    gravar_estado(c, lid, {**e, 'falhas': falhas})
    return ['Desculpe, não entendi. Pode escrever de outro jeito ou pedir um atendente.']


def _zerar_falhas(c, lid):
    e = estado(c.lead(lid))
    if e.get('falhas'):
        e['falhas'] = 0
        gravar_estado(c, lid, e)


def _abrir(c, lid, motivo, prefixo=''):
    gravar_estado(c, lid, {})
    _ident, respostas = chamados.abrir(c, lid, motivo)
    respostas[0] = prefixo + respostas[0]
    return respostas


def _pergunta_nome(c, lead, e):
    if lead['push_name']:
        gravar_estado(c, lead['id'], {**e, 'etapa': 'confirma_nome'})
        return f"Posso te chamar de {lead['push_name']}?"
    gravar_estado(c, lead['id'], {**e, 'etapa': 'nome'})
    return 'Para começar, qual é o seu nome?'


def _apos_nome(c, lid, e):
    gravar_estado(c, lid, {**e, 'etapa': 'procura', 'falhas': 0})
    nome = primeiro_nome(c.lead(lid)['nome'])
    return [f'Prazer, {nome}! O que você procura?\n{opcoes_produtos(c)}']


def qualificar(c, lead, e, texto, t):
    """Consome a mensagem da etapa atual. None = etapa encerrada, segue as regras seguintes."""
    lid = lead['id']
    etapa = e.get('etapa')
    palavras = set(t.split())
    if etapa in ('nome', 'confirma_nome', 'procura', 'quando') and _numero(t) is None:
        # Pergunta do FAQ no meio da qualificação: responde e mantém a etapa (não vira nome/opção).
        faq = casar_faq(c, t)
        if faq is not None:
            return [faq]
        prod = casar_produto(c, t) if etapa in ('nome', 'confirma_nome') else None
        if prod and not (palavras & SIM):
            nota = lead['nota']
            c.db.execute('UPDATE leads SET interesse=?, nota=? WHERE id=?',
                         (prod['id'], nota if nota == 'quente' else 'morno', lid))
            return [f"Ótimo, {prod['nome']}! " + _pergunta_nome(c, c.lead(lid), e)]
    if etapa == 'confirma_nome':
        if palavras & SIM and not palavras & {'nao'}:
            c.db.execute('UPDATE leads SET nome=? WHERE id=?', (lead['push_name'], lid))
            return _apos_nome(c, lid, e)
        if t in NAO or (palavras & {'nao'} and len(palavras) <= 2):
            gravar_estado(c, lid, {**e, 'etapa': 'nome'})
            return ['Tudo bem. Qual é o seu nome?']
        etapa = 'nome'
    if etapa == 'nome':
        nome = extrair_nome(texto)
        if not nome or t in SAUDACOES:
            gravar_estado(c, lid, {**e, 'etapa': 'nome'})
            return ['Qual é o seu nome?']
        c.db.execute('UPDATE leads SET nome=? WHERE id=?', (nome, lid))
        return _apos_nome(c, lid, e)
    if etapa == 'procura':
        n = _numero(t)
        produtos = c.cfg.get('produtos', [])
        prod = None
        if n is not None and 1 <= n <= len(produtos):
            prod = produtos[n - 1]
        elif n is None:
            prod = casar_produto(c, t)
        if prod is None and n != 0:
            return [f'Não achei essa opção. Responda com o número:\n{opcoes_produtos(c)}']
        if prod:
            c.db.execute('UPDATE leads SET interesse=? WHERE id=?', (prod['id'], lid))
        gravar_estado(c, lid, {**e, 'etapa': 'quando', 'falhas': 0})
        return [f'Para quando você precisa?\n{URG_OPCOES}']
    if etapa == 'quando':
        n = _numero(t)
        if n not in (1, 2, 3):
            mapa = {'hoje': 1, 'semana': 1, 'mes': 2, 'pesquisando': 3}
            n = next((v for k, v in mapa.items() if k in palavras), None)
        if n == 1:
            c.db.execute("UPDATE leads SET urgencia=1, nota='quente' WHERE id=?", (lid,))
            return _abrir(c, lid, 'venda')
        if n == 2:
            c.db.execute("UPDATE leads SET urgencia=2, nota='morno' WHERE id=?", (lid,))
            gravar_estado(c, lid, {'etapa': 'quer_falar', 'falhas': 0})
            return ['Ótimo! Quer que eu chame alguém para te atender?']
        if n == 3:
            c.db.execute("UPDATE leads SET urgencia=3, nota='frio' WHERE id=?", (lid,))
            gravar_estado(c, lid, {'falhas': 0})
            return ['Sem problema. Se tiver qualquer dúvida, é só mandar mensagem por aqui.']
        return [f'Responda com o número:\n{URG_OPCOES}']
    if etapa == 'quer_falar':
        if 'nao' in palavras or t in NAO:
            gravar_estado(c, lid, {'falhas': 0})
            return ['Tudo bem! Se tiver qualquer dúvida, é só mandar mensagem por aqui.']
        if palavras & SIM:
            return _abrir(c, lid, 'venda')
        gravar_estado(c, lid, {'falhas': e.get('falhas', 0)})
        return None
    gravar_estado(c, lid, {})
    return None


# ---------- página do lead ----------
def falar(c, token):
    lead = c.lead_token(token)
    if lead['nao_contatar']:
        c.db.execute('UPDATE leads SET nao_contatar=0 WHERE id=?', (lead['id'],))
    aberto = chamados.aberto_do_lead(c, lead['id'])
    if aberto and aberto['status'] == 'atendendo':
        respostas = []
    elif aberto:
        respostas = ['Eu já avisei a equipe; logo alguém fala com você por aqui.']
    else:
        respostas = _abrir(c, lead['id'], 'pediu_humano')
    aberto = chamados.aberto_do_lead(c, lead['id'])
    for r in respostas:
        registrar(c, lead['id'], 'agente', r, aberto['id'] if aberto else None)
    return {'ok': True, 'respostas': respostas, 'chamado': aberto['id'] if aberto else None,
            'lead': lead_resumo(c.lead(lead['id']))}


def apagar(c, token):
    lead = c.lead_token(token)
    anonimizar(c, lead['id'])
    return {'ok': True, 'mensagem': 'Seus dados foram apagados.'}
