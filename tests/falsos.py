"""Cérebros falsos locais (seção 14): API no formato Anthropic/OpenAI e binário de CLI. Nada sai da máquina."""
import json
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FalsoLLM:
    """Responde no formato da Anthropic (/v1/messages) ou OpenAI (/chat/completions) e grava cada pedido.

    `texto`: o que o modelo "responde"; `recusa`: stop_reason refusal; `atraso`: segundos antes de responder.
    """

    def __init__(self, texto='Resposta do modelo.'):
        self.texto = texto
        self.recusa = False
        self.atraso = 0.0
        self.pedidos = []
        self.trava = threading.Lock()
        dono = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
                with dono.trava:
                    dono.pedidos.append({'rota': self.path, 'json': corpo,
                                         'headers': {k.lower(): v for k, v in self.headers.items()}})
                if dono.atraso:
                    time.sleep(dono.atraso)
                texto = dono.texto(corpo) if callable(dono.texto) else dono.texto
                if self.path.endswith('/messages'):
                    r = {'id': 'msg_falso', 'type': 'message', 'role': 'assistant',
                         'content': [{'type': 'text', 'text': texto}],
                         'stop_reason': 'refusal' if dono.recusa else 'end_turn'}
                else:
                    r = {'choices': [{'message': {'role': 'assistant', 'content': texto}}]}
                b = json.dumps(r).encode()
                try:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(b)))
                    self.end_headers()
                    self.wfile.write(b)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.srv.server_address[1]}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def lista(self):
        with self.trava:
            return list(self.pedidos)

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


def cli_falso(pasta, resposta='Resposta do CLI.'):
    """Script que grava args e stdin e imprime `resposta`. Se o stdin não for fechado, `cat` trava (e o teste acusa)."""
    exe = pasta / 'cli-falso'
    exe.write_text('#!/bin/sh\n'
                   f'printf "%s\\n" "$@" > "{pasta}/args.txt"\n'
                   f'cat > "{pasta}/stdin.txt"\n'
                   f'printf "%s\\n" "{resposta}"\n', encoding='utf-8')
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def cfg_cerebro(api, cerebro, info=None, extra=None):
    """Grava cerebro (e info) pelo PUT /api/gestor/config."""
    st, cfg = api.get('/api/gestor/config')
    assert st == 200, (st, cfg)
    cfg['cerebro'] = cerebro
    if info is not None:
        cfg['info'] = info
    cfg.update(extra or {})
    st, r = api.put('/api/gestor/config', cfg)
    assert st == 200, (st, r)
    return r
