"""Agente por regras: lead, conversa e qualificação (seções 4 e 5)."""
import json
import re
import secrets

from .core import Erro, formatar_telefone, iso, normalizar, normalizar_telefone, novo_token, primeiro_nome
from . import base, cerebro, chamados, equipe, evolution, sugestao

PARAR = ('parar', 'sair', 'pare')
APAGAR = 'apagar meus dados'
HUMANO = ('atendente', 'humano', 'falar com alguem', 'falar com uma pessoa', 'vendedor', 'me liga', 'me ligue',
          'ligacao')
VENDA = ('quero comprar', 'quero contratar', 'como faco para comprar', 'como faco para contratar', 'quero fechar',
         'fechar negocio', 'fechar o pedido', 'fechar a compra', 'quanto custa', 'qual o valor', 'qual o preco', 'forma de pagamento', 'parcela', 'orcamento')
PRECISA = ('reclamacao', 'reclamar', 'problema', 'nao funciona', 'defeito', 'cancelar', 'reembolso', 'absurdo',
           'pessimo', 'procon')
SIM = {'sim', 'quero', 'pode', 's', 'claro', 'ok', 'isso', 'bora', 'beleza', 'yes'}
NAO = {'nao', 'n', 'agora nao', 'depois'}
NAO_SEI = 'Essa eu não sei responder com certeza.'
SAUDACOES = {'oi', 'ola', 'oie', 'oii', 'opa', 'e ai', 'eai', 'bom dia', 'boa tarde', 'boa noite', 'hey', 'hello',
             'alo', 'tudo bem', 'oi tudo bem'}
COMUNS = set('''a o as os um uma uns umas de da do das dos em na no nas nos ao aos e ou que qual quais como onde
quando para pra pro por com sem se seu sua seus suas meu minha meus minhas eu voce voces vcs ele ela eles elas nos
isso isto esse essa este esta aquele aquela tem ter mais menos muito pelo pela pelos pelas me te lhe vos ja nao sim
the and'''.split())
URG_OPCOES = '1 - Hoje / esta semana\n2 - Este mês\n3 - Só pesquisando'

SEM_TEXTO = 'Por enquanto só consigo ler mensagens de texto.'
# 1.10.8: agradecimento e confirmação têm resposta própria (não contam como "não sei")
AGRADECE = {'obrigado', 'obrigada', 'obg', 'brigado', 'brigada', 'valeu', 'vlw', 'agradeco', 'muito obrigado',
            'muito obrigada', 'obrigado mesmo', 'obrigada mesmo', 'gratidao', 'grato', 'grata', 'valeu mesmo'}
CONFIRMA = {'', 'ok', 'okay', 'blz', 'beleza', 'ta bom', 'ta', 'certo', 'entendi', 'show', 'top', 'perfeito',
            'combinado', 'tudo bem', 'tudo certo', 'ah ta', 'hum', 'humm', 'sei', 'otimo', 'legal', 'massa', 'joia',
            'ok obrigado', 'ok obrigada', 'certo obrigado', 'certo obrigada', 'ta obrigado', 'ta obrigada'}
# 1.10.8: no chamado silencioso, só um pedido de pessoa tira o silêncio ("é para alguém da família" não é pedido)
PEDE_ALGUEM = re.compile(r'\b(tem|ha|cade) (alguem|ninguem|uma pessoa|atendente)( (ai|ae|ai mesmo|online|por ai|de verdade))?$'
                         r'|\bninguem (me |vai )?(responde|atende)'
                         r'|\bfalar com (alguem|uma pessoa|gente|atendente|humano|vendedor)\b'
                         r'|\balguem (ai|ae|de verdade|real|me atende|pode me atender|pra me atender|para me atender)\b'
                         r'|^(alguem|ninguem|ola alguem|oi alguem)$')


NEGACAO_1 = {'sem', 'nenhum', 'nenhuma'}
NEGACAO_2 = {('nao', 'tem'), ('nao', 'ha'), ('nao', 'e'), ('nao', 'foi'), ('nao', 'teve')}


def tem(t, termos):
    return any(normalizar(x) in t for x in termos)


def negado(antes):
    """As até 2 palavras antes do termo negam? ('sem problema', 'nenhum problema', 'não tem problema')."""
    ws = antes.split()[-3:]
    if any(w in NEGACAO_1 for w in ws[-2:]):
        return True
    return len(ws) >= 2 and tuple(ws[-2:]) in NEGACAO_2 or (len(ws) >= 3 and tuple(ws[-3:-1]) in NEGACAO_2)


def tem_palavra(t, termos):
    """Termo como palavra/expressão inteira (aceita plural com 's'), ignorando a forma negada simples."""
    for termo in termos:
        n = normalizar(termo)
        if not n:
            continue
        for m in re.finditer(rf'(?<!\w){re.escape(n)}s?(?!\w)', t):
            if n.startswith('nao ') or not negado(t[:m.start()]):
                return True
    return False


# ---------- lead ----------
def obter_lead(c, telefone, criar=True):
    """Lead do WhatsApp: identidade = telefone (nunca mistura com leads do chat web)."""
    r = c.db.execute('SELECT * FROM leads WHERE telefone=? AND sessao IS NULL', (telefone,)).fetchone()
    if r or not criar:
        return r, False
    agora = iso(c.agora())
    ident = c.db.execute('INSERT INTO leads(token,telefone,status,nota,criado_em,ultimo_contato) VALUES (?,?,?,?,?,?)',
                         (novo_token(), telefone, 'novo', 'frio', agora, agora)).lastrowid
    return c.lead(ident), True


def novo_lead_web(c, telefone):
    """Chat web: cada sessão é um lead novo; o telefone digitado é só dado de contato."""
    agora = iso(c.agora())
    ident = c.db.execute('INSERT INTO leads(token,telefone,status,nota,criado_em,ultimo_contato,sessao,canal) '
                         'VALUES (?,?,?,?,?,?,?,?)',
                         (novo_token(), telefone, 'novo', 'frio', agora, agora, secrets.token_urlsafe(24), 'web')
                         ).lastrowid
    return c.lead(ident)


def lead_sessao(c, sessao):
    r = c.db.execute('SELECT * FROM leads WHERE sessao=?', (str(sessao),)).fetchone() if sessao else None
    if not r:
        raise Erro(404, 'Sessão inexistente')
    return r


def mensagens_web(c, sessao):
    """Chat web consulta as respostas da equipe pela própria sessão."""
    lead = lead_sessao(c, sessao)
    # Avisos ao lead ("Ana vai te atender agora.", "Combinado! ...") saem pela caixa de saída com tipo `aviso`:
    # marcados aqui para o chat web mostrá-los (as respostas do agente ele já mostra na hora).
    avisos = {r['texto'] for r in c.db.execute("SELECT texto FROM saida WHERE lead_id=? AND tipo='aviso'",
                                                (lead['id'],))}
    msgs = [{'de': r['de'], 'texto': r['texto'], 'em': r['em'],
             'tipo': 'aviso' if r['de'] == 'agente' and r['texto'] in avisos else r['de']} for r in
            c.db.execute("SELECT de, texto, em FROM mensagens WHERE lead_id=? ORDER BY id DESC LIMIT 50", (lead['id'],))]
    from . import paginas
    _t, colab, _r = paginas.status_lead(c, lead)
    return {'lead': lead_resumo(lead), 'colaborador': colab, 'mensagens': list(reversed(msgs))}


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
    chamados.encerrar_por_apagar(c, lead_id)
    c.db.execute("UPDATE leads SET nome='apagado', telefone=?, push_name=NULL, estado='{}', interesse=NULL, "
                 'urgencia=NULL WHERE id=?', (f'apagado-{lead_id}', lead_id))
    c.db.execute('DELETE FROM mensagens WHERE lead_id=?', (lead_id,))
    c.db.execute('DELETE FROM saida WHERE lead_id=?', (lead_id,))
    c.db.execute('DELETE FROM sugestoes WHERE lead_id=?', (lead_id,))  # textos do lead e da equipe
    c.db.execute('DELETE FROM aprendizado WHERE lead_id=?', (lead_id,))
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



def _duvida_em_espera(c, t, texto, lid=None):
    """Resposta a dúvida enquanto o chamado espera dono. Não abre chamado nem inicia qualificação."""
    if re.search(r'\b(alguem|ninguem|atendente|humano|pessoa)\b', t):  # "alguém aí?" → já avisei
        return None
    if base.pergunta_horario(t):
        return base.resposta_horario(c, t, casar_faq(c, t))
    faq = casar_faq(c, t)
    if faq:
        return faq
    info = base.resposta_info(c, t)
    if info and _numero(t) is None:
        return info
    prod = casar_produto(c, t)
    if prod and base.preco_vigente(c, prod):
        return f"{prod['nome']}: {base.preco_vigente(c, prod)}. Alguém da equipe já vai falar com você sobre isso."
    if len(t.split()) >= 3:  # "ok", "obrigado", "alguém aí?" não vão para a IA
        return cerebro.responder_duvida(c, texto, lid)
    return None

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


# Primeira palavra que mostra que a frase não é um nome ("não sei", "quero ver", "tenho dúvida", "oi"...).
NAO_E_NOME = set('''nao sim quero tenho oi ola bom boa ok okay obrigado obrigada valeu tudo talvez depois agora
ainda so preciso gostaria queria quer pode posso vou vai estou to tava sei acho qual quanto quando como onde
porque por que pra para eu voce me meu minha tem ter e eh ai opa oie oii hey hello alo bem nada nenhum
nenhuma isso esse essa aqui la sou chamo'''.split())
_PALAVRA_NOME = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def parece_nome(nome):
    """1 a 4 palavras, só letras/espaço/apóstrofo/hífen, 2–40 caracteres, sem dígitos, e a primeira palavra
    não é negação, verbo ou saudação comum."""
    if not isinstance(nome, str):
        return False
    nome = ' '.join(nome.split())
    palavras = nome.split()
    if not 2 <= len(nome) <= 40 or not 1 <= len(palavras) <= 4:
        return False
    if not all(_PALAVRA_NOME.fullmatch(p) for p in palavras):
        return False
    return normalizar(palavras[0]) not in NAO_E_NOME


# ---------- entrada ----------
def receber(c, telefone, texto, canal='web', nome=None, push_name=None, sessao=None, internacional=False):
    if canal not in ('web', 'whatsapp'):
        canal = 'web'
    if canal == 'web' and sessao:
        lead = lead_sessao(c, sessao)
        if not isinstance(texto, str) or not texto.strip():
            raise Erro(422, 'Texto obrigatório')
    else:
        tel = normalizar_telefone(telefone, internacional=internacional and canal == 'whatsapp')
        if not isinstance(texto, str) or not texto.strip():
            raise Erro(422, 'Texto obrigatório')
        lead = obter_lead(c, tel)[0] if canal == 'whatsapp' else novo_lead_web(c, tel)
    agora = iso(c.agora())
    c.db.execute('UPDATE leads SET ultimo_contato=?, canal=? WHERE id=?', (agora, canal, lead['id']))
    if isinstance(push_name, str) and push_name.strip():
        c.db.execute('UPDATE leads SET push_name=? WHERE id=?', (push_name.strip()[:60], lead['id']))
    # Nome do formulário (chat web/simulação) passa pela mesma validação da qualificação; inválido é ignorado
    # e o agente pergunta depois.
    if isinstance(nome, str) and parece_nome(nome) and not lead['nome']:
        c.db.execute('UPDATE leads SET nome=? WHERE id=?', (' '.join(nome.split())[:80], lead['id']))
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
        sugestao.criar(c, aberto, lead, texto)  # sugestão de resposta ao dono (seção 7a), gerada fora do lock
        from . import atender
        if atender.cobre_dono(c, aberto):  # 1.9.8: "robô responde por mim" — o dono continua vendo tudo
            return atender.resposta_robo(c, t, texto, lid, aberto,
                                         f"Anotei! {primeiro_nome(c.nome_colab(aberto['dono']))} já vai te responder.")
        return []
    # 4. chamado aguardando: enquanto ninguém assume, o agente continua tirando dúvidas
    #    (horário, FAQ, informações, preço cadastrado, IA). Sem resposta → lembra que a equipe já foi avisada.
    #    Chamado silencioso (1.10.8, chance de venda): o cliente não sabe — a conversa segue as regras normais;
    #    se ele pedir uma pessoa ("tem alguém aí?"), aí sim o robô conta que chamou.
    if aberto and aberto['silencioso']:
        horario = base.pergunta_horario(t) and re.search(r'\b(que horas?|horario|quando|abre|fecha)\b', t)
        if not horario and (PEDE_ALGUEM.search(t) or (tem(t, HUMANO) and not base.pergunta_horario(t))):
            return [chamados.tirar_silencio(c, aberto, 'pediu_humano')]
    elif aberto:
        r = _duvida_em_espera(c, t, texto, lid)
        if r:
            return [r]
        if aberto['robo_assumiu']:  # 1.9.8: o robô já avisou que segue com o lead
            return ['Sigo por aqui com você. Assim que alguém da equipe ficar livre, assume a conversa.']
        return ['Eu já avisei a equipe; logo alguém fala com você por aqui.']
    e = estado(lead)
    # 4a. pergunta de horário/disponibilidade (antes de 5–7: "que hora tem atendimento humano?" não é pedido)
    if base.pergunta_horario(t):
        _zerar_falhas(c, lid)
        return [base.resposta_horario(c, t, casar_faq(c, t))]
    # 5–7. pedidos que abrem chamado
    if tem(t, HUMANO):
        return _abrir(c, lid, 'pediu_humano')
    if tem(t, VENDA):
        c.db.execute("UPDATE leads SET nota='quente' WHERE id=?", (lid,))
        prod = casar_produto(c, t)
        prefixo = ''
        if prod:
            c.db.execute('UPDATE leads SET interesse=? WHERE id=?', (prod['id'], lid))
            if base.preco_vigente(c, prod):
                prefixo = f"{prod['nome']}: {base.preco_vigente(c, prod)}. "
        elif re.search(r'\b(quanto custa|valor|valores|preco|precos|orcamento)\b', t):
            prefixo = _tabela_precos(c)  # 1.10.8: pergunta de preço sem produto → mostra os preços cadastrados
        if base.PAGAMENTO.search(t):
            prefixo += base.prefixo_pagamento(c)
        if not prefixo and len(t.split()) >= 3 and c.lead(lid)['nome'] and c.lead(lid)['urgencia']:
            prefixo = ((cerebro.responder_duvida(c, texto, lid) or '') + ' ').lstrip()
        return _abrir(c, lid, 'venda', prefixo)
    if tem_palavra(t, PRECISA):
        return _abrir(c, lid, 'precisa')
    # 7a. informações do negócio (só campo preenchido; nunca inventa)
    info = base.resposta_info(c, t)
    if info and _numero(t) is None:
        _zerar_falhas(c, lid)
        return [info]
    # 8. qualificação em andamento
    etapa = e.get('etapa')
    if etapa:
        r = qualificar(c, c.lead(lid), e, texto, t)
        if r is not None:
            return r
        e = estado(c.lead(lid))
    # 8a. agradecimento / confirmação (1.10.8): resposta curta, sem contar falha nem chamar ninguém
    if not primeiro and (t in AGRADECE or t in CONFIRMA):
        _zerar_falhas(c, lid)
        if t in AGRADECE or 'obrigad' in t:
            return ['Por nada! Se precisar de mais alguma coisa, é só mandar mensagem.']
        return ['Combinado! Qualquer dúvida, é só mandar mensagem por aqui.']
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
        preco = f" ({base.preco_vigente(c, prod)})" if base.preco_vigente(c, prod) else ''
        if lead['urgencia']:  # já disse para quando: é chance de venda (abre calado)
            return _abrir(c, lid, 'venda', f"Temos o {prod['nome']}{preco}. ")
        gravar_estado(c, lid, {'etapa': 'quando', 'falhas': 0})
        return [f"Temos o {prod['nome']}{preco}. Para quando você precisa?\n{URG_OPCOES}"]
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
    duvida = cerebro.responder_duvida(c, texto, lid)
    if duvida:
        _zerar_falhas(c, lid)
        return [duvida]
    falhas = int(e.get('falhas', 0)) + 1
    if falhas >= 2:
        gravar_estado(c, lid, {})
        return _abrir(c, lid, 'precisa', NAO_SEI + ' ')
    # 1.10.8: não oferece chamar ninguém (só quem pede ouve isso); a segunda seguida sem resposta avisa a equipe.
    gravar_estado(c, lid, {'etapa': 'nao_sei2', 'falhas': falhas})  # nao_sei = conversa de antes da 1.10.8
    return [NAO_SEI + ' Pode me contar de outro jeito o que você precisa?']


def _zerar_falhas(c, lid):
    e = estado(c.lead(lid))
    if e.get('falhas'):
        e['falhas'] = 0
        gravar_estado(c, lid, e)


def _abrir(c, lid, motivo, prefixo='', silencioso=None):
    gravar_estado(c, lid, {})
    aberto = chamados.aberto_do_lead(c, lid)
    if aberto:  # 1.10.8: já há chamado (silencioso): nunca abre outro
        if motivo == 'venda' and silencioso is not False:
            c.db.execute('UPDATE chamados SET prioridade=? WHERE id=?', (chamados.prioridade(motivo, c.lead(lid)), aberto['id']))
            return _seguir_venda(c, lid, prefixo)
        if aberto['silencioso']:
            return [prefixo + chamados.tirar_silencio(c, aberto, motivo)]
        c.db.execute('UPDATE chamados SET prioridade=? WHERE id=?', (chamados.prioridade(motivo, c.lead(lid)), aberto['id']))
        return [prefixo + chamados.texto_chamei(c, motivo)]
    _ident, respostas = chamados.abrir(c, lid, motivo, silencioso=silencioso)
    if not respostas:  # chance de venda: a equipe foi chamada sem o cliente saber
        return _seguir_venda(c, lid, prefixo)
    respostas[0] = prefixo + respostas[0]
    return respostas


def _tabela_precos(c):
    itens = [f"{p['nome']}: {base.preco_vigente(c, p)}" for p in c.cfg.get('produtos', []) if base.preco_vigente(c, p)]
    return ('Nossos valores: ' + '; '.join(itens) + '. ') if itens else ''


def _seguir_venda(c, lid, prefixo=''):
    """Depois de chamar a equipe em silêncio, o robô segue a conversa como se nada fosse."""
    lead = c.lead(lid)
    if not lead['nome']:
        return [(prefixo or 'Ótimo! ') + _pergunta_nome(c, lead, {'falhas': 0})]
    if not lead['urgencia']:
        gravar_estado(c, lid, {'etapa': 'quando', 'falhas': 0})
        return [prefixo + f'Para quando você precisa?\n{URG_OPCOES}']
    return [prefixo + 'Anotado! Se tiver qualquer dúvida, pode perguntar por aqui.']


def _pergunta_nome(c, lead, e):
    if lead['push_name'] and parece_nome(lead['push_name']):
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
        if not nome or t in SAUDACOES or not parece_nome(nome):
            gravar_estado(c, lid, {**e, 'etapa': 'nome'})
            return ['Pode me dizer só o seu nome?']
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
        if n == 2:  # 1.10.8: este mês também é chance de venda — chama a equipe sem dizer
            c.db.execute("UPDATE leads SET urgencia=2, nota='morno' WHERE id=?", (lid,))
            return _abrir(c, lid, 'venda')
        if n == 3:
            c.db.execute("UPDATE leads SET urgencia=3, nota='frio' WHERE id=?", (lid,))
            ab = chamados.aberto_do_lead(c, lid)
            if ab and ab['silencioso'] and ab['status'] in ('aguardando', 'alerta'):
                chamados.desistir_calado(c, ab)
            gravar_estado(c, lid, {'falhas': 0})
            return ['Sem problema. Se tiver qualquer dúvida, é só mandar mensagem por aqui.']
        return [f'Responda com o número:\n{URG_OPCOES}']
    if etapa in ('nao_sei', 'nao_sei2'):
        # Depois do "Essa eu não sei responder...": não → encerra; outra coisa segue as regras (mantém as falhas:
        # a segunda seguida sem resposta avisa a equipe sozinha). 1.10.8: o robô não oferece mais chamar alguém.
        if 'nao' in palavras or t in NAO:
            gravar_estado(c, lid, {'falhas': 0})
            return ['Tudo bem! Se tiver qualquer dúvida, é só mandar mensagem por aqui.']
        if etapa == 'nao_sei' and palavras & SIM and len(palavras) <= 3:  # "sim" a "Quer que eu chame alguém?" (conversa de antes da 1.10.8)
            return _abrir(c, lid, 'precisa')
        gravar_estado(c, lid, {'falhas': e.get('falhas', 0)})
        return None
    if etapa == 'quer_falar':  # só existe em conversa de antes da 1.10.8 ("Quer que eu chame alguém?")
        if 'nao' in palavras or t in NAO:
            gravar_estado(c, lid, {'falhas': 0})
            return ['Tudo bem! Se tiver qualquer dúvida, é só mandar mensagem por aqui.']
        if palavras & SIM:  # ele aceitou que chamássemos alguém: avisa (não é chamado calado)
            return _abrir(c, lid, 'venda', silencioso=False)
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
    elif aberto and not aberto['silencioso']:
        respostas = ['Eu já avisei a equipe; logo alguém fala com você por aqui.']
    else:  # sem chamado, ou chamado silencioso (agora o cliente pediu: conta que chamou)
        respostas = _abrir(c, lead['id'], 'pediu_humano')
    aberto = chamados.aberto_do_lead(c, lead['id'])
    for r in respostas:
        registrar(c, lead['id'], 'agente', r, aberto['id'] if aberto else None)
    return {'ok': True, 'respostas': respostas, 'chamado': aberto['id'] if aberto else None,
            'lead': lead_resumo(c.lead(lead['id']))}


def apagar(c, token, b=None):
    lead = c.lead_token(token)
    if not isinstance(b, dict) or b.get('confirmar') is not True:
        raise Erro(422, 'Confirme com {"confirmar": true}')
    anonimizar(c, lead['id'])
    return {'ok': True, 'mensagem': 'Seus dados foram apagados.'}
