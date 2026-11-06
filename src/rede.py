"""HTTP de saída. Falha de rede nunca derruba a requisição.

Usa http.client (e não urllib.request) para mandar os headers com a grafia exata
(ex.: `apikey` minúsculo, como a Evolution documenta).
"""
import http.client
import json
import ssl
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .core import log


def postar(url, corpo, headers=None, timeout=5):
    """Devolve (ok_http, json|{}). ok_http=False em erro HTTP (>= 400) ou de conexão."""
    st, r = postar_status(url, corpo, headers, timeout)
    return 200 <= st < 300, r


def postar_status(url, corpo, headers=None, timeout=5):
    """Devolve (status_http, json|{}). status 0 = erro de conexão/timeout (vale tentar de novo)."""
    dados = json.dumps(corpo, ensure_ascii=False).encode('utf-8')
    try:
        u = urlsplit(url)
        if u.scheme == 'https':
            conn = http.client.HTTPSConnection(u.hostname, u.port or 443, timeout=timeout,
                                               context=ssl.create_default_context())
        elif u.scheme == 'http':
            conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
        else:
            return 0, {}
        caminho = (u.path or '/') + (f'?{u.query}' if u.query else '')
        cab = {'Content-Type': 'application/json', 'Content-Length': str(len(dados))}
        cab.update(headers or {})
        try:
            conn.request('POST', caminho, body=dados, headers=cab)
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        try:
            r = json.loads(raw) if raw else {}
        except ValueError:
            r = {}
        if not isinstance(r, dict):
            r = {'result': r}
        return resp.status, r
    except Exception as e:  # conexão recusada, timeout, DNS, TLS
        log(f'rede: falha em POST: {type(e).__name__}')
        return 0, {}


def baixar(url, destino, timeout=30):
    try:
        with urlopen(Request(url), timeout=timeout) as resp, open(destino, 'wb') as f:
            f.write(resp.read())
        return True
    except Exception as e:
        log(f'rede: falha ao baixar: {type(e).__name__}')
        return False
