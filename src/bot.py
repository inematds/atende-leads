"""Webhook do Telegram (seção 16): vínculo, botões, comandos, respostas ao lead e fechamento guiado."""
import hmac
import json
import os
import re
import shlex
import subprocess
import tempfile
from datetime import datetime, timedelta

from .core import Erro, formatar_telefone, iso, log, normalizar
from . import chamados, equipe, limite
from . import telegram as tg

ENTRAR = 'Envie /entrar <seu código>.'
MOTIVOS_BT = {
    'sem_interesse': [('💸 Preço', 'preco'), ('🛒 Já comprou', 'ja_comprou'), ('👀 Curioso', 'curioso'),
                      ('Outro', 'outro')],
    'invalido': [('📵 Número errado', 'numero_errado'), ('🚫 Spam', 'spam'), ('🙅 Não é lead', 'nao_e_lead')],
}
AJUDA = ('Comandos: /livre /ocupado /fora /status /meus /retornos /lead <nome ou telefone> '
         '/fechar <id> vendeu <valor> | retornar <AAAA-MM-DDTHH:MM> | negociando | sem <motivo> | invalido <motivo>')


def autorizar(headers):
    segredo = os.environ.get('TELEGRAM_SEGREDO', '')
    recebido = headers.get('X-Telegram-Bot-Api-Secret-Token', '') or ''
    if not segredo or not hmac.compare_digest(recebido.encode(), segredo.encode()):
        raise Erro(401, 'Segredo inválido')


def botoes_status():
    return [[tg.bt('🟢 Livre', 'st:livre'), tg.bt('🔴 Ocupado', 'st:ocupado'), tg.bt('⚫ Fora', 'st:fora')]]


def receber(c, u):
    if not isinstance(u, dict):
        return
    if isinstance(u.get('callback_query'), dict):
        callback(c, u['callback_query'])
    elif isinstance(u.get('message'), dict):
        mensagem(c, u['message'])


# ---------- fluxo de fechamento ----------
def fluxo(c, colab):
    r = c.db.execute('SELECT dados FROM tg_fluxo WHERE colaborador=?', (colab,)).fetchone()
    try:
        return json.loads(r['dados']) if r else None
    except ValueError:
        return None


def gravar_fluxo(c, colab, f):
    if f is None:
        c.db.execute('DELETE FROM tg_fluxo WHERE colaborador=?', (colab,))
    else:
        c.db.execute('INSERT OR REPLACE INTO tg_fluxo VALUES (?,?)', (colab, json.dumps(f, ensure_ascii=False)))


def _dono_ok(c, ident, colab):
    ch = c.chamado(ident)
    if ch['dono'] != colab:
        raise Erro(403, 'Só o dono fecha o atendimento')
    if ch['status'] == 'fechado':
        raise Erro(409, 'Chamado já fechado')
    return ch


def pedir_nota(c, colab, f):
    f['etapa'] = 'nota'
    gravar_fluxo(c, colab, f)
    equipe.privado(c, colab, f"Quer deixar uma nota sobre #{f['chamado']}? Escreva ou mande um áudio.",
                   [[tg.bt('Pular', f"fp:{f['chamado']}")]])


def iniciar_fechamento(c, colab, ident, resultado):
    _dono_ok(c, ident, colab)
    if resultado not in chamados.RESULTADOS:
        raise Erro(422, 'Resultado inválido')
    f = {'chamado': ident, 'resultado': resultado}
    if resultado == 'vendeu':
        f['etapa'] = 'valor'
        gravar_fluxo(c, colab, f)
        equipe.privado(c, colab, f'Qual o valor da venda de #{ident}? (ex.: 1200 ou 1.200,50)')
    elif resultado == 'retornar':
        f['etapa'] = 'data'
        gravar_fluxo(c, colab, f)
        equipe.privado(c, colab, f'Quando retornar o contato de #{ident}?',
                       [[tg.bt('Amanhã 09:00', f'fr:{ident}:1')], [tg.bt('Em 3 dias 09:00', f'fr:{ident}:3')],
                        [tg.bt('Semana que vem 09:00', f'fr:{ident}:7')]])
    elif resultado in MOTIVOS_BT:
        f['etapa'] = 'motivo'
        gravar_fluxo(c, colab, f)
        equipe.privado(c, colab, f'Qual o motivo? (#{ident})',
                       [[tg.bt(rot, f'fm:{ident}:{m}')] for rot, m in MOTIVOS_BT[resultado]])
    else:
        pedir_nota(c, colab, f)


def concluir(c, colab, f, nota):
    corpo = {k: f.get(k) for k in ('resultado', 'valor', 'motivo', 'retornar_em')}
    corpo['nota'] = nota
    gravar_fluxo(c, colab, None)
    try:
        chamados.fechar(c, f['chamado'], colab, corpo)
    except Erro as e:
        equipe.privado(c, colab, f"Não deu para fechar #{f['chamado']}: {e.mensagem}")
        return
    equipe.privado(c, colab, f"✔️ Atendimento #{f['chamado']} fechado: {f['resultado']}. Você está livre de novo.")


def valor_texto(texto):
    t = re.sub(r'[^\d,.]', '', texto or '')
    if not t:
        return None
    if ',' in t:
        t = t.replace('.', '').replace(',', '.')
    elif t.count('.') > 1 or re.fullmatch(r'\d{1,3}(\.\d{3})+', t):
        t = t.replace('.', '')
    try:
        return float(t)
    except ValueError:
        return None


def transcrever(c, file_id):
    """Baixar e transcrever roda FORA do lock (c.pronto desfaz a transação e repete com o texto)."""
    cmd = os.environ.get('WHISPER_CMD')
    if not cmd or not file_id:
        return '[áudio]'
    return c.pronto(('audio', str(file_id)), lambda: _transcrever(cmd, file_id)) or '[áudio]'


def _transcrever(cmd, file_id):
    """Só rede e subprocesso: não toca no banco."""
    with tempfile.TemporaryDirectory() as tmp:
        caminho = os.path.join(tmp, 'audio.ogg')
        if not tg.baixar_arquivo(file_id, caminho):
            return '[áudio]'
        try:
            r = subprocess.run(shlex.split(cmd) + [caminho], capture_output=True, text=True, timeout=180)
            texto = (r.stdout or '').strip()
            return texto or '[áudio]'
        except (OSError, subprocess.SubprocessError) as e:
            log(f'whisper: falhou: {type(e).__name__}')
            return '[áudio]'


# ---------- callbacks ----------
def callback(c, cq):
    cid = cq.get('id')
    dados = str(cq.get('data') or '')
    from_id = str((cq.get('from') or {}).get('id', ''))
    colab = equipe.colab_por_telegram(c, from_id)
    if not colab:
        tg.responder_callback(c, cid, ENTRAR)
        if from_id:
            tg.enviar(c, from_id, ENTRAR)
        return
    resposta = ''
    try:
        resposta = _callback(c, colab, dados, cq) or ''
    except Erro as e:
        resposta = e.mensagem
        equipe.privado(c, colab, e.mensagem)
    except (ValueError, KeyError, TypeError, IndexError):
        resposta = 'Botão inválido.'
    tg.responder_callback(c, cid, resposta[:190])


def _id(parte):
    return int(parte)


def _callback(c, colab, dados, cq):
    partes = dados.split(':')
    pre = partes[0]
    if pre == 'as':
        ident = _id(partes[1])
        chamados.assumir(c, ident, colab, restrito=True)
        return f'Você assumiu #{ident}'
    if pre == 'pa':
        ident = _id(partes[1])
        chamados.passar(c, ident, colab)
        return f'#{ident} passou para o próximo'
    if pre == 'st':
        r = equipe.mudar_status(c, colab, partes[1])
        return f"Status: {r['status']}"
    if pre == 'fe':
        iniciar_fechamento(c, colab, _id(partes[1]), partes[2])
        return ''
    if pre == 'fm':
        ident, motivo = _id(partes[1]), partes[2]
        f = fluxo(c, colab)
        if not f or f.get('chamado') != ident:
            ch = _dono_ok(c, ident, colab)
            res = 'invalido' if motivo in chamados.MOTIVOS_INV else 'sem_interesse'
            f = {'chamado': ch['id'], 'resultado': res}
        f['motivo'] = motivo
        pedir_nota(c, colab, f)
        return ''
    if pre == 'fr':
        ident, dias = _id(partes[1]), int(partes[2])
        if dias not in (1, 3, 7):
            raise Erro(422, 'Prazo inválido')
        f = fluxo(c, colab)
        if not f or f.get('chamado') != ident:
            _dono_ok(c, ident, colab)
            f = {'chamado': ident, 'resultado': 'retornar'}
        dia = (c.agora() + timedelta(days=dias)).date()
        f['retornar_em'] = iso(datetime.combine(dia, datetime.strptime('09:00', '%H:%M').time()))
        pedir_nota(c, colab, f)
        return ''
    if pre == 'fp':
        ident = _id(partes[1])
        f = fluxo(c, colab)
        if not f or f.get('chamado') != ident:
            raise Erro(409, 'Nenhum fechamento em andamento')
        concluir(c, colab, f, None)
        return 'Fechado'
    if pre == 'dv':
        ident = _id(partes[1])
        chamados.devolver(c, ident, colab)
        chamados.limpar_fluxos(c, ident)
        equipe.privado(c, colab, f'↩️ #{ident} devolvido ao bot. Você está livre de novo.')
        return 'Devolvido ao bot'
    if pre == 'lc':
        ident = _id(partes[1])
        ch = c.chamado(ident)
        if ch['dono'] != colab or ch['status'] != 'atendendo':
            raise Erro(409, 'Atendimento não está com você')
        c.db.execute('UPDATE chamados SET ultimo_mov=?, lembrado=0 WHERE id=?', (iso(c.agora()), ident))
        return 'Certo, seguimos.'
    if pre == 'lt':
        ident = _id(partes[1])
        ch = _dono_ok(c, ident, colab)
        equipe.privado(c, colab, f'Como terminou #{ident}?', chamados.botoes_fechamento(c, ch))
        return ''
    if pre == 'ra':
        ident = _id(partes[1])
        chamados.assumir_retorno(c, ident, colab)
        return 'Retorno assumido'
    if pre == 'sg':
        from . import sugestao
        sid, acao = _id(partes[1]), partes[2]
        s, ch = sugestao.obter(c, sid, colab)
        if acao == 'ok':
            chamados.responder(c, ch['id'], colab, s['texto'], sugestao_id=sid)
            return 'Enviada'
        if acao == 'ed':
            ref = equipe.privado(c, colab, f"✏️ Mande o texto editado respondendo a esta mensagem.\n\n{s['texto']}")
            chamados.guardar_msg(c, ref, ch['id'], f'sg:{sid}')
            return 'Mande o texto editado'
        raise Erro(422, 'Botão inválido.')
    return ''


# ---------- mensagens ----------
def mensagem(c, msg):
    chat = msg.get('chat') or {}
    chat_id = str(chat.get('id', ''))
    from_id = str((msg.get('from') or {}).get('id', ''))
    texto = msg.get('text') if isinstance(msg.get('text'), str) else ''
    grupo = tg.grupo()
    no_grupo = chat.get('type') in ('group', 'supergroup', 'channel') or (grupo and chat_id == str(grupo))
    cmd, _, resto = texto.strip().partition(' ')
    cmd = cmd.split('@')[0].lower()
    resto = resto.strip()
    if no_grupo:
        # Só o grupo da equipe (TELEGRAM_GRUPO_ID); em qualquer outro grupo o bot fica calado.
        if cmd == '/status' and grupo and chat_id == str(grupo):
            tg.enviar(c, chat_id, equipe.texto_painel(c))
        return
    if not from_id:
        return
    if cmd == '/entrar':
        chave = ('entrar', from_id)
        if limite.bloqueado(chave):
            tg.enviar(c, chat_id or from_id, limite.MENSAGEM)
            return
        membro = next((m for m in c.cfg.get('equipe', [])
                       if resto and hmac.compare_digest(str(m.get('codigo', '')).encode(), resto.encode())), None)
        if not membro:
            limite.falhou(chave)
            tg.enviar(c, chat_id or from_id, 'Código inválido.')
            return
        antes = equipe.vinculado(c, membro['id'])
        if antes and str(antes) != from_id:
            tg.enviar(c, antes, f"⚠️ Seu código foi usado em outra conta do Telegram e o bot passou a falar com ela. "
                                f"Se não foi você, avise o gestor para trocar o seu código.")
        c.db.execute('UPDATE colaboradores SET telegram_id=NULL WHERE telegram_id=?', (from_id,))
        c.db.execute('UPDATE colaboradores SET telegram_id=? WHERE id=?', (from_id, membro['id']))
        tg.enviar(c, from_id, f"Olá, {membro['nome']}!", botoes_status())
        chamados.distribuir(c)
        return
    colab = equipe.colab_por_telegram(c, from_id)
    if not colab:
        tg.enviar(c, chat_id or from_id, ENTRAR)
        return
    try:
        _mensagem(c, colab, msg, texto, cmd, resto)
    except Erro as e:
        equipe.privado(c, colab, e.mensagem)


def _mensagem(c, colab, msg, texto, cmd, resto):
    voz = msg.get('voice') or msg.get('audio')
    f = fluxo(c, colab)
    if voz:
        if f and f.get('etapa') == 'nota':
            concluir(c, colab, f, transcrever(c, voz.get('file_id')))
        else:
            equipe.privado(c, colab, 'Áudio só é usado como nota durante o fechamento.')
        return
    if cmd in ('/livre', '/ocupado', '/fora'):
        r = equipe.mudar_status(c, colab, cmd[1:])
        equipe.privado(c, colab, f"Status: {r['status']}", botoes_status())
        return
    if cmd == '/status':
        equipe.privado(c, colab, equipe.texto_painel(c))
        return
    if cmd == '/meus':
        linhas = [f"#{ch['id']} {c.lead(ch['lead_id'])['nome'] or 'lead'} · {chamados.MOTIVO_LEG[ch['motivo']]}"
                  for ch in equipe.atendendo_de(c, colab)]
        equipe.privado(c, colab, 'Seus atendimentos:\n' + '\n'.join(linhas) if linhas else 'Nenhum atendimento aberto.')
        return
    if cmd == '/retornos':
        rs = retornos_hoje(c, colab)
        linhas = [f"{r['em'][11:16]} {r['nome'] or 'lead'} {formatar_telefone(r['telefone'])}" for r in rs]
        equipe.privado(c, colab, 'Retornos de hoje:\n' + '\n'.join(linhas) if linhas else 'Nenhum retorno hoje.')
        return
    if cmd == '/lead':
        equipe.privado(c, colab, buscar_lead(c, colab, resto))
        return
    if cmd == '/fechar':
        comando_fechar(c, colab, resto)
        return
    if cmd == '/start':
        equipe.privado(c, colab, f"Olá, {c.nome_colab(colab)}!", botoes_status())
        return
    reply = (msg.get('reply_to_message') or {}).get('message_id')
    if reply is not None and texto:
        chat_id = str((msg.get('chat') or {}).get('id', ''))
        r = c.db.execute('SELECT chamado_id, tipo FROM tg_msgs WHERE chat_id=? AND message_id=?',
                         (chat_id, str(reply))).fetchone()
        if r:
            ch = c.chamado(r['chamado_id'])
            if ch['dono'] == colab and ch['status'] == 'atendendo':
                sid = None
                if str(r['tipo'] or '').startswith('sg:'):  # reply ao 💡 ou ao "Mande o texto editado"
                    s = c.db.execute("SELECT id FROM sugestoes WHERE id=? AND status='pronta'",
                                     (str(r['tipo'])[3:],)).fetchone()
                    sid = s['id'] if s else None
                chamados.responder(c, ch['id'], colab, texto, sugestao_id=sid)
                return
            raise Erro(409, 'Esse atendimento não está com você.')
    if f and texto:
        if f.get('etapa') == 'valor':
            v = valor_texto(texto)
            if v is None or v < 0:
                equipe.privado(c, colab, 'Não entendi o valor. Mande só o número, ex.: 1200')
                return
            f['valor'] = v
            pedir_nota(c, colab, f)
            return
        if f.get('etapa') == 'nota':
            concluir(c, colab, f, texto.strip())
            return
    equipe.privado(c, colab, AJUDA)


def comando_fechar(c, colab, resto):
    partes = resto.split()
    if len(partes) < 2 or not partes[0].lstrip('#').isdigit():
        raise Erro(422, 'Use: /fechar <id> vendeu <valor> | retornar <AAAA-MM-DDTHH:MM> | negociando | '
                        'sem <motivo> | invalido <motivo>')
    ident = int(partes[0].lstrip('#'))
    tipo = normalizar(partes[1])
    corpo, extra = {}, partes[2:]
    if tipo == 'vendeu':
        v = valor_texto(extra[0]) if extra else None
        if v is None:
            raise Erro(422, 'Informe o valor: /fechar <id> vendeu <valor>')
        corpo = {'resultado': 'vendeu', 'valor': v}
        extra = extra[1:]
    elif tipo == 'retornar':
        corpo = {'resultado': 'retornar', 'retornar_em': extra[0] if extra else None}
        extra = extra[1:]
    elif tipo == 'negociando':
        corpo = {'resultado': 'negociando'}
    elif tipo in ('sem', 'sem_interesse'):
        corpo = {'resultado': 'sem_interesse', 'motivo': extra[0] if extra else None}
        extra = extra[1:]
    elif tipo in ('invalido',):
        corpo = {'resultado': 'invalido', 'motivo': extra[0] if extra else None}
        extra = extra[1:]
    else:
        raise Erro(422, 'Resultado inválido')
    if extra:
        corpo['nota'] = ' '.join(extra)
    chamados.fechar(c, ident, colab, corpo)
    equipe.privado(c, colab, f"✔️ Atendimento #{ident} fechado: {corpo['resultado']}.")


# ---------- consultas ----------
def pode_ver(c, colab, lead_id):
    for ch in c.db.execute('SELECT ofertado_a, dono, status, recusaram FROM chamados WHERE lead_id=?', (lead_id,)):
        if ch['ofertado_a'] == colab or ch['dono'] == colab or ch['status'] == 'alerta':
            return True
        if colab in chamados.recusaram(ch):
            return True
    return False


def retornos_hoje(c, colab):
    hoje = c.agora().date().isoformat()
    out = []
    for r in c.db.execute('SELECT * FROM retornos WHERE colaborador=? AND substr(em,1,10)=? ORDER BY em', (colab, hoje)):
        lead = c.lead(r['lead_id'])
        out.append({'chamado_id': r['chamado_id'], 'lead_id': r['lead_id'], 'nome': lead['nome'],
                    'telefone': lead['telefone'], 'em': r['em'], 'enviado': bool(r['enviado']),
                    'assumido': bool(r['assumido'])})
    return out


def buscar_lead(c, colab, q):
    q = (q or '').strip()
    if not q:
        return 'Use: /lead <nome ou telefone>'
    qn, qd = normalizar(q), re.sub(r'\D', '', q)
    achados = []
    for lead in c.db.execute('SELECT * FROM leads ORDER BY id DESC'):
        if not pode_ver(c, colab, lead['id']):
            continue
        if (qd and len(qd) >= 4 and qd in lead['telefone']) or (qn and qn in normalizar(lead['nome'] or '')):
            achados.append(lead)
        if len(achados) >= 5:
            break
    if not achados:
        return 'Nenhum lead encontrado entre os que você pode ver.'
    linhas = []
    for lead in achados:
        prod = c.produto(lead['interesse']) if lead['interesse'] else None
        linhas.append(f"Lead {lead['id']}: {lead['nome'] or 'sem nome'} · {formatar_telefone(lead['telefone'])} · "
                      f"nota {lead['nota']} · {lead['status']}" + (f" · {prod['nome']}" if prod else ''))
    return '\n'.join(linhas)

