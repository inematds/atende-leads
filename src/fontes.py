"""Gerar base a partir de link ou arquivo (seção 13c, 1.7.8).

O gestor manda um link (lê a página e as do mesmo domínio ligadas a ela) ou um arquivo (TXT, MD, CSV, HTML, DOCX,
PDF). Um trabalhador em segundo plano lê o conteúdo e o passa ao cérebro da curadoria, que devolve propostas
estruturadas (info, produto, preço, horário, FAQ) com a fonte e a evidência; sem cérebro LLM, as regras tiram só o
óbvio (telefone, e-mail, endereço com CEP, preços, horários). As propostas entram no Aprendizado (`origem: fonte`).

Rede: só http/https, sem login; o host é resolvido e IP privado/loopback/link-local/reservado é recusado, também a
cada redirecionamento (até 3), e a conexão vai ao IP já conferido (sem segunda resolução). 10 s e 2 MB por
página, robots.txt (Disallow de *). `ATENDE_FONTE_PERMITIR_LOCAL` (só teste) libera `host:porta` listados ou tudo
com `1` — nunca em produção. O conteúdo fica só em memória (PDF para o pdftotext: arquivo temporário apagado).
"""
import base64
import binascii
import http.client
import io
import ipaddress
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import zipfile
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree as ET

from .core import Erro, iso, log, normalizar
from . import base, cerebro, consolidada, sugestao

MAX_PAGINAS_PADRAO = 8
MAX_PAGINAS = 20
MAX_PAGINA = 2 * 1024 * 1024
MAX_ARQUIVO = 10 * 1024 * 1024
TIMEOUT = 10
MAX_REDIR = 3
BLOCO = 15000
MAX_BLOCOS = 12
MAX_PROPOSTAS = 40
PROFUNDIDADE = 2
EXTENSOES = ('txt', 'md', 'csv', 'html', 'htm', 'docx', 'pdf')
UA_PADRAO = 'https://github.com/inematds/atende-leads'


class Recusado(Exception):
    """Fonte que não dá para ler (mensagem vai ao gestor)."""


# ---------------------------------------------------------------- SSRF
def _permitidos_locais():
    v = os.environ.get('ATENDE_FONTE_PERMITIR_LOCAL') or ''
    return {x.strip().lower() for x in v.split(',') if x.strip()}


def _local_liberado(host, porta):
    p = _permitidos_locais()
    return '1' in p or f'{host}:{porta}'.lower() in p


def ip_proibido(ip):
    """True para tudo que não é endereço público da internet (privado, loopback, link-local, reservado...)."""
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
            or ip.is_unspecified or not ip.is_global)


def resolver(host, porta):
    """IP (texto) seguro para conectar, ou Recusado. Confere TODOS os endereços que o nome resolve."""
    try:
        infos = socket.getaddrinfo(host, porta, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError, OSError):
        raise Recusado(f'não encontrei o endereço {host}')
    ips = []
    for _f, _t, _p, _c, sa in infos:
        ip = ipaddress.ip_address(sa[0].split('%')[0])
        if ip_proibido(ip) and not _local_liberado(host, porta):
            raise Recusado(f'endereço interno ({ip}) não é permitido')
        ips.append(str(ip))
    if not ips:
        raise Recusado(f'não encontrei o endereço {host}')
    return ips[0]


def checar_url(url):
    """Validação imediata (sem DNS): esquema, host, sem login; IP literal interno já recusa aqui."""
    if not isinstance(url, str) or not url.strip() or len(url) > 2000:
        raise Recusado('informe o link (http:// ou https://)')
    u = urlsplit(url.strip())
    if u.scheme not in ('http', 'https') or not u.hostname:
        raise Recusado('só links http:// ou https://')
    if u.username or u.password:
        raise Recusado('link com usuário/senha não é aceito (só páginas públicas, sem login)')
    try:
        porta = u.port or (443 if u.scheme == 'https' else 80)
    except ValueError:
        raise Recusado('porta inválida no link')
    try:
        ip = ipaddress.ip_address(u.hostname.strip('[]'))
    except ValueError:
        ip = None
    if ip is not None and ip_proibido(ip) and not _local_liberado(u.hostname, porta):
        raise Recusado(f'endereço interno ({ip}) não é permitido')
    return u, porta


class _HTTP(http.client.HTTPConnection):
    def __init__(self, host, porta, ip, timeout):
        super().__init__(host, porta, timeout=timeout)
        self._ip = ip

    def connect(self):  # conecta no IP já conferido (sem resolver de novo: nada de DNS rebinding)
        self.sock = socket.create_connection((self._ip, self.port), self.timeout)


class _HTTPS(http.client.HTTPSConnection):
    def __init__(self, host, porta, ip, timeout):
        super().__init__(host, porta, timeout=timeout, context=ssl.create_default_context())
        self._ip = ip

    def connect(self):
        sock = socket.create_connection((self._ip, self.port), self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def baixar(url, ua, limite=MAX_PAGINA, timeout=TIMEOUT):
    """(url final, content-type, bytes, charset). Segue até 3 redirecionamentos, conferindo cada destino."""
    for _ in range(MAX_REDIR + 1):
        u, porta = checar_url(url)
        ip = resolver(u.hostname, porta)
        cls = _HTTPS if u.scheme == 'https' else _HTTP
        conn = cls(u.hostname, porta, ip, timeout)
        caminho = (u.path or '/') + (f'?{u.query}' if u.query else '')
        fim = time.monotonic() + timeout
        try:
            conn.request('GET', caminho, headers={'User-Agent': ua, 'Accept-Encoding': 'identity',
                                                  'Accept': 'text/html,text/plain;q=0.9,*/*;q=0.1'})
            r = conn.getresponse()
            if r.status in (301, 302, 303, 307, 308):
                loc = r.getheader('Location')
                if not loc:
                    raise Recusado('redirecionamento sem destino')
                url = urljoin(url, loc.strip())
                continue
            if r.status >= 400:
                raise Recusado(f'a página respondeu {r.status}')
            ct = r.getheader('Content-Type') or ''
            tamanho = r.getheader('Content-Length') or ''
            if tamanho.isdigit() and int(tamanho) > limite:
                raise Recusado('página maior que 2 MB')
            partes, total = [], 0
            while True:
                if time.monotonic() > fim:
                    raise Recusado(f'a página demorou mais de {timeout} s')
                bloco = r.read(65536)
                if not bloco:
                    break
                total += len(bloco)
                if total > limite:
                    raise Recusado('página maior que 2 MB')
                partes.append(bloco)
            m = re.search(r'charset=([\w-]+)', ct, re.I)
            return url, ct.split(';')[0].strip().lower(), b''.join(partes), (m.group(1) if m else None)
        except Recusado:
            raise
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise Recusado(f'não consegui abrir a página ({type(e).__name__})')
        finally:
            conn.close()
    raise Recusado('redirecionamentos demais (máximo 3)')


def decodificar(dados, charset=None):
    for cod in [charset, 'utf-8-sig', 'cp1252']:
        if not cod:
            continue
        try:
            return dados.decode(cod)
        except (LookupError, UnicodeDecodeError):
            continue
    return dados.decode('utf-8', 'replace')


# ---------------------------------------------------------------- HTML → texto
class _Extrator(HTMLParser):
    PULAR = {'script', 'style', 'nav', 'footer', 'noscript', 'svg', 'template', 'iframe', 'head', 'form', 'button',
             'select', 'option'}
    BLOCOS = {'p', 'div', 'section', 'article', 'main', 'header', 'aside', 'ul', 'ol', 'dl', 'dt', 'dd', 'table',
              'thead', 'tbody', 'blockquote', 'address', 'pre', 'figure', 'figcaption', 'br', 'hr', 'body'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.linhas, self.atual, self.links = [], [], []
        self.pular = 0
        self.titulo, self.no_titulo = '', False
        self.celulas = None

    def _quebra(self):
        t = ' '.join(''.join(self.atual).split())
        if t:
            self.linhas.append(t)
        self.atual = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'a' and a.get('href'):
            self.links.append(a['href'])
        if tag == 'title':
            self.no_titulo = True
        if tag == 'meta' and (a.get('name') or '').lower() == 'description' and a.get('content'):
            self.linhas.append(' '.join(a['content'].split()))
        if tag in self.PULAR:
            self.pular += 1
            return
        if self.pular:
            return
        if tag == 'tr':
            self._quebra()
            self.celulas = []
        elif tag in ('td', 'th'):
            if self.celulas is not None:
                self.celulas.append(' '.join(''.join(self.atual).split()))
                self.atual = []
        elif re.fullmatch(r'h[1-6]', tag):
            self._quebra()
            self.atual.append('#' * int(tag[1]) + ' ')
        elif tag == 'li':
            self._quebra()
            self.atual.append('- ')
        elif tag in self.BLOCOS:
            self._quebra()

    def handle_endtag(self, tag):
        if tag == 'title':
            self.no_titulo = False
        if tag in self.PULAR:
            self.pular = max(0, self.pular - 1)
            return
        if self.pular:
            return
        if tag == 'tr' and self.celulas is not None:
            self.celulas.append(' '.join(''.join(self.atual).split()))
            self.atual = []
            linha = ' | '.join(x for x in self.celulas if x)
            if linha:
                self.linhas.append(linha)
            self.celulas = None
        elif re.fullmatch(r'h[1-6]', tag) or tag in ('li', 'td', 'th') or tag in self.BLOCOS:
            if tag in ('td', 'th') and self.celulas is not None:
                self.atual.append(' ')
                return
            self._quebra()

    def handle_data(self, data):
        if self.no_titulo:
            self.titulo += data
            return
        if not self.pular:
            self.atual.append(data)


def extrair_html(texto):
    """(texto legível, hrefs). Remove script/style/nav/footer; títulos com #, listas com -, tabelas com |."""
    p = _Extrator()
    try:
        p.feed(texto)
        p.close()
    except Exception:  # HTML quebrado: fica com o que deu para ler
        pass
    p._quebra()
    linhas = ([('# ' + ' '.join(p.titulo.split()))] if p.titulo.strip() else []) + p.linhas
    return limpar_texto('\n'.join(x for x in linhas if x.strip('#- ').strip())), p.links


def limpar_texto(texto):
    out = []
    for linha in str(texto or '').splitlines():
        t = ' '.join(linha.split())
        if t and (not out or out[-1] != t):
            out.append(t)
    return '\n'.join(out)


# ---------------------------------------------------------------- arquivos
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'


def _par_docx(p):
    partes = []
    for el in p.iter():
        if el.tag == W + 't' and el.text:
            partes.append(el.text)
        elif el.tag in (W + 'tab',):
            partes.append(' ')
        elif el.tag in (W + 'br', W + 'cr'):
            partes.append('\n')
    return ''.join(partes)


def ler_docx(dados):
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
        info = z.getinfo('word/document.xml')
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise Recusado('DOCX inválido (não achei word/document.xml)')
    if info.file_size > 50 * 1024 * 1024:
        raise Recusado('DOCX grande demais por dentro')
    xml = z.read(info)
    if b'<!DOCTYPE' in xml[:4096].upper() or b'<!ENTITY' in xml:
        raise Recusado('DOCX inválido')
    try:
        raiz = ET.fromstring(xml)
    except ET.ParseError:
        raise Recusado('DOCX inválido (XML quebrado)')
    corpo = raiz.find(W + 'body')
    linhas = []
    for el in (list(corpo) if corpo is not None else []):
        if el.tag == W + 'p':
            linhas.append(_par_docx(el))
        elif el.tag == W + 'tbl':
            for tr in el.iter(W + 'tr'):
                cel = [' '.join(_par_docx(p) for p in tc.iter(W + 'p')).strip() for tc in tr.findall(W + 'tc')]
                linhas.append(' | '.join(x for x in cel if x))
    return limpar_texto('\n'.join(linhas))


def pdftotext_bin():
    return shutil.which(os.environ.get('ATENDE_PDFTOTEXT_BIN') or 'pdftotext')


def ler_pdf_local(dados):
    exe = pdftotext_bin()
    if not exe:
        raise Recusado('PDF precisa do cérebro Anthropic ou do pdftotext')
    with tempfile.TemporaryDirectory() as pasta:  # apagado ao sair
        arq = os.path.join(pasta, 'f.pdf')
        with open(arq, 'wb') as f:
            f.write(dados)
        try:
            r = subprocess.run([exe, '-layout', '-enc', 'UTF-8', arq, '-'], capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            raise Recusado('pdftotext falhou')
    if r.returncode != 0:
        raise Recusado('pdftotext não conseguiu ler o PDF')
    return limpar_texto(decodificar(r.stdout, 'utf-8'))


def extensao(nome):
    m = re.search(r'\.([A-Za-z0-9]{1,5})$', str(nome or ''))
    return m.group(1).lower() if m else ''


def pdf_por_anthropic(c):
    return cerebro.tipo(c, 'curadoria') == 'anthropic' and cerebro.ligado(c, 'curadoria')


def texto_arquivo(nome, dados):
    ext = extensao(nome)
    if ext in ('txt', 'md', 'csv'):
        return limpar_texto(decodificar(dados))
    if ext in ('html', 'htm'):
        return extrair_html(decodificar(dados))[0]
    if ext == 'docx':
        return ler_docx(dados)
    raise Recusado('tipo de arquivo não aceito')


# ---------------------------------------------------------------- leitura do link (BFS no mesmo domínio)
def _dominio(host):
    h = (host or '').lower().rstrip('.')
    return h[4:] if h.startswith('www.') else h


def _sem_fragmento(url):
    u = urlsplit(url)
    return urlunsplit((u.scheme, u.netloc.lower(), u.path or '/', u.query, ''))


def _robots(url, ua, cache):
    u = urlsplit(url)
    chave = f'{u.scheme}://{u.netloc.lower()}'
    if chave not in cache:
        rp = RobotFileParser()
        try:
            _f, _t, corpo, cs = baixar(chave + '/robots.txt', ua, limite=512 * 1024)
            rp.parse(decodificar(corpo, cs).splitlines())
        except Recusado:
            rp.parse([])  # sem robots.txt (ou ilegível): tudo liberado
        cache[chave] = rp
    return cache[chave]


def ler_link(url, max_paginas, ua):
    """([(url, texto)], avisos). A primeira página que falhar derruba a leitura (Recusado); as outras viram aviso."""
    fila, vistos, paginas, avisos, robots = [(url.strip(), 0)], set(), [], [], {}
    dominio = None
    while fila and len(paginas) < max_paginas:
        alvo, prof = fila.pop(0)
        chave = _sem_fragmento(alvo)
        if chave in vistos:
            continue
        vistos.add(chave)
        primeira = dominio is None
        if not primeira and _dominio(urlsplit(alvo).hostname) != dominio:
            continue
        try:
            if not _robots(alvo, ua, robots).can_fetch('atende-leads', alvo):
                raise Recusado('o robots.txt do site não permite ler esta página')
            final, tipo, corpo, cs = baixar(alvo, ua)
        except Recusado as e:
            if primeira:
                raise
            avisos.append(f'{alvo}: {e}')
            continue
        host_final = _dominio(urlsplit(final).hostname)
        if primeira:
            dominio = host_final
        elif host_final != dominio:
            avisos.append(f'{alvo}: redirecionou para outro domínio (não li)')
            continue
        vistos.add(_sem_fragmento(final))
        if tipo not in ('text/html', 'application/xhtml+xml', 'text/plain', ''):
            if primeira:
                raise Recusado(f'o link não é uma página (tipo {tipo})')
            avisos.append(f'{alvo}: não é página ({tipo})')
            continue
        bruto = decodificar(corpo, cs)
        if tipo == 'text/plain':
            texto, links = limpar_texto(bruto), []
        else:
            texto, links = extrair_html(bruto)
        if texto:
            paginas.append((final, texto[:200000]))
        if prof < PROFUNDIDADE:
            for h in links:
                prox = urljoin(final, h.strip())
                pu = urlsplit(prox)
                if (pu.scheme in ('http', 'https') and _dominio(pu.hostname) == dominio
                        and _sem_fragmento(prox) not in vistos
                        and not re.search(r'\.(jpe?g|png|gif|webp|svg|pdf|zip|mp4|mp3|css|js|ico|woff2?)$', pu.path, re.I)):
                    fila.append((prox, prof + 1))
    if not paginas:
        raise Recusado('não achei texto nas páginas')
    return paginas, avisos


# ---------------------------------------------------------------- propostas
TIPOS = ('info', 'produto', 'preco', 'horario', 'faq', 'correcao')
ITEM_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {
        'tipo': {'type': 'string', 'enum': list(TIPOS)}, 'perguntas': {'type': 'array', 'items': {'type': 'string'}},
        'resposta': {'type': 'string'}, 'campo': {'type': 'string'}, 'nome': {'type': 'string'},
        'palavras': {'type': 'array', 'items': {'type': 'string'}}, 'horarios': {'type': 'string'},
        'faq_id': {'type': 'string'}, 'produto_id': {'type': 'string'}, 'preco_novo': {'type': 'string'},
        'promocao': {'type': 'string'}, 'validade': {'type': 'string'}, 'justificativa': {'type': 'string'},
        'fonte': {'type': 'string'}, 'evidencia': {'type': 'string'}, 'contradiz': {'type': 'boolean'}},
}
ITEM_SCHEMA['required'] = list(ITEM_SCHEMA['properties'])
SCHEMA = {'type': 'object', 'additionalProperties': False, 'required': ['propostas'],
          'properties': {'propostas': {'type': 'array', 'items': ITEM_SCHEMA}}}

INSTR = (
    'Você ajuda o gestor de {nome} a montar a base de conhecimento do atendimento a partir de um conteúdo do próprio '
    'negócio (site ou documento). Proponha itens para a base usando SÓ fatos escritos no conteúdo — nunca invente.\n'
    'Compare com a base atual (abaixo): não proponha o que a base já diz; quando o conteúdo CONTRADIZ a base (preço, '
    'horário, endereço, resposta do FAQ), proponha a correção com "contradiz": true e diga em "justificativa" o que '
    'a base diz hoje.\n'
    'REGRA DURA: "resposta" é o texto FINAL que vai para a base e que o atendente dirá ao cliente — factual, sem '
    'bastidores (nada de "o site diz", "segundo o documento", "a base diz", "confirmar com a equipe"). O porquê vai '
    'SÓ em "justificativa".\n'
    'Tipos: "info" (campo = endereco|pagamento|entrega|garantia|site|observacoes; resposta = o texto do campo); '
    '"produto" (produto que NÃO está no cadastro: nome, palavras que o cliente usaria, preco_novo "R$ ..." se houver); '
    '"preco" (produto já cadastrado: produto_id da lista + preco_novo; promocao/validade AAAA-MM-DD se o conteúdo '
    'disser); "horario" (horarios em texto: "seg 08:00-18:00; sab 09:00-13:00; dom fechado", só os dias citados); '
    '"faq" (perguntas que o cliente faria + resposta factual); "correcao" (faq_id existente + resposta nova).\n'
    'Cada item: "fonte" = a URL da página (o conteúdo vem marcado com "=== Fonte: <url ou arquivo> ===") ou o nome do '
    'arquivo; "evidencia" = trecho curto COPIADO do conteúdo (até 200 caracteres) que prova o item. Campos que não '
    'se aplicam: "" ou []. No máximo 15 itens. Responda SOMENTE com JSON {{"propostas": [...]}}.')


def _usuario(c, blocos_txt, n, total, fontes_txt):
    prods = '\n'.join(f"- {p.get('id')}: {p.get('nome')} — {base.preco_vigente(c, p) or 'sem preço'}"
                      for p in c.cfg.get('produtos') or [])
    ids = '\n'.join(f"- {f.get('id')}: {' / '.join(f.get('perguntas') or [])}" for f in c.cfg.get('faq') or [])
    return (f'Fontes: {fontes_txt}\nProdutos cadastrados (id: nome — preço):\n{prods or "(nenhum)"}\n'
            f'IDs do FAQ atual:\n{ids or "(vazio)"}\n\n'
            + (f'Conteúdo (bloco {n} de {total}):\n{blocos_txt}' if blocos_txt is not None
               else 'Conteúdo: o documento PDF anexo.'))


def dividir(paginas, tam=BLOCO):
    """Blocos de ~15 mil caracteres, cada um começando com a marca da fonte; quebra em linhas."""
    blocos, atual = [], ''
    for fonte, texto in paginas:
        marca = f'=== Fonte: {fonte} ===\n'
        for linha in (marca + texto).splitlines():
            linha = linha[:tam]
            if len(atual) + len(linha) + 1 > tam and atual:
                blocos.append(atual)
                atual = marca if not linha.startswith('=== Fonte:') else ''
            atual += linha + '\n'
    if atual.strip():
        blocos.append(atual)
    return blocos


DIA_RX = r'(seg|segunda|ter|terca|qua|quarta|qui|quinta|sex|sexta|sab|sabado|dom|domingo)'
JANELA_RX = re.compile(r'(\d{1,2})(?:[:h](\d{2}))?h?\s*(?:-|–|a|as|ate)\s*(\d{1,2})(?:[:h](\d{2}))?h?')


def horarios_de_texto(v):
    """'seg 08:00-18:00; sab 09:00-13:00; dom fechado' (ou dict) → {dia: [[ini, fim]]}; None se não der."""
    if isinstance(v, dict):
        return sugestao.horarios_validos(v)
    if not isinstance(v, str) or not v.strip():
        return None
    out = {}
    for parte in re.split(r'[;\n]', consolidada._plano(v)):
        parte = parte.strip()
        m = re.match(DIA_RX + r'(?:-feira)?s?\b(?:\s*(?:a|-|–|ate)\s*' + DIA_RX + r'(?:-feira)?s?\b)?(.*)', parte)
        if not m:
            continue
        a = consolidada.DIA_NOMES[m.group(1)]
        b = consolidada.DIA_NOMES[m.group(2)] if m.group(2) else a
        ia, ib = consolidada.DIAS.index(a), consolidada.DIAS.index(b)
        dias = consolidada.DIAS[ia:ib + 1] if ia <= ib else consolidada.DIAS[ia:] + consolidada.DIAS[:ib + 1]
        resto = m.group(3)
        jan = []
        if 'fechad' not in resto:
            for j in JANELA_RX.finditer(resto):
                ini, fim = consolidada._hhmm(j.group(1), j.group(2)), consolidada._hhmm(j.group(3), j.group(4))
                if ini and fim:
                    jan.append([ini, '23:59' if fim == '24:00' else fim])
            if not jan:
                continue
        for d in dias:
            out[d] = jan
    return sugestao.horarios_validos(out) if out else None


def _mesmo_horario(c, h):
    atual = c.cfg.get('horarios') or {}
    return all([list(x) for x in (atual.get(d) or [])] == j for d, j in h.items())


def _ja_na_base(c, tipo, d):
    """O que a base já diz igual não vira proposta."""
    if tipo == 'preco':
        prod = c.produto(d['produto_id'])
        precos = {normalizar(prod.get('preco') or '')}
        if base.promocao_ativa(c, prod):
            precos.add(normalizar(prod.get('preco_promocao') or ''))
        return normalizar(d['preco_novo']) in precos
    if tipo == 'info':
        atual = normalizar(base.campo(c, d['campo']))
        return bool(atual) and normalizar(d['resposta']) in atual
    if tipo == 'horario':
        return _mesmo_horario(c, d['horarios'])
    if tipo == 'correcao':
        f = next((f for f in c.cfg.get('faq') or [] if f.get('id') == d.get('faq_id')), {})
        return normalizar(f.get('resposta') or '') == normalizar(d['resposta'])
    if tipo == 'faq':
        perg = {normalizar(x) for f in c.cfg.get('faq') or [] for x in f.get('perguntas') or []}
        return any(normalizar(x) in perg for x in d['perguntas'])
    return False


def validar_itens(c, itens, fontes_validas, fonte_padrao):
    """Itens crus (do cérebro ou das regras) → [(tipo, dados)] prontos para `sugestao._inserir`."""
    out, vistos = [], set()
    for p in itens if isinstance(itens, list) else []:
        if not isinstance(p, dict):
            continue
        p = dict(p)
        if p.get('tipo') == 'horario':
            p['horarios'] = horarios_de_texto(p.get('horarios'))
        for k in ('faq_id', 'produto_id'):
            if not p.get(k):
                p.pop(k, None)
        lido = sugestao._limpar(c, p)
        if not lido:
            continue
        tipo, d = lido
        if _ja_na_base(c, tipo, d):
            continue
        chave = (tipo, d.get('produto_id') or d.get('campo') or '', normalizar(d.get('nome') or d['resposta']))
        if chave in vistos:
            continue
        vistos.add(chave)
        fonte = sugestao._texto(p.get('fonte'), 2000)
        d['fonte'] = fonte if fonte in fontes_validas else fonte_padrao
        ev = sugestao._texto(p.get('evidencia'), 300)
        d['evidencia'] = ev
        d['contradiz'] = bool(p.get('contradiz')) or tipo in ('preco', 'correcao') or (
            tipo == 'horario' and any((c.cfg.get('horarios') or {}).get(x) for x in d['horarios']))
        if not d.get('justificativa'):
            d['justificativa'] = 'Lido de ' + d['fonte']
        out.append((tipo, d))
        if len(out) >= MAX_PROPOSTAS:
            break
    return out


# ---------------------------------------------------------------- sem cérebro LLM: só o óbvio
FONE = re.compile(r'(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?9?\d{4}[-.\s]?\d{4}(?!\d)')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
CEP = re.compile(r'(?<!\d)\d{5}-?\d{3}(?!\d)')
PRECO = re.compile(r'R\$\s?\d[\d.]*(?:,\d{2})?')
PRE_NOME = re.compile(r'\s*(?:[-–:|•*#]+|\bpor\b|\bapenas\b|\ba partir de\b|\bde\b|\bpreco\b|\bpreço\b|\bvalor\b)\s*$', re.I)


def _nome_antes(linha, ini):
    nome = linha[:ini]
    for _ in range(4):
        novo = PRE_NOME.sub('', nome)
        if novo == nome:
            break
        nome = novo
    nome = nome.strip(' -–:|•*#')
    return nome if 2 <= len(nome) <= 60 and re.search(r'[A-Za-zÀ-ú]', nome) else ''


def por_regras(c, paginas, link=None):
    itens = []
    fones, emails = [], []
    horarios, ev_hor, fonte_hor = {}, [], None
    endereco = None
    for fonte, texto in paginas:
        linhas = texto.splitlines()
        for i, linha in enumerate(linhas):
            limpa = linha.lstrip('#- ').strip()
            for m in FONE.finditer(limpa):
                dig = re.sub(r'\D', '', m.group(0))
                if 10 <= len(dig) <= 13 and dig not in [x[0] for x in fones] and not CEP.fullmatch(m.group(0).strip()):
                    fones.append((dig, m.group(0).strip(), fonte, limpa))
            for m in EMAIL.finditer(limpa):
                if m.group(0).lower() not in [x[0] for x in emails]:
                    emails.append((m.group(0).lower(), fonte, limpa))
            if endereco is None and CEP.search(limpa):
                txt = re.sub(r'^(endere[cç]o|localiza[cç][aã]o|onde estamos)\s*:?\s*', '', limpa, flags=re.I)
                endereco = (txt[:300], fonte, limpa)
            for m in PRECO.finditer(limpa):
                nome = _nome_antes(limpa, m.start())
                if not nome and i and len(linhas[i - 1]) <= 60:
                    nome = linhas[i - 1].lstrip('#- ').strip()
                preco = m.group(0).replace('R$', 'R$ ').replace('  ', ' ')
                prod = next((p for p in c.cfg.get('produtos') or []
                             if p.get('nome') and normalizar(p['nome']) in normalizar(nome or limpa)), None)
                if prod:
                    itens.append({'tipo': 'preco', 'produto_id': prod['id'], 'preco_novo': preco, 'fonte': fonte,
                                  'evidencia': limpa[:200], 'justificativa': f"O conteúdo cita {preco} para {prod['nome']}."})
                elif nome:
                    itens.append({'tipo': 'produto', 'nome': nome, 'preco_novo': preco, 'fonte': fonte,
                                  'palavras': [normalizar(nome)], 'evidencia': limpa[:200],
                                  'justificativa': 'Produto com preço citado no conteúdo.'})
            plano = consolidada._plano(limpa)
            if re.search(DIA_RX, plano) and JANELA_RX.search(plano) and re.search(r'\d\s*(h|:)', plano):
                dias, jan, _completo = consolidada.horario_do_texto(limpa)
                if dias and jan:
                    for d in dias:
                        horarios[d] = [list(jan)]
                    ev_hor.append(limpa[:120])
                    fonte_hor = fonte_hor or fonte
    for dig, txt, fonte, ev in fones[:3]:
        itens.append({'tipo': 'info', 'campo': 'observacoes', 'resposta': f'Telefone: {txt}', 'fonte': fonte,
                      'evidencia': ev[:200], 'justificativa': 'Telefone citado no conteúdo.'})
    for em, fonte, ev in emails[:3]:
        itens.append({'tipo': 'info', 'campo': 'observacoes', 'resposta': f'E-mail: {em}', 'fonte': fonte,
                      'evidencia': ev[:200], 'justificativa': 'E-mail citado no conteúdo.'})
    if endereco:
        itens.append({'tipo': 'info', 'campo': 'endereco', 'resposta': endereco[0], 'fonte': endereco[1],
                      'evidencia': endereco[2][:200], 'justificativa': 'Endereço com CEP citado no conteúdo.'})
    if horarios:
        horarios = {d: horarios[d] for d in consolidada.DIAS if d in horarios}
        itens.append({'tipo': 'horario', 'horarios': horarios, 'fonte': fonte_hor, 'evidencia': ' · '.join(ev_hor)[:300],
                      'justificativa': 'Horários citados no conteúdo.'})
    if link and not base.campo(c, 'site'):
        u = urlsplit(link)
        itens.append({'tipo': 'info', 'campo': 'site', 'resposta': f'{u.scheme}://{u.netloc}', 'fonte': link,
                      'evidencia': link[:200], 'justificativa': 'Endereço do site lido.'})
    return itens


# ---------------------------------------------------------------- API (rotas do gestor)
def _job_json(r):
    d = dict(r)
    try:
        d['avisos'] = json.loads(d.get('avisos') or '[]')
    except ValueError:
        d['avisos'] = []
    return d


def listar(c):
    return {'fontes': [_job_json(r) for r in c.db.execute('SELECT * FROM fontes ORDER BY id DESC LIMIT 30')],
            'pdf': {'anthropic': pdf_por_anthropic(c), 'pdftotext': bool(pdftotext_bin())}}


def _novo(c, tipo, fonte, mem):
    fid = c.db.execute('INSERT INTO fontes(em,tipo,fonte,status) VALUES (?,?,?,?)',
                       (iso(c.agora()), tipo, fonte, 'lendo')).lastrowid
    c.fonte_mem[fid] = mem
    c.enfileirar('fonte', fid)
    return {'ok': True, 'fonte': _job_json(c.db.execute('SELECT * FROM fontes WHERE id=?', (fid,)).fetchone())}


def _ocupado(c):
    n = c.db.execute("SELECT COUNT(*) FROM fontes WHERE status IN ('lendo','analisando')").fetchone()[0]
    if n >= 3:
        raise Erro(429, 'Já há 3 leituras em andamento; espere uma terminar.')


def pedir_link(c, b):
    url = b.get('url')
    mp = b.get('max_paginas', MAX_PAGINAS_PADRAO)
    if isinstance(mp, bool) or not isinstance(mp, int) or not 1 <= mp <= MAX_PAGINAS:
        raise Erro(422, f'max_paginas: inteiro de 1 a {MAX_PAGINAS}')
    try:
        checar_url(url)
    except Recusado as e:
        raise Erro(422, str(e))
    _ocupado(c)
    return _novo(c, 'link', url.strip(), {'url': url.strip(), 'max_paginas': mp})


def pedir_arquivo(c, b):
    nome = b.get('nome')
    if not isinstance(nome, str) or not nome.strip() or len(nome) > 200:
        raise Erro(422, 'nome do arquivo obrigatório')
    nome = os.path.basename(nome.strip().replace('\\', '/'))
    ext = extensao(nome)
    if ext not in EXTENSOES:
        raise Erro(422, 'Aceito: TXT, MD, CSV, HTML, DOCX e PDF')
    bruto = b.get('conteudo_base64')
    if not isinstance(bruto, str) or not bruto:
        raise Erro(422, 'conteudo_base64 obrigatório')
    if len(bruto) > (MAX_ARQUIVO * 4) // 3 + 8:
        raise Erro(413, 'Arquivo maior que 10 MB')
    try:
        dados = base64.b64decode(bruto, validate=True)
    except (binascii.Error, ValueError):
        raise Erro(422, 'conteudo_base64 inválido')
    if len(dados) > MAX_ARQUIVO:
        raise Erro(413, 'Arquivo maior que 10 MB')
    if not dados:
        raise Erro(422, 'Arquivo vazio')
    if ext == 'pdf':
        if not dados.startswith(b'%PDF'):
            raise Erro(422, 'O arquivo não parece um PDF')
        if not pdf_por_anthropic(c) and not pdftotext_bin():
            raise Erro(422, 'PDF precisa do cérebro Anthropic ou do pdftotext')
    _ocupado(c)
    return _novo(c, 'arquivo', nome, {'nome': nome, 'dados': dados})


# ---------------------------------------------------------------- trabalhador
class Trabalhador:
    """Lê as fontes e gera as propostas fora do lock, uma por vez (não atrasa as sugestões da equipe)."""

    def __init__(self, app):
        self.app = app
        self.parar = threading.Event()
        self.thread = threading.Thread(target=self._rodar, daemon=True)

    def iniciar(self):
        app = self.app
        app.executar(lambda: app.db.execute(
            "UPDATE fontes SET status='erro', erro='interrompido (o servidor reiniciou); mande de novo' "
            "WHERE status IN ('lendo','analisando')"))
        app.acordar['fonte'].set()
        self.thread.start()
        return self

    def encerrar(self):
        self.parar.set()
        self.app.acordar['fonte'].set()
        self.thread.join(1)

    def _rodar(self):
        ev = self.app.acordar['fonte']
        while not self.parar.is_set():
            ev.wait(10)
            ev.clear()
            if self.parar.is_set():
                break
            try:
                ids = self.app.executar(lambda: [r['id'] for r in self.app.db.execute(
                    "SELECT id FROM fontes WHERE status='lendo' ORDER BY id")])
                for fid in ids:
                    if self.parar.is_set():
                        return
                    self.processar(fid)
            except Exception as e:
                log(f'fontes: {type(e).__name__}: {e}')

    def _status(self, fid, **campos):
        sets = ', '.join(f'{k}=?' for k in campos)
        self.app.executar(lambda: self.app.db.execute(f'UPDATE fontes SET {sets} WHERE id=?',
                                                       (*campos.values(), fid)))

    def processar(self, fid):
        app = self.app
        mem = app.fonte_mem.pop(fid, None)
        if mem is None:
            self._status(fid, status='erro', erro='conteúdo perdido; mande de novo')
            return
        avisos = []
        try:
            ua = f"atende-leads (+{app.url_publica() or UA_PADRAO})"
            pdf = None
            if 'url' in mem:
                paginas, avisos = ler_link(mem['url'], mem['max_paginas'], ua)
                fonte_padrao = mem['url']
            else:
                fonte_padrao = mem['nome']
                if extensao(mem['nome']) == 'pdf':
                    if pdf_por_anthropic(app):
                        pdf = base64.b64encode(mem['dados']).decode()
                        paginas = []
                    else:
                        paginas = [(mem['nome'], ler_pdf_local(mem['dados']))]
                else:
                    paginas = [(mem['nome'], texto_arquivo(mem['nome'], mem['dados']))]
                mem['dados'] = None
                if pdf is None and not (paginas and paginas[0][1].strip()):
                    raise Recusado('não achei texto no arquivo')
            caracteres = sum(len(t) for _f, t in paginas)
            self._status(fid, status='analisando', paginas=len(paginas) or 1, caracteres=caracteres,
                         avisos=json.dumps(avisos, ensure_ascii=False))
            validas = {f for f, _t in paginas} | {fonte_padrao}
            itens = self.gerar(paginas, pdf, avisos)
            if itens is None:
                itens = por_regras(app, paginas, mem.get('url'))
                origem_txt = 'regras'
            else:
                origem_txt = 'cérebro'
            origem_txt = 'propostas pelo cérebro' if origem_txt == 'cérebro' else 'propostas pelas regras'

            def gravar():
                lista = validar_itens(app, itens, validas, fonte_padrao)
                for _t, d in lista:
                    d['fonte_id'] = fid
                existentes = {normalizar(sugestao._proposta_json(r)['resposta']) for r in
                              app.db.execute("SELECT * FROM propostas WHERE status='nova'")}
                ids = sugestao._inserir(app, lista, 'fonte', existentes)
                app.db.execute("UPDATE fontes SET status='pronto', propostas=?, avisos=?, erro=NULL WHERE id=?",
                               (len(ids), json.dumps(avisos + [origem_txt], ensure_ascii=False), fid))
            app.executar(gravar)
        except Recusado as e:
            self._status(fid, status='erro', erro=str(e)[:300], avisos=json.dumps(avisos, ensure_ascii=False))
        except Exception as e:
            log(f'fonte {fid}: {type(e).__name__}: {e}')
            self._status(fid, status='erro', erro='falha ao processar a fonte')
        finally:
            mem.clear()

    def gerar(self, paginas, pdf, avisos):
        """Itens crus do cérebro da curadoria, ou None (sem LLM / tudo falhou → regras)."""
        app = self.app
        if not cerebro.ligado(app, 'curadoria'):
            if pdf is not None:
                raise Recusado('PDF precisa do cérebro Anthropic ou do pdftotext')
            return None
        base_txt = app.executar(lambda: base.texto_base(app))
        instr = INSTR.format(nome=app.cfg.get('nome') or 'uma empresa')
        if pdf is not None:
            usuario = app.executar(lambda: _usuario(app, None, 1, 1, paginas and paginas[0][0] or 'PDF anexo'))
            r = cerebro.perguntar(app, instr, usuario, base_txt, papel='curadoria', formato=SCHEMA, limpar=False,
                                  anexo={'media_type': 'application/pdf', 'data': pdf})
            d = cerebro.ler_json(r) if r else None
            if not isinstance(d, dict) or not isinstance(d.get('propostas'), list):
                raise Recusado('o cérebro não conseguiu ler o PDF')
            return d['propostas']
        blocos = dividir(paginas)
        if len(blocos) > MAX_BLOCOS:
            avisos.append(f'conteúdo longo: li os {MAX_BLOCOS} primeiros blocos de {len(blocos)}')
            blocos = blocos[:MAX_BLOCOS]
        fontes_txt = ', '.join(f for f, _t in paginas)[:3000]
        todos, algum = [], False
        for n, bloco in enumerate(blocos, 1):
            usuario = app.executar(lambda: _usuario(app, bloco, n, len(blocos), fontes_txt))
            r = cerebro.perguntar(app, instr, usuario, base_txt, papel='curadoria', formato=SCHEMA, limpar=False)
            d = cerebro.ler_json(r) if r else None
            if isinstance(d, dict) and isinstance(d.get('propostas'), list):
                algum = True
                todos.extend(d['propostas'])
            else:
                avisos.append(f'bloco {n}: o cérebro não respondeu')
        return todos if algum else None
