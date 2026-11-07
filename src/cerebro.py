"""Cérebro do agente (seção 14). 'regras' cobre tudo; os tipos LLM resumem, tiram dúvida, sugerem respostas
à equipe e propõem itens para a base.

Tipos: regras | anthropic | openrouter | openai | ollama | claude_cli | codex_cli.
Qualquer erro, timeout, recusa ou resposta vazia cai na regra. A chave vem só de CEREBRO_API_KEY (nunca do
JSON). anthropic/openrouter têm URL fixa (host sempre permitido); openai/ollama usam cerebro.url, e a chave só
vai a host de CEREBRO_HOSTS_PERMITIDOS. Nenhuma chamada (rede ou subprocesso) acontece dentro do lock do banco.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

from . import rede
from .core import log

URGENCIA = {1: 'hoje', 2: 'este mês', 3: 'pesquisando'}
ASSUNTO = {'pediu_humano': 'falar com alguém', 'venda': 'comprar', 'precisa': 'resolver um problema', 'retomada': 'retomar a conversa',
           'gestor': 'falar com a equipe'}
TIPOS = ('regras', 'anthropic', 'openrouter', 'openai', 'ollama', 'claude_cli', 'codex_cli')
ESFORCOS = ('low', 'medium', 'high', 'xhigh', 'max')
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODELO_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.:/@_-]{0,99}$')
TIMEOUTS = {'ollama': 15, 'openai': 15, 'anthropic': 20, 'openrouter': 20, 'claude_cli': 60, 'codex_cli': 60}
MAX_TOKENS = 1024
MAX_TOKENS_CURADORIA = 4096
PAPEIS = ('principal', 'curadoria')


def cfg(c, papel='principal'):
    """`curadoria` (propostas para a base): `cerebro_curadoria` se tiver tipo; senão o `cerebro` principal."""
    if papel == 'curadoria':
        v = c.cfg.get('cerebro_curadoria')
        if isinstance(v, dict) and v.get('tipo'):
            return v
    v = c.cfg.get('cerebro')
    return v if isinstance(v, dict) else {}


def propria(c):
    """True se a curadoria tem cérebro próprio (senão herda o principal)."""
    v = c.cfg.get('cerebro_curadoria')
    return isinstance(v, dict) and bool(v.get('tipo'))


def chave_api(papel='principal'):
    if papel == 'curadoria':
        return os.environ.get('CEREBRO_CURADORIA_API_KEY') or os.environ.get('CEREBRO_API_KEY') or ''
    return os.environ.get('CEREBRO_API_KEY') or ''


def tipo(c, papel='principal'):
    t = cfg(c, papel).get('tipo') or 'regras'
    return t if t in TIPOS else 'regras'


def timeout(t, papel='principal'):
    """A curadoria (saída longa, modelo mais forte, poucas chamadas) tem 3× o tempo."""
    try:
        teste = float(os.environ.get('CEREBRO_TIMEOUT_S') or 0)
    except ValueError:
        teste = 0
    padrao = TIMEOUTS.get(t, 15) * (3 if papel == 'curadoria' else 1)
    return min(padrao, teste) if teste > 0 else padrao


_BINS = {}


def binario(t):
    """Caminho do CLI (resolvido uma vez: a saúde é servida fora do lock e precisa ser rápida)."""
    nome = os.environ.get('CEREBRO_CLI_BIN') or ('claude' if t == 'claude_cli' else 'codex')
    if nome not in _BINS:
        _BINS[nome] = shutil.which(nome)
    return _BINS[nome]


def disponivel(c, papel='principal'):
    """(ok, motivo). ok=False → tudo por regras."""
    t = tipo(c, papel)
    k = cfg(c, papel)
    if t == 'regras':
        return True, None
    modelo = str(k.get('modelo') or '')
    if t in ('anthropic', 'openrouter'):
        if not chave_api(papel):
            return False, 'CEREBRO_API_KEY não definida no .env'
        if not modelo:
            return False, 'cerebro.modelo vazio'
        return True, None
    if t in ('ollama', 'openai'):
        if not str(k.get('url') or '') or not modelo:
            return False, 'cerebro.url ou cerebro.modelo vazio'
        return True, None
    if not binario(t):
        nome = os.environ.get('CEREBRO_CLI_BIN') or ('claude' if t == 'claude_cli' else 'codex')
        return False, f'binário {nome!r} não encontrado (o CLI só existe rodando direto na máquina, não no Docker)'
    if t == 'codex_cli' and not modelo:
        return False, 'cerebro.modelo vazio'
    return True, None


def ligado(c, papel='principal'):
    return tipo(c, papel) != 'regras' and disponivel(c, papel)[0]


def _ultima(c, lead_id):
    r = c.db.execute("SELECT texto FROM mensagens WHERE lead_id=? AND de='lead' ORDER BY id DESC LIMIT 1",
                     (lead_id,)).fetchone()
    return r['texto'] if r else ''


def resumo_regras(c, lead, motivo):
    linhas = []
    prod = c.produto(lead['interesse']) if lead['interesse'] else None
    linhas.append(f"Quer: {prod['nome'] if prod else ASSUNTO.get(motivo, 'atendimento')}")
    if lead['urgencia'] in URGENCIA:
        linhas.append(f"Urgência: {URGENCIA[lead['urgencia']]}")
    ultima = _ultima(c, lead['id'])
    if ultima:
        linhas.append(f'Disse: "{ultima[:120]}"')
    return '\n'.join(linhas)


def conversa_texto(c, lead_id, n=10):
    hist = c.db.execute('SELECT de, texto FROM mensagens WHERE lead_id=? ORDER BY id DESC LIMIT ?',
                        (lead_id, n)).fetchall()
    nomes = {'lead': 'cliente', 'agente': 'atendente virtual', 'humano': 'vendedor'}
    return '\n'.join(f"{nomes.get(r['de'], r['de'])}: {r['texto']}" for r in reversed(hist))


def resumo(c, lead, motivo):
    regra = resumo_regras(c, lead, motivo)
    if not ligado(c):
        return regra
    texto = perguntar(c, 'Resuma em até 3 linhas curtas, em português do Brasil, texto simples sem markdown, o que o cliente quer e a urgência. '
                         'Não invente nada que não esteja na conversa.', conversa_texto(c, lead['id']))
    if not texto:
        return regra
    return '\n'.join(texto.strip().splitlines()[:3])


VERDADE_ATENDENTE = (
    ' Ordem de verdade: (1) o que o vendedor (atendente humano) já afirmou nesta conversa — preço, promoção, '
    'prazo, condição — é a informação mais atual e vale sobre a base; se ele afirmou valores diferentes em '
    'momentos diferentes, vale o ÚLTIMO; (2) a base. Nunca mencione base, sistema, IA nem divergência interna, '
    'e não peça desculpa por inconsistência.')


def tem_atendente(c, lead_id):
    return bool(lead_id) and c.db.execute("SELECT 1 FROM mensagens WHERE lead_id=? AND de='humano' LIMIT 1",
                                          (lead_id,)).fetchone() is not None


def responder_duvida(c, texto, lead_id=None):
    """Usado quando caiu em 'não entendi' (e na espera por alguém). Devolve texto ou None (→ regra).
    Se um vendedor já falou na conversa, as últimas mensagens vão no contexto e o que ele afirmou vale sobre a base."""
    if not ligado(c):
        return None
    from . import base
    instr = base.instrucoes(c).replace('Se a base não responder, diga que vai chamar alguém da equipe.',
                                       'Se nem a conversa nem a base responderem, responda exatamente: SEM_RESPOSTA '
                                       '(o sistema chama alguém da equipe).')
    # 1.10.8: quem decide e conta ao cliente que a equipe vem é o sistema, nunca o modelo
    instr += (' Nunca diga que vai chamar, avisar, encaminhar ou passar o cliente para alguém da equipe, nem prometa '
              'contato de uma pessoa ou ligação.')
    usuario = texto
    if tem_atendente(c, lead_id):
        instr = instr.replace('Use SOMENTE a base de conhecimento abaixo.',
                              'Use SOMENTE a conversa e a base de conhecimento abaixo.') + VERDADE_ATENDENTE
        usuario = (f'Conversa (mais recente por último):\n{conversa_texto(c, lead_id, 10)}\n\n'
                   f'Responda à última mensagem do cliente: {texto}')
    r = perguntar(c, instr, usuario, base.texto_base(c))
    if not r or 'SEM_RESPOSTA' in r:
        return None
    return r.strip()



def ler_json(texto):
    """Objeto JSON de uma resposta do modelo: puro, dentro de ```json```, ou com texto em volta. None se não houver."""
    import json
    if not isinstance(texto, str) or '{' not in texto:
        return None
    t = texto.strip()
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', t, re.S)
    candidatos = [m.group(1)] if m else []
    candidatos.append(t[t.index('{'):t.rindex('}') + 1])
    for cand in candidatos:
        try:
            d = json.loads(cand)
        except ValueError:
            continue
        if isinstance(d, dict):
            return d
    return None


def limpar_md(texto):
    """O modelo às vezes responde em markdown (**negrito**, # título, - lista); o lead e o Telegram veem texto puro."""
    if not texto:
        return texto
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
    t = re.sub(r'__(.+?)__', r'\1', t)
    t = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', t)
    t = re.sub(r'(?m)^\s*[-*]\s+', '• ', t)
    return t.replace('**', '').strip()

def perguntar(c, instrucoes, usuario, base_txt=None, papel='principal', formato=None, limpar=True, anexo=None):
    """A chamada ao modelo roda FORA do lock: c.pronto desfaz a transação, chama e repete com o resultado.
    Fora de uma transação (trabalhador em segundo plano), chama direto.

    `papel`: 'principal' (respostas, resumo, sugestão) ou 'curadoria' (propostas para a base).
    `formato`: JSON Schema da saída (structured outputs só no tipo anthropic; nos outros vale a instrução).
    `limpar=False` devolve o texto cru (saída JSON: quem chama limpa o campo de texto).
    `anexo`: {'media_type': 'application/pdf', 'data': <base64>} — vai como bloco `document` (só no tipo anthropic;
    nos outros tipos é ignorado, e quem chama só manda anexo com curadoria anthropic)."""
    ok, _motivo = disponivel(c, papel)
    t = tipo(c, papel)
    if t == 'regras' or not ok:
        return None
    k = dict(cfg(c, papel))
    k['_referer'] = c.url_publica() or 'https://github.com/inematds/atende-leads'
    k['_max_tokens'] = MAX_TOKENS_CURADORIA if papel == 'curadoria' else MAX_TOKENS
    k['_formato'] = formato
    k['_papel'] = papel
    k['_anexo'] = anexo if t == 'anthropic' else None
    marca = hashlib.sha256(str((anexo or {}).get('data') or '').encode()).hexdigest() if anexo else ''
    # a chave da API nunca entra nesta tupla (ela vira texto de exceção/log); o anexo entra só como hash
    chave = ('cerebro', papel, t, str(k.get('url') or ''), str(k.get('modelo') or ''), str(k.get('esforco') or ''),
             instrucoes, base_txt or '', usuario, bool(formato), marca)
    r = c.pronto(chave, lambda: _perguntar(t, k, instrucoes, base_txt, usuario))
    return limpar_md(r) if limpar else r


def hosts_permitidos():
    return {h.strip().lower() for h in (os.environ.get('CEREBRO_HOSTS_PERMITIDOS') or '').split(',') if h.strip()}


def host_permitido(url):
    """A CEREBRO_API_KEY só vai a um host listado em CEREBRO_HOSTS_PERMITIDOS (vazio = a nenhum). Quem tem o
    token do gestor pode mudar cerebro.url; sem esta lista, poderia apontar para um servidor seu e ler a chave."""
    partes = urlsplit(url)
    host = (partes.hostname or '').lower()
    permitidos = hosts_permitidos()
    if host and (host in permitidos or (partes.netloc or '').lower() in permitidos):
        return True
    if os.environ.get('CEREBRO_API_KEY'):
        log(f'cérebro: CEREBRO_API_KEY não enviada a {host or "?"} (fora de CEREBRO_HOSTS_PERMITIDOS)')
    return False


def corpo_anthropic(k, instrucoes, base_txt, usuario):
    system = [{'type': 'text', 'text': instrucoes}]
    if base_txt:
        system.append({'type': 'text', 'text': 'Base de conhecimento:\n' + base_txt,
                       'cache_control': {'type': 'ephemeral'}})
    esforco = k.get('esforco') if k.get('esforco') in ESFORCOS else 'low'
    saida = {'effort': esforco}
    if k.get('_formato'):
        saida['format'] = {'type': 'json_schema', 'schema': k['_formato']}
    return {'model': k.get('modelo'), 'max_tokens': k.get('_max_tokens') or MAX_TOKENS, 'system': system,
            'messages': [{'role': 'user', 'content': _conteudo(k, usuario)}],
            'output_config': saida, 'fallbacks': 'default'}


def _conteudo(k, usuario):
    """Texto puro, ou [bloco document (PDF em base64), texto] quando há anexo."""
    a = k.get('_anexo')
    if not a:
        return usuario
    return [{'type': 'document', 'source': {'type': 'base64', 'media_type': a.get('media_type') or 'application/pdf',
                                            'data': a.get('data') or ''}},
            {'type': 'text', 'text': usuario}]


def _texto_anthropic(r):
    if not isinstance(r, dict) or r.get('stop_reason') == 'refusal':
        return None
    for bloco in r.get('content') or []:
        if isinstance(bloco, dict) and bloco.get('type') == 'text':
            return bloco.get('text')
    return None


def _texto_openai(r):
    escolhas = r.get('choices') if isinstance(r, dict) else None
    if not escolhas or not isinstance(escolhas, list) or not isinstance(escolhas[0], dict):
        return None
    return (escolhas[0].get('message') or {}).get('content')


def _perguntar(t, k, instrucoes, base_txt, usuario):
    """Só rede/subprocesso: não toca no banco."""
    modelo = k.get('modelo')
    sistema = instrucoes + ('\n\nBase de conhecimento:\n' + base_txt if base_txt else '')
    msgs = [{'role': 'system', 'content': sistema}, {'role': 'user', 'content': usuario}]
    chave = chave_api(k.get('_papel') or 'principal')
    mx = k.get('_max_tokens') or MAX_TOKENS
    to = timeout(t, k.get('_papel') or 'principal')
    texto = None
    try:
        if t == 'anthropic':
            url = os.environ.get('CEREBRO_ANTHROPIC_URL') or ANTHROPIC_URL
            headers = {'x-api-key': chave, 'anthropic-version': '2023-06-01',
                       'anthropic-beta': 'server-side-fallback-2026-07-01'}
            ok, r = rede.postar(url, corpo_anthropic(k, instrucoes, base_txt, usuario), headers, timeout=to)
            texto = _texto_anthropic(r) if ok else None
        elif t == 'openrouter':
            url = os.environ.get('CEREBRO_OPENROUTER_URL') or OPENROUTER_URL
            headers = {'Authorization': f'Bearer {chave}', 'HTTP-Referer': k.get('_referer') or '',
                       'X-Title': 'atende-leads'}
            ok, r = rede.postar(url, {'model': modelo, 'messages': msgs, 'max_tokens': mx}, headers,
                                timeout=to)
            texto = _texto_openai(r) if ok else None
        elif t == 'ollama':
            url = str(k.get('url') or '').rstrip('/')
            ok, r = rede.postar(url + '/api/chat', {'model': modelo, 'messages': msgs, 'stream': False}, timeout=to)
            texto = (r.get('message') or {}).get('content') if ok else None
        elif t == 'openai':
            url = str(k.get('url') or '').rstrip('/')
            if url.endswith('/chat/completions'):
                destino = url
            elif url.endswith('/v1'):
                destino = url + '/chat/completions'
            else:
                destino = url + '/v1/chat/completions'
            headers = {}
            if chave and host_permitido(destino):
                headers['Authorization'] = f'Bearer {chave}'
            ok, r = rede.postar(destino, {'model': modelo, 'messages': msgs, 'temperature': 0.2}, headers, timeout=to)
            texto = _texto_openai(r) if ok else None
        elif t in ('claude_cli', 'codex_cli'):
            texto = _cli(t, modelo, sistema + '\n\nMensagem:\n' + usuario, to)
    except Exception as e:
        log(f'cérebro {t}: falhou: {type(e).__name__}')
        return None
    if not isinstance(texto, str) or not texto.strip():
        return None
    return texto


def _cli(t, modelo, prompt, to):
    exe = binario(t)
    if not exe:
        return None
    if t == 'claude_cli':
        args = [exe, '-p', '--model', str(modelo or 'sonnet')]
    else:
        args = [exe, 'exec'] + (['-m', str(modelo)] if modelo else []) + ['-s', 'read-only',
                                                                         '--skip-git-repo-check', '-']
    with tempfile.TemporaryDirectory() as pasta:  # nada do projeto ao alcance do CLI
        try:
            r = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=to, cwd=pasta)
        except (OSError, subprocess.SubprocessError) as e:
            log(f'cérebro {t}: {type(e).__name__}')
            return None
    if r.returncode != 0:
        log(f'cérebro {t}: saída {r.returncode}')
        return None
    return (r.stdout or '').strip()
