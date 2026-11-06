"""Cérebro do agente (seção 14). 'regras' cobre tudo; os tipos LLM resumem, tiram dúvida, sugerem respostas
à equipe e propõem itens para a base.

Tipos: regras | anthropic | openrouter | openai | ollama | claude_cli | codex_cli.
Qualquer erro, timeout, recusa ou resposta vazia cai na regra. A chave vem só de CEREBRO_API_KEY (nunca do
JSON). anthropic/openrouter têm URL fixa (host sempre permitido); openai/ollama usam cerebro.url, e a chave só
vai a host de CEREBRO_HOSTS_PERMITIDOS. Nenhuma chamada (rede ou subprocesso) acontece dentro do lock do banco.
"""
import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urlsplit

from . import rede
from .core import log

URGENCIA = {1: 'hoje', 2: 'este mês', 3: 'pesquisando'}
ASSUNTO = {'pediu_humano': 'falar com alguém', 'venda': 'comprar', 'precisa': 'resolver um problema'}
TIPOS = ('regras', 'anthropic', 'openrouter', 'openai', 'ollama', 'claude_cli', 'codex_cli')
ESFORCOS = ('low', 'medium', 'high', 'xhigh', 'max')
ANTHROPIC_URL = 'https://api.anthropic.com/v1/messages'
OPENROUTER_URL = 'https://openrouter.ai/api/v1/chat/completions'
MODELO_OK = re.compile(r'^[A-Za-z0-9][A-Za-z0-9.:/@_-]{0,99}$')
TIMEOUTS = {'ollama': 15, 'openai': 15, 'anthropic': 20, 'openrouter': 20, 'claude_cli': 60, 'codex_cli': 60}
MAX_TOKENS = 1024


def cfg(c):
    v = c.cfg.get('cerebro')
    return v if isinstance(v, dict) else {}


def tipo(c):
    t = cfg(c).get('tipo') or 'regras'
    return t if t in TIPOS else 'regras'


def timeout(t):
    try:
        teste = float(os.environ.get('CEREBRO_TIMEOUT_S') or 0)
    except ValueError:
        teste = 0
    return min(TIMEOUTS.get(t, 15), teste) if teste > 0 else TIMEOUTS.get(t, 15)


_BINS = {}


def binario(t):
    """Caminho do CLI (resolvido uma vez: a saúde é servida fora do lock e precisa ser rápida)."""
    nome = os.environ.get('CEREBRO_CLI_BIN') or ('claude' if t == 'claude_cli' else 'codex')
    if nome not in _BINS:
        _BINS[nome] = shutil.which(nome)
    return _BINS[nome]


def disponivel(c):
    """(ok, motivo). ok=False → tudo por regras."""
    t = tipo(c)
    k = cfg(c)
    if t == 'regras':
        return True, None
    modelo = str(k.get('modelo') or '')
    if t in ('anthropic', 'openrouter'):
        if not os.environ.get('CEREBRO_API_KEY'):
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


def ligado(c):
    return tipo(c) != 'regras' and disponivel(c)[0]


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


def responder_duvida(c, texto):
    """Usado quando caiu em 'não entendi'. Devolve texto ou None (→ regra)."""
    if not ligado(c):
        return None
    from . import base
    instr = base.instrucoes(c).replace('Se a base não responder, diga que vai chamar alguém da equipe.',
                                       'Se a base não responder, responda exatamente: SEM_RESPOSTA '
                                       '(o sistema chama alguém da equipe).')
    r = perguntar(c, instr, texto, base.texto_base(c))
    if not r or 'SEM_RESPOSTA' in r:
        return None
    return r.strip()



def limpar_md(texto):
    """O modelo às vezes responde em markdown (**negrito**, # título, - lista); o lead e o Telegram veem texto puro."""
    if not texto:
        return texto
    t = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
    t = re.sub(r'__(.+?)__', r'\1', t)
    t = re.sub(r'(?m)^\s{0,3}#{1,6}\s*', '', t)
    t = re.sub(r'(?m)^\s*[-*]\s+', '• ', t)
    return t.replace('**', '').strip()

def perguntar(c, instrucoes, usuario, base_txt=None):
    """A chamada ao modelo roda FORA do lock: c.pronto desfaz a transação, chama e repete com o resultado.
    Fora de uma transação (trabalhador em segundo plano), chama direto."""
    ok, _motivo = disponivel(c)
    t = tipo(c)
    if t == 'regras' or not ok:
        return None
    k = dict(cfg(c))
    k['_referer'] = c.url_publica() or 'https://github.com/inematds/atende-leads'
    chave = ('cerebro', t, str(k.get('url') or ''), str(k.get('modelo') or ''), str(k.get('esforco') or ''),
             instrucoes, base_txt or '', usuario)
    return limpar_md(c.pronto(chave, lambda: _perguntar(t, k, instrucoes, base_txt, usuario)))


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
    return {'model': k.get('modelo'), 'max_tokens': MAX_TOKENS, 'system': system,
            'messages': [{'role': 'user', 'content': usuario}],
            'output_config': {'effort': esforco}, 'fallbacks': 'default'}


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
    chave = os.environ.get('CEREBRO_API_KEY') or ''
    to = timeout(t)
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
            ok, r = rede.postar(url, {'model': modelo, 'messages': msgs, 'max_tokens': MAX_TOKENS}, headers,
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
