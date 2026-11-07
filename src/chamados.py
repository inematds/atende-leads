"""Chamados: abrir, rotear (oferta/alerta), assumir, passar, fechar, devolver (seções 7 e 9)."""
import json
from datetime import datetime, timedelta

from .core import Erro, ddmm_hhmm, formatar_telefone, iso, minutos, novo_token, parse, primeiro_nome
from . import equipe, evolution, horario
from . import telegram as tg

MOTIVO_LEG = {'pediu_humano': 'pediu humano', 'venda': 'chance de venda', 'precisa': 'precisa de atenção',
             'retomada': 'retomada pelo atendente', 'gestor': 'passado pelo gestor'}
RESULTADOS = ('vendeu', 'retornar', 'negociando', 'sem_interesse', 'invalido')
MOTIVOS_SEM = ('preco', 'ja_comprou', 'curioso', 'nao_quer_contato', 'outro')
MOTIVOS_INV = ('numero_errado', 'spam', 'nao_e_lead')
STATUS_LEAD = {'vendeu': 'ganho', 'retornar': 'retornar', 'negociando': 'negociando',
               'sem_interesse': 'perdido', 'invalido': 'invalido'}
ABERTOS = ('aguardando', 'alerta', 'atendendo')


# ---------- leitura ----------
def aberto_do_lead(c, lead_id):
    return c.db.execute("SELECT * FROM chamados WHERE lead_id=? AND status IN ('aguardando','alerta','atendendo') "
                        'ORDER BY id DESC LIMIT 1', (lead_id,)).fetchone()


def recusaram(ch):
    try:
        return list(json.loads(ch['recusaram'] or '[]'))
    except ValueError:
        return []


def link_ligar(c, ch):
    return f"{c.url_publica()}/ligar/{ch['token']}"


def json_chamado(c, ch):
    lead = c.lead(ch['lead_id'])
    prod = c.produto(lead['interesse']) if lead['interesse'] else None
    return {
        'id': ch['id'], 'lead_id': ch['lead_id'], 'motivo': ch['motivo'], 'prioridade': ch['prioridade'],
        'status': ch['status'], 'ofertado_a': ch['ofertado_a'], 'ofertado_em': ch['ofertado_em'],
        'recusaram': recusaram(ch), 'dono': ch['dono'], 'aberto_em': ch['aberto_em'],
        'assumido_em': ch['assumido_em'], 'fechado_em': ch['fechado_em'], 'resultado': ch['resultado'],
        'valor': ch['valor'], 'produto': ch['produto'], 'motivo_fechamento': ch['motivo_fechamento'],
        'nota_fechamento': ch['nota_fechamento'], 'retornar_em': ch['retornar_em'], 'resumo': ch['resumo'],
        'token_chamado': ch['token'], 'link_ligar': link_ligar(c, ch),
        'minutos': minutos(ch['conta_desde'] or ch['aberto_em'], c.agora()),
        'lead_nome': lead['nome'], 'telefone': lead['telefone'], 'nota': lead['nota'],
        'interesse': lead['interesse'], 'interesse_nome': prod['nome'] if prod else None,
        'nao_contatar': bool(lead['nao_contatar']), 'tempos': tempos(c, ch),
        'silencioso': bool(ch['silencioso']),
    }


# Frases prontas do robô na espera não contam como conversa (só avisam que a equipe foi chamada).
PRONTAS = ('Eu já avisei a equipe', 'Essa eu não sei responder com certeza. Agora', 'Por nada!', 'Combinado!', 'Sigo por aqui com você', 'Nossa equipe está ocupada', 'Certo, vou chamar alguém',
           'Agora estamos fora do horário', 'Anotei!', 'Combinado! Vamos te procurar',
           'Certo, já chamei alguém', 'Já avisei a equipe', 'Essa eu não sei responder com certeza. Já avisei')


def pronta(texto):
    t = str(texto or '')
    return t.startswith(PRONTAS) or t.endswith('vai te atender agora.')


def tempos(c, ch):
    """1.9.8 — tempos classificados do chamado (minutos):
    espera_min = do início do prazo (conta_desde/aberto_em) até assumir (ou até agora/fechar, se ninguém assumiu);
    espera_sem_resposta_min = parte da espera com mensagem do lead sem resposta de verdade (frase pronta não conta);
    espera_robo_min = da 1ª à última resposta de verdade do robô na espera (o robô conversando);
    espera_silencio_min = o resto (ninguém escrevendo);
    robo_msgs = respostas de verdade do robô na espera;
    primeira_resposta_min = do assumir até a 1ª mensagem da equipe (None = ninguém respondeu ainda).
    Chamado aberto já assumido (retomada, passado pelo gestor) tem espera 0."""
    inicio = ch['conta_desde'] or ch['aberto_em']
    if not inicio:
        return None
    fim = parse(ch['assumido_em']) or parse(ch['fechado_em']) or c.agora()
    total = minutos(inicio, fim)
    pend, sem, robo, prim_r, ult_r = None, 0, 0, None, None
    for m in c.db.execute("SELECT de, em, texto FROM mensagens WHERE lead_id=? AND em>=? AND em<=? AND de IN ('lead','agente') "
                          'ORDER BY id', (ch['lead_id'], inicio, iso(fim))):
        if m['de'] == 'lead':
            if m['em'] == inicio:  # o próprio pedido que abriu o chamado
                continue
            pend = pend or m['em']
        elif not pronta(m['texto']):
            robo += 1
            prim_r = prim_r or m['em']
            ult_r = m['em']
            if pend:
                sem += minutos(pend, parse(m['em']))
                pend = None
    if pend:
        sem += minutos(pend, fim)
    sem = min(sem, total)
    conv = min(minutos(prim_r, parse(ult_r)), total - sem) if prim_r else 0
    prim = None
    if ch['assumido_em']:
        r = c.db.execute("SELECT MIN(em) FROM mensagens WHERE chamado_id=? AND de='humano'", (ch['id'],)).fetchone()[0]
        prim = minutos(ch['assumido_em'], parse(r)) if r else None
    return {'espera_min': total, 'espera_sem_resposta_min': sem, 'espera_robo_min': conv,
            'espera_silencio_min': total - sem - conv, 'robo_msgs': robo, 'primeira_resposta_min': prim}


def ultimas_mensagens(c, lead_id, n=5):
    rows = c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' ORDER BY id DESC LIMIT ?",
                        (lead_id, n)).fetchall()
    return [r['texto'] for r in reversed(rows)]


def _interesse_nome(c, lead):
    p = c.produto(lead['interesse']) if lead['interesse'] else None
    return p['nome'] if p else '—'


def _icone(ch):
    return '🔥' if ch['prioridade'] == 'quente' else '🙋'


# ---------- textos ----------
def texto_linha(c, ch, ofertado=None):
    lead = c.lead(ch['lead_id'])
    t = f"{_icone(ch)} #{ch['id']} {primeiro_nome(lead['nome'])} · {MOTIVO_LEG[ch['motivo']]}"
    if ofertado:
        t += f' → {c.nome_colab(ofertado)}'
    return t


def texto_ficha(c, ch, titulo):
    lead = c.lead(ch['lead_id'])
    linhas = [titulo,
              f"Nome: {lead['nome'] or 'não informado'}",
              f"Telefone: {formatar_telefone(lead['telefone'])}",
              f"Nota: {lead['nota']}",
              f"Motivo: {MOTIVO_LEG[ch['motivo']]}",
              f"Interesse: {_interesse_nome(c, lead)}"]
    if ch['silencioso']:
        linhas.append('🤫 Chance de venda percebida pelo robô: o cliente não pediu contato. Apresente-se com calma.')
    if ch['resumo']:
        linhas += ['', ch['resumo']]
    ult = ultimas_mensagens(c, lead['id'])
    if ult:
        linhas += ['', 'Últimas mensagens:'] + [f'• {m}' for m in ult]
    linhas += ['', '📞 Ligar = ligação comum pelo telefone.',
               '💬 WhatsApp = abre a conversa; para ligar, toque no ícone de chamada dentro do WhatsApp.']
    return '\n'.join(linhas)


def botoes_contato(c, ch):
    lead = c.lead(ch['lead_id'])
    return [tg.bt_url('📞 Ligar (telefone)', link_ligar(c, ch)), tg.bt_url('💬 WhatsApp (conversa ou chamada)', f"https://wa.me/{lead['telefone']}")]


def botoes_fechamento(c, ch):
    i = ch['id']
    return [[tg.bt('✅ Vendeu', f'fe:{i}:vendeu'), tg.bt('📅 Retornar', f'fe:{i}:retornar')],
            [tg.bt('🤔 Negociando', f'fe:{i}:negociando'), tg.bt('❌ Sem interesse', f'fe:{i}:sem_interesse')],
            [tg.bt('🚫 Inválido', f'fe:{i}:invalido'), tg.bt('↩️ Devolver ao bot', f'dv:{i}')],
            botoes_contato(c, ch)]


def enviar_cartao(c, ch):
    texto = texto_ficha(c, ch, f"✅ Você está atendendo #{ch['id']} · {MOTIVO_LEG[ch['motivo']]}") + \
        '\n\nResponda (reply) a esta mensagem para falar com o lead. Ao terminar, escolha o resultado:'
    ref = equipe.privado(c, ch['dono'], texto, botoes_fechamento(c, ch))
    if ref:
        c.db.execute('UPDATE chamados SET tg_cartao=? WHERE id=?', (ref, ch['id']))
        guardar_msg(c, ref, ch['id'], 'cartao')
    return ref


def guardar_msg(c, ref, chamado_id, tipo):
    """Liga a mensagem do Telegram ao chamado (para o reply). Ref provisória: o despachante grava ao enviar."""
    if ref and ref.startswith('q:'):
        c.db.execute('UPDATE tg_saida SET chamado_id=?, tipo=? WHERE id=?', (chamado_id, tipo, ref[2:]))
    elif ref:
        chat, mid = ref.rsplit(':', 1)
        c.db.execute('INSERT OR REPLACE INTO tg_msgs VALUES (?,?,?,?)', (chat, mid, chamado_id, tipo))


# ---------- abrir / rotear ----------
def prioridade(motivo, lead):
    # 1.10.8: a prioridade segue a nota do lead (venda de lead morno não ganha o prazo nem o 🔥 de quente)
    return 'quente' if lead['nota'] == 'quente' else 'normal'


# 1.10.8 — o que o robô diz ao abrir o chamado. Só fala em chamar alguém quando o cliente pediu; percebeu
# necessidade (reclamação, dúvida sem resposta) → avisa que notificou e segue; chance de venda → não diz nada.
TXT_PEDIU = 'Certo, já chamei alguém da equipe. Enquanto isso, sigo com você por aqui: pode perguntar.'
TXT_PRECISA = 'Já avisei a equipe sobre isso, e alguém vai falar com você por aqui. Enquanto isso, sigo com você.'


def silencioso_por_padrao(motivo):
    return motivo == 'venda'


def texto_chamei(c, motivo):
    """O que o lead ouve quando sabe que a equipe foi chamada (fora do horário diz quando abre)."""
    agora = c.agora()
    if horario.no_horario(c, agora):
        return TXT_PRECISA if motivo == 'precisa' else TXT_PEDIU
    prox = horario.proximo_inicio(c, agora)
    quando = ddmm_hhmm(prox) if prox else 'no próximo expediente'
    return (f'Agora estamos fora do horário de atendimento; já deixei avisado, e alguém da equipe fala com '
            f'você assim que abrirmos: {quando}. Enquanto isso, sigo com você por aqui.')


def tirar_silencio(c, ch, motivo):
    """O cliente do chamado calado pediu uma pessoa ou reclamou: agora ele sabe. Atualiza motivo/prioridade,
    não repete o aviso "equipe ocupada" (o texto já diz "sigo com você") e avisa quem tem o chamado."""
    lead = c.lead(ch['lead_id'])
    c.db.execute('UPDATE chamados SET silencioso=0, motivo=?, prioridade=?, robo_assumiu=COALESCE(robo_assumiu, ?) '
                 'WHERE id=?', (motivo, prioridade('venda', lead) if ch['motivo'] == 'venda' else prioridade(motivo, lead),
                                iso(c.agora()), ch['id']))
    c.sujo = True
    quem = ch['dono'] or ch['ofertado_a']
    if quem:
        o_que = 'pediu para falar com alguém' if motivo == 'pediu_humano' else 'está com um problema'
        equipe.privado(c, quem, f"⚠️ #{ch['id']} {primeiro_nome(lead['nome']) or 'O cliente'} {o_que} e agora sabe "
                                f"que a equipe vem. Não é mais só chance de venda: atenda logo.")
    return texto_chamei(c, motivo)


def abrir(c, lead_id, motivo, resumo=None, silencioso=None):
    """Abre chamado e devolve (id, respostas ao lead). Chance de venda abre calado: respostas = []."""
    from . import cerebro, limite
    ip = getattr(c._local, 'ip_publico', None)  # pedido veio do chat web ou da página do lead
    if ip is not None:
        if not limite.chamado_web_permitido(ip):
            raise Erro(429, limite.MSG_CHAMADO_WEB)
        c._local.abriu_publico = True  # contado depois que a requisição termina (a transação pode repetir)
    lead = c.lead(lead_id)
    agora = c.agora()
    no_horario = horario.no_horario(c, agora)
    if resumo is None:
        resumo = cerebro.resumo(c, lead, motivo)
    calado = silencioso_por_padrao(motivo) if silencioso is None else bool(silencioso)
    ident = c.db.execute(
        'INSERT INTO chamados(lead_id,motivo,prioridade,status,aberto_em,conta_desde,token,resumo,silencioso) '
        'VALUES (?,?,?,?,?,?,?,?,?)',
        (lead_id, motivo, prioridade(motivo, lead), 'aguardando', iso(agora),
         iso(agora) if no_horario else None, novo_token(), resumo, 1 if calado else 0)).lastrowid
    c.sujo = True
    if calado:
        if no_horario:
            ativar(c, ident)
        return ident, []
    # Link "meu atendimento": desligado por padrão; ligado (link_acompanhamento) só vai no WhatsApp,
    # nunca no chat do site (o lead já está na conversa).
    extra = []
    if c.cfg.get('link_acompanhamento') and not lead['sessao']:
        extra = [f"Acompanhe aqui: {c.url_publica()}/meu/{lead['token']}"]
    if no_horario:
        ativar(c, ident)
    return ident, [texto_chamei(c, motivo)] + extra


def ativar(c, ident):
    """Manda a linha ao grupo e roteia (abertura no horário ou na abertura do expediente)."""
    ch = c.chamado(ident)
    alvo = proximo_alvo(c, ch)
    gid = tg.grupo()
    if gid:
        ref = tg.enviar(c, gid, texto_linha(c, ch, alvo))
        if ref:
            c.db.execute('UPDATE chamados SET tg_linha=? WHERE id=?', (ref, ident))
    if alvo:
        oferecer(c, c.chamado(ident), alvo)
    else:
        alertar(c, c.chamado(ident))


def elegiveis(c, ch):
    recus = set(recusaram(ch))
    exige_vinculo = tg.configurado()
    out = []
    for colab in equipe.ordem_de_vez(c):
        if colab in recus:
            continue
        if exige_vinculo and not equipe.vinculado(c, colab):
            continue
        out.append(colab)
    return out


def proximo_alvo(c, ch):
    cands = elegiveis(c, ch)
    if not cands:
        return None
    limite = iso(c.agora() - timedelta(days=30))
    ant = c.db.execute("SELECT dono FROM chamados WHERE lead_id=? AND status='fechado' AND dono IS NOT NULL "
                       "AND fechado_em>=? AND id<>? ORDER BY fechado_em DESC, id DESC LIMIT 1",
                       (ch['lead_id'], limite, ch['id'])).fetchone()
    if ant and ant['dono'] in cands:
        return ant['dono']
    return cands[0]


def oferecer(c, ch, colab):
    agora = iso(c.agora())
    c.db.execute('UPDATE chamados SET ofertado_a=?, ofertado_em=? WHERE id=?', (colab, agora, ch['id']))
    c.sujo = True
    ch = c.chamado(ch['id'])
    texto = texto_ficha(c, ch, f"{_icone(ch)} Chamado #{ch['id']} · {MOTIVO_LEG[ch['motivo']]}")
    botoes = [[tg.bt('✅ Assumir', f"as:{ch['id']}"), tg.bt('↪️ Passar', f"pa:{ch['id']}")], botoes_contato(c, ch)]
    ref = equipe.privado(c, colab, texto, botoes)
    c.db.execute('UPDATE chamados SET tg_oferta=? WHERE id=?', (ref, ch['id']))
    guardar_msg(c, ref, ch['id'], 'oferta')


def rotear(c, ident, alertar_se_vazio=True):
    ch = c.chamado(ident)
    if ch['status'] not in ('aguardando', 'alerta'):
        return False
    alvo = proximo_alvo(c, ch)
    if alvo:
        oferecer(c, ch, alvo)
        if ch['tg_linha'] and ch['status'] == 'aguardando':
            tg.editar(c, ch['tg_linha'], texto_linha(c, ch, alvo))
        return True
    c.db.execute('UPDATE chamados SET ofertado_a=NULL, ofertado_em=NULL WHERE id=?', (ident,))
    if alertar_se_vazio:
        alertar(c, c.chamado(ident))
    return False


def recusar(c, ch, texto_antigo):
    """Oferta recusada (vencida ou passada): edita o aviso antigo e oferece ao próximo."""
    rec = recusaram(ch)
    if ch['ofertado_a'] and ch['ofertado_a'] not in rec:
        rec.append(ch['ofertado_a'])
    c.db.execute('UPDATE chamados SET recusaram=?, ofertado_a=NULL, ofertado_em=NULL WHERE id=?',
                 (json.dumps(rec), ch['id']))
    if ch['tg_oferta']:
        tg.editar(c, ch['tg_oferta'], texto_antigo)
        c.db.execute('UPDATE chamados SET tg_oferta=NULL WHERE id=?', (ch['id'],))
    c.sujo = True
    rotear(c, ch['id'])


def vencer_oferta(c, ch):
    recusar(c, ch, f"⌛ #{ch['id']} passou para o próximo")


def passar(c, ident, colab):
    ch = c.chamado(ident)
    if ch['status'] not in ('aguardando', 'alerta'):
        raise Erro(409, 'Chamado não está aguardando')
    if ch['ofertado_a'] != colab:
        raise Erro(409, 'Esta oferta não é sua')
    recusar(c, ch, f"↪️ #{ident} passou para o próximo")
    return json_chamado(c, c.chamado(ident))


def alertar(c, ch):
    if ch['status'] not in ('aguardando', 'alerta'):
        return False
    if ch['alertado']:
        if ch['status'] != 'alerta':
            c.db.execute("UPDATE chamados SET status='alerta' WHERE id=?", (ch['id'],))
        return False
    c.db.execute("UPDATE chamados SET status='alerta', alertado=1 WHERE id=?", (ch['id'],))
    c.sujo = True
    lead = c.lead(ch['lead_id'])
    espera = minutos(ch['conta_desde'] or ch['aberto_em'], c.agora())
    texto = (f"🚨 #{ch['id']} {primeiro_nome(lead['nome'])} · {MOTIVO_LEG[ch['motivo']]} · nota {lead['nota']} · "
             f"interesse {_interesse_nome(c, lead)} · esperando há {espera} min")
    gid = tg.grupo()
    if gid:
        ref = tg.enviar(c, gid, texto, [[tg.bt('✅ Assumir', f"as:{ch['id']}")]])
        if ref:
            c.db.execute('UPDATE chamados SET tg_alerta=? WHERE id=?', (ref, ch['id']))
            guardar_msg(c, ref, ch['id'], 'alerta')
    return True


def distribuir(c):
    """Alguém ficou livre: oferece os chamados ativos sem oferta, na ordem de abertura."""
    for ch in c.db.execute("SELECT id FROM chamados WHERE status IN ('aguardando','alerta') AND conta_desde IS NOT NULL "
                           'AND ofertado_a IS NULL ORDER BY aberto_em, id').fetchall():
        rotear(c, ch['id'], alertar_se_vazio=False)


# ---------- assumir ----------
def assumir(c, ident, colab, restrito=False):
    """restrito=True (colaborador pela API ou pelo Telegram): só quem recebeu a oferta, ou qualquer um com o
    chamado em alerta. O gestor usa transferir."""
    ch = c.chamado(ident)
    r = c.colab(colab)
    if ch['status'] in ('atendendo', 'fechado') and ch['dono']:
        raise Erro(409, f"já foi assumido por {c.nome_colab(ch['dono'])}")
    if restrito and ch['status'] == 'aguardando' and ch['ofertado_a'] != colab:
        raise Erro(403, 'Este chamado não foi oferecido a você')
    if r['status'] == 'fora':
        raise Erro(409, 'Quem está fora não pode assumir')
    agora = iso(c.agora())
    cur = c.db.execute("UPDATE chamados SET status='atendendo', dono=?, assumido_em=?, ultimo_mov=?, lembrado=0, "
                       "ofertado_a=NULL WHERE id=? AND status IN ('aguardando','alerta')", (colab, agora, agora, ident))
    if cur.rowcount != 1:
        atual = c.chamado(ident)
        raise Erro(409, f"já foi assumido por {c.nome_colab(atual['dono'])}" if atual['dono'] else
                   'Chamado não está aberto')
    _pos_assumir(c, ch, colab)
    return json_chamado(c, c.chamado(ident))


def _pos_assumir(c, ch_antes, colab, avisar_lead=True):
    ident = ch_antes['id']
    nome = c.nome_colab(colab)
    lead = c.lead(ch_antes['lead_id'])
    if lead['status'] != 'em_atendimento':
        c.db.execute("UPDATE leads SET status_antes=status, status='em_atendimento' WHERE id=?", (lead['id'],))
    equipe.ficou_atendendo(c, colab)
    feito = f'✅ {nome} assumiu #{ident}'
    for campo in ('tg_linha', 'tg_alerta', 'tg_oferta'):
        if ch_antes[campo]:
            tg.editar(c, ch_antes[campo], feito)
    c.db.execute('UPDATE chamados SET tg_oferta=NULL WHERE id=?', (ident,))
    enviar_cartao(c, c.chamado(ident))
    if avisar_lead:
        texto = f'{nome} vai te atender agora.'
        lead = c.lead(lead['id'])
        _registrar(c, lead['id'], ident, 'agente', texto)
        evolution.enviar_lead(c, lead, texto, 'aviso', automatica=True)
        c.db.execute('UPDATE chamados SET silencioso=0 WHERE id=?', (ident,))  # agora o cliente sabe
    c.sujo = True


def _registrar(c, lead_id, chamado_id, de, texto, autor=None):
    c.db.execute('INSERT INTO mensagens(lead_id,chamado_id,de,autor,texto,em) VALUES (?,?,?,?,?,?)',
                 (lead_id, chamado_id, de, autor, texto, iso(c.agora())))


def transferir(c, ident, colab):
    ch = c.chamado(ident)
    r = c.colab(colab)
    if ch['status'] == 'fechado':
        raise Erro(409, 'Chamado fechado')
    if r['status'] == 'fora':
        raise Erro(409, 'Quem está fora não pode assumir')
    if ch['status'] in ('aguardando', 'alerta'):
        return assumir(c, ident, colab)
    antigo = ch['dono']
    if antigo == colab:
        return json_chamado(c, ch)
    agora = iso(c.agora())
    c.db.execute('UPDATE chamados SET dono=?, ultimo_mov=?, lembrado=0 WHERE id=?', (colab, agora, ident))
    if ch['tg_cartao']:
        tg.editar(c, ch['tg_cartao'], f'↪️ #{ident} transferido para {c.nome_colab(colab)}')
    nome = c.nome_colab(colab)
    equipe.ficou_atendendo(c, colab)
    enviar_cartao(c, c.chamado(ident))
    lead = c.lead(ch['lead_id'])
    texto = f'{nome} vai te atender agora.'
    _registrar(c, lead['id'], ident, 'agente', texto)
    evolution.enviar_lead(c, lead, texto, 'aviso', automatica=True)
    c.db.execute('UPDATE chamados SET silencioso=0 WHERE id=?', (ident,))
    c.sujo = True
    equipe.liberar_se_vazio(c, antigo)
    return json_chamado(c, c.chamado(ident))


# ---------- conversa dono → lead ----------
def responder(c, ident, colab, texto, sugestao_id=None):
    from . import sugestao
    ch = c.chamado(ident)
    if not isinstance(texto, str) or not texto.strip():
        raise Erro(422, 'Texto obrigatório')
    if colab is not None and ch['dono'] != colab:
        raise Erro(403, 'Só o dono do atendimento responde')
    if ch['status'] != 'atendendo':
        raise Erro(409, 'Chamado não está em atendimento')
    lead = c.lead(ch['lead_id'])
    sugestao.registrar_resposta(c, ch, colab, texto.strip(), sugestao_id)  # aprendizado (seção 7a)
    _registrar(c, lead['id'], ident, 'humano', texto.strip(), ch['dono'])
    c.db.execute('UPDATE chamados SET ultimo_mov=?, lembrado=0 WHERE id=?', (iso(c.agora()), ident))
    status = evolution.enviar_lead(c, lead, texto.strip(), 'humano')
    return {'ok': True, 'status': status}


# ---------- fechamento ----------
def validar_fechamento(c, b):
    if not isinstance(b, dict):
        raise Erro(422, 'Corpo inválido')
    res = b.get('resultado')
    if res not in RESULTADOS:
        raise Erro(422, 'Resultado inválido')
    out = {'resultado': res, 'valor': None, 'produto': None, 'retornar_em': None, 'motivo': None, 'nota': None}
    valor = b.get('valor')
    if valor is not None:
        if isinstance(valor, bool) or not isinstance(valor, (int, float)) or valor < 0:
            raise Erro(422, 'Valor inválido')
        out['valor'] = float(valor)
    if res == 'vendeu' and out['valor'] is None:
        raise Erro(422, 'Informe o valor')
    if res == 'retornar':
        try:
            quando = datetime.strptime(str(b.get('retornar_em') or '')[:16], '%Y-%m-%dT%H:%M')
        except ValueError:
            raise Erro(422, 'Informe retornar_em AAAA-MM-DDTHH:MM')
        if quando <= c.agora():
            raise Erro(422, 'retornar_em precisa ser no futuro')
        out['retornar_em'] = iso(quando)
    motivo = b.get('motivo')
    if res == 'sem_interesse' and motivo not in MOTIVOS_SEM:
        raise Erro(422, 'Motivo inválido')
    if res == 'invalido' and motivo not in MOTIVOS_INV:
        raise Erro(422, 'Motivo inválido')
    if res in ('sem_interesse', 'invalido'):
        out['motivo'] = motivo
    produto = b.get('produto')
    if produto not in (None, ''):
        if not isinstance(produto, str):
            raise Erro(422, 'Produto inválido')
        out['produto'] = produto
    nota = b.get('nota')
    if nota not in (None, ''):
        out['nota'] = str(nota)
    return out


def fechar(c, ident, colab, b):
    """colab=None → gestor (fecha qualquer)."""
    ch = c.chamado(ident)
    if colab is not None and ch['dono'] != colab:
        raise Erro(403, 'Só o dono fecha o atendimento')
    if ch['status'] == 'fechado':
        raise Erro(409, 'Chamado já fechado')
    d = validar_fechamento(c, b)
    agora = c.agora()
    c.db.execute('UPDATE chamados SET status=?, resultado=?, valor=?, produto=?, motivo_fechamento=?, '
                 'nota_fechamento=?, retornar_em=?, fechado_em=?, ofertado_a=NULL WHERE id=?',
                 ('fechado', d['resultado'], d['valor'], d['produto'], d['motivo'], d['nota'], d['retornar_em'],
                  iso(agora), ident))
    lead = c.lead(ch['lead_id'])
    c.db.execute("UPDATE leads SET status=?, estado='{}' WHERE id=?", (STATUS_LEAD[d['resultado']], lead['id']))
    if d['motivo'] == 'nao_quer_contato':  # 1.9.8: some da retomada e da prospecção até ele voltar a escrever
        c.db.execute('UPDATE leads SET nao_contatar=1 WHERE id=?', (lead['id'],))
    evento = {'em': iso(agora), 'chamado_id': ident, 'colaborador': ch['dono'], 'resultado': d['resultado'],
              'valor': d['valor'], 'produto': d['produto'], 'motivo': d['motivo'], 'nota': d['nota'],
              # conta do início do prazo: a abertura do expediente, se o chamado chegou fora do horário
              'minutos_ate_assumir': (minutos(ch['conta_desde'] or ch['aberto_em'], parse(ch['assumido_em']))
                                      if ch['assumido_em'] else None),
              'minutos_atendimento': minutos(ch['assumido_em'], agora) if ch['assumido_em'] else None}
    c.db.execute('INSERT INTO historico(lead_id,dados) VALUES (?,?)', (lead['id'], json.dumps(evento, ensure_ascii=False)))
    _encerrar_mensagens(c, ch, f"✔️ #{ident} fechado: {d['resultado']}")
    if d['resultado'] == 'retornar':
        c.db.execute('INSERT OR REPLACE INTO retornos(chamado_id,lead_id,colaborador,em) VALUES (?,?,?,?)',
                     (ident, lead['id'], ch['dono'], d['retornar_em']))
        texto = f"Combinado! Vamos te procurar em {parse(d['retornar_em']).strftime('%d/%m às %H:%M')}."
        _registrar(c, lead['id'], ident, 'agente', texto)
        evolution.enviar_lead(c, c.lead(lead['id']), texto, 'aviso', automatica=True)
    limpar_fluxos(c, ident)
    from . import contatos
    contatos.marcar_visto(c, ch['dono'], lead['id'])  # "novas" contam a partir daqui (seção 12)
    c.sujo = True
    equipe.liberar_se_vazio(c, ch['dono'])
    return json_chamado(c, c.chamado(ident)) | {'evento': evento}


def limpar_fluxos(c, ident):
    for r in c.db.execute('SELECT colaborador, dados FROM tg_fluxo').fetchall():
        try:
            if json.loads(r['dados']).get('chamado') == ident:
                c.db.execute('DELETE FROM tg_fluxo WHERE colaborador=?', (r['colaborador'],))
        except ValueError:
            c.db.execute('DELETE FROM tg_fluxo WHERE colaborador=?', (r['colaborador'],))


def _encerrar_mensagens(c, ch, texto):
    if ch['tg_cartao']:
        tg.editar(c, ch['tg_cartao'], texto)
    for campo in ('tg_linha', 'tg_alerta', 'tg_oferta'):
        if ch[campo] and ch['status'] in ('aguardando', 'alerta'):
            tg.editar(c, ch[campo], texto)


def desistir_calado(c, ch):
    """1.10.8: chance de venda calada que esfriou ("só pesquisando") antes de alguém assumir: o chamado sai da
    fila sem incomodar a equipe (o cliente nunca soube dele)."""
    texto = f"↩️ #{ch['id']} o cliente disse que só está pesquisando; voltou para o assistente"
    _encerrar_mensagens(c, ch, texto)
    if ch['ofertado_a']:
        equipe.privado(c, ch['ofertado_a'], texto)
    c.db.execute("UPDATE chamados SET status='fechado', resultado='devolvido', fechado_em=?, ofertado_a=NULL, "
                 'ofertado_em=NULL WHERE id=?', (iso(c.agora()), ch['id']))
    limpar_fluxos(c, ch['id'])
    c.sujo = True


def encerrar_por_apagar(c, lead_id):
    """Lead pediu para apagar os dados (§4 regra 2): fecha os chamados abertos com resultado `apagado`,
    tira os dados dele das mensagens do Telegram (oferta, alerta, linha do grupo, cartão), avisa o dono,
    libera o colaborador e cancela o que ainda estava na fila de saída com dados dele."""
    lead = c.lead(lead_id)
    todos = [r['id'] for r in c.db.execute('SELECT id FROM chamados WHERE lead_id=?', (lead_id,))]
    abertos = c.db.execute("SELECT * FROM chamados WHERE lead_id=? AND status IN ('aguardando','alerta','atendendo')",
                           (lead_id,)).fetchall()
    # 1) fila do Telegram: o que ainda não saiu e tem dados dele não sai mais
    refs = []
    for ch in c.db.execute('SELECT tg_linha, tg_alerta, tg_oferta, tg_cartao FROM chamados WHERE lead_id=?',
                           (lead_id,)).fetchall():
        refs += [r[2:] for r in ch if r and str(r).startswith('q:')]
    filtros, args = [], []
    if todos:
        filtros.append(f"chamado_id IN ({','.join('?' * len(todos))})")
        args += todos
    if refs:
        filtros.append(f"id IN ({','.join('?' * len(refs))})")
        args += refs
    for tel in {lead['telefone'], formatar_telefone(lead['telefone'])}:
        if tel:
            filtros.append('instr(corpo, ?) > 0')
            args.append(tel)
    if filtros:
        c.db.execute(f"UPDATE tg_saida SET status='cancelado', corpo='{{}}' WHERE status='pendente' "
                     f"AND metodo<>'painel' AND ({' OR '.join(filtros)})", args)
    c.db.execute('DELETE FROM retornos WHERE lead_id=? AND enviado=0', (lead_id,))
    # 2) mensagens já entregues no privado do dono com dados dele ('💬 <nome>: <texto>', '📅 Retorno: ...',
    #    'Ainda com <nome>?'), de qualquer chamado do lead, inclusive os já fechados
    if todos:
        for m in c.db.execute(f"SELECT chat_id, message_id, chamado_id FROM tg_msgs WHERE (tipo IN "
                              f"('lead','lembrete','retorno') OR tipo LIKE 'sg:%') AND chamado_id IN ({','.join('?' * len(todos))})",
                              todos).fetchall():
            tg.editar(c, f"{m['chat_id']}:{m['message_id']}", f"🗑️ #{m['chamado_id']} lead pediu para apagar os dados")
    # 3) chamados abertos
    agora = iso(c.agora())
    for ch in abertos:
        ident = ch['id']
        texto = f'🗑️ #{ident} lead pediu para apagar os dados'
        c.db.execute("UPDATE chamados SET status='fechado', resultado='apagado', fechado_em=?, ofertado_a=NULL, "
                     'ofertado_em=NULL WHERE id=?', (agora, ident))
        for campo in ('tg_linha', 'tg_alerta', 'tg_oferta', 'tg_cartao'):
            if ch[campo]:
                tg.editar(c, ch[campo], texto)
        if ch['dono']:
            equipe.privado(c, ch['dono'], texto)
        limpar_fluxos(c, ident)
        equipe.liberar_se_vazio(c, ch['dono'])
    if abertos:
        if lead['status'] == 'em_atendimento':
            c.db.execute("UPDATE leads SET status=COALESCE(status_antes,'novo') WHERE id=?", (lead_id,))
        c.sujo = True
    return len(abertos)


def devolver(c, ident, colab):
    ch = c.chamado(ident)
    if colab is not None and ch['dono'] != colab:
        raise Erro(403, 'Só o dono devolve o atendimento')
    if ch['status'] == 'fechado':
        raise Erro(409, 'Chamado já fechado')
    agora = iso(c.agora())
    c.db.execute("UPDATE chamados SET status='fechado', resultado='devolvido', fechado_em=?, ofertado_a=NULL WHERE id=?",
                 (agora, ident))
    lead = c.lead(ch['lead_id'])
    if lead['status'] == 'em_atendimento':
        c.db.execute("UPDATE leads SET status=COALESCE(status_antes,'novo'), estado='{}' WHERE id=?", (lead['id'],))
    _encerrar_mensagens(c, ch, f'↩️ #{ident} devolvido ao bot')
    limpar_fluxos(c, ident)
    from . import contatos
    contatos.marcar_visto(c, ch['dono'], lead['id'])  # "novas" contam a partir daqui (seção 12)
    c.sujo = True
    equipe.liberar_se_vazio(c, ch['dono'])
    return json_chamado(c, c.chamado(ident))


def reabrir(c, ident):
    ch = c.chamado(ident)
    if ch['status'] != 'fechado':
        raise Erro(409, 'Chamado não está fechado')
    if aberto_do_lead(c, ch['lead_id']):
        raise Erro(409, 'O lead já tem chamado aberto')
    agora = c.agora()
    no_horario = horario.no_horario(c, agora)
    c.db.execute("UPDATE chamados SET status='aguardando', dono=NULL, assumido_em=NULL, fechado_em=NULL, resultado=NULL, "
                 "valor=NULL, produto=NULL, motivo_fechamento=NULL, nota_fechamento=NULL, retornar_em=NULL, "
                 "recusaram='[]', ofertado_a=NULL, ofertado_em=NULL, alertado=0, lembrado=0, conta_desde=?, "
                 "tg_linha=NULL, tg_alerta=NULL, tg_oferta=NULL, tg_cartao=NULL WHERE id=?",
                 (iso(agora) if no_horario else None, ident))
    c.db.execute('DELETE FROM retornos WHERE chamado_id=? AND enviado=0', (ident,))
    c.sujo = True
    if no_horario:
        ativar(c, ident)
    return json_chamado(c, c.chamado(ident))


def assumir_retorno(c, chamado_ref, colab):
    """Botão ra:<id> → novo chamado 'venda' já assumido pelo colaborador."""
    r = c.db.execute('SELECT * FROM retornos WHERE chamado_id=?', (chamado_ref,)).fetchone()
    if not r:
        raise Erro(404, 'Retorno inexistente')
    if r['colaborador'] and r['colaborador'] != colab:
        raise Erro(403, 'Retorno de outro colaborador')
    if c.colab(colab)['status'] == 'fora':
        raise Erro(409, 'Quem está fora não pode assumir')
    aberto = aberto_do_lead(c, r['lead_id'])
    if aberto:
        if aberto['status'] == 'atendendo':
            raise Erro(409, f"já foi assumido por {c.nome_colab(aberto['dono'])}")
        return assumir(c, aberto['id'], colab)
    from . import cerebro
    lead = c.lead(r['lead_id'])
    agora = iso(c.agora())
    ident = c.db.execute(
        'INSERT INTO chamados(lead_id,motivo,prioridade,status,aberto_em,conta_desde,token,resumo,dono,assumido_em,'
        'ultimo_mov) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
        (lead['id'], 'venda', 'quente', 'atendendo', agora, agora, novo_token(), cerebro.resumo(c, lead, 'venda'),
         colab, agora, agora)).lastrowid
    c.db.execute('UPDATE retornos SET assumido=1 WHERE chamado_id=?', (chamado_ref,))
    _pos_assumir(c, c.chamado(ident), colab, avisar_lead=False)
    return json_chamado(c, c.chamado(ident))
