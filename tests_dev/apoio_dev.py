"""Apoio dos testes de desenvolvimento: servidor real + Telegram/Evolution falsos locais."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RAIZ = Path(__file__).resolve().parent.parent
TOKEN = 'TROQUE-ESTE-TOKEN'


class Falso:
    """Servidor falso que grava cada POST e responde no formato do Telegram/Evolution."""

    def __init__(self, falhar_edicao=False):
        self.chamadas = []
        self.lock = threading.Lock()
        self.prox_id = 100
        self.falhar_edicao = falhar_edicao
        dono = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get('Content-Length') or 0)
                corpo = json.loads(self.rfile.read(n) or b'{}')
                metodo = self.path.rsplit('/', 1)[-1]
                with dono.lock:
                    dono.prox_id += 1
                    mid = dono.prox_id
                    dono.chamadas.append({'path': self.path, 'metodo': metodo, 'corpo': corpo,
                                          'headers': dict(self.headers), 'mid': mid})
                if metodo == 'editMessageText' and dono.falhar_edicao:
                    r = {'ok': False, 'description': 'Bad Request: message to edit not found'}
                    st = 400
                elif metodo == 'getFile':
                    r = {'ok': True, 'result': {'file_id': corpo.get('file_id'), 'file_path': 'voice/a.ogg'}}
                    st = 200
                else:
                    r = {'ok': True, 'result': {'message_id': mid}}
                    st = 200
                dados = json.dumps(r).encode()
                self.send_response(st)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def do_GET(self):
                dados = b'OggS-falso'
                self.send_response(200)
                self.send_header('Content-Length', str(len(dados)))
                self.end_headers()
                self.wfile.write(dados)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = f'http://127.0.0.1:{self.srv.server_port}'
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def de(self, metodo):
        with self.lock:
            return [c for c in self.chamadas if c['metodo'] == metodo]

    def textos(self, metodo='sendMessage', chat=None):
        return [c['corpo'].get('text', '') for c in self.de(metodo)
                if chat is None or str(c['corpo'].get('chat_id')) == str(chat)]

    def limpar(self):
        with self.lock:
            self.chamadas.clear()

    def parar(self):
        self.srv.shutdown()


class Servidor:
    def __init__(self, agora='2026-11-09T10:00', env=None, cfg=None, dados=None, manter=False):
        self.dir = dados or tempfile.mkdtemp(prefix='al-')
        self.manter = manter
        if cfg is not None:
            Path(self.dir, 'negocio.json').write_text(json.dumps(cfg, ensure_ascii=False))
        e = {k: v for k, v in os.environ.items() if not k.startswith(('TELEGRAM_', 'EVOLUTION_', 'WEBHOOK_'))}
        if agora:
            e['ATENDE_AGORA'] = agora
        e.update(env or {})
        self.p = subprocess.Popen([sys.executable, str(RAIZ / 'atende'), 'serve', '--porta', '0', '--dados', self.dir],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=e, text=True)
        linha = self.p.stdout.readline().strip()
        assert linha.startswith('PORTA='), (linha, self.p.stderr.read() if self.p.poll() is not None else '')
        self.url = f'http://127.0.0.1:{linha.split("=")[1]}'

    def req(self, metodo, rota, corpo=None, headers=None, bruto=False):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        r = Request(self.url + rota, data=dados, method=metodo, headers={'Content-Type': 'application/json',
                                                                          **(headers or {})})
        try:
            with urlopen(r, timeout=20) as resp:
                raw = resp.read()
                return resp.status, (raw.decode() if bruto else (json.loads(raw) if raw else None))
        except HTTPError as e:
            raw = e.read()
            try:
                return e.code, (raw.decode() if bruto else json.loads(raw))
            except ValueError:
                return e.code, raw.decode()

    def g(self, metodo, rota, corpo=None, **kw):
        return self.req(metodo, rota, corpo, {'X-Token': TOKEN}, **kw)

    def e(self, codigo, metodo, rota, corpo=None):
        return self.req(metodo, rota, corpo, {'X-Codigo': codigo})

    def msg(self, telefone, texto, **extra):
        # canal whatsapp pela API = simulação do WhatsApp, só com o token do gestor (§4)
        corpo = {'telefone': telefone, 'texto': texto, 'canal': 'whatsapp', **extra}
        h = {'X-Token': TOKEN} if corpo['canal'] == 'whatsapp' else None
        return self.req('POST', '/api/mensagens', corpo, h)

    def relogio(self, agora):
        st, r = self.g('POST', '/api/relogio', {'agora': agora})
        assert st == 200, r
        return self.g('POST', '/api/tarefas/rodar')[1]

    def tg(self, update, segredo='seg-tg'):
        return self.req('POST', '/webhook/telegram', update, {'X-Telegram-Bot-Api-Secret-Token': segredo})

    def parar(self):
        self.p.terminate()
        try:
            self.p.wait(5)
        except subprocess.TimeoutExpired:
            self.p.kill()
        err = self.p.stderr.read()
        if not self.manter:
            shutil.rmtree(self.dir, ignore_errors=True)
        ruins = [l for l in err.splitlines() if 'erro interno' in l or 'Traceback' in l or 'ignorado' in l
                 or 'pedido inválido' in l]
        assert not ruins, ruins
        return err


def cfg_exemplo(**mudar):
    cfg = json.loads((RAIZ / 'exemplos' / 'negocio.json').read_text())
    cfg['equipe'] = [
        {'id': 'ana', 'nome': 'Ana', 'telefone': '5541999990010', 'codigo': 'ana-1234-dev01'},
        {'id': 'bruno', 'nome': 'Bruno', 'telefone': '5541999990011', 'codigo': 'bruno-1234-dev01'},
        {'id': 'carla', 'nome': 'Carla', 'telefone': '5541999990012', 'codigo': 'carla-1234-dev01'},
    ]
    cfg.update(mudar)
    return cfg


def env_tg(falso, evo=None):
    e = {'TELEGRAM_API_URL': falso.url, 'TELEGRAM_TOKEN': '123:abc', 'TELEGRAM_GRUPO_ID': '-100', 'TELEGRAM_SEGREDO': 'seg-tg'}
    if evo:
        e.update({'EVOLUTION_URL': evo.url, 'EVOLUTION_API_KEY': 'k', 'EVOLUTION_INSTANCIA': 'loja',
                  'WEBHOOK_SEGREDO': 'seg-evo'})
    return e


def upd_msg(from_id, texto, chat_id=None, reply=None, uid=[0]):
    uid[0] += 1
    m = {'message_id': 9000 + uid[0], 'from': {'id': from_id}, 'chat': {'id': chat_id or from_id, 'type': 'private'
                                                                         if not chat_id else 'supergroup'},
         'text': texto}
    if reply:
        m['reply_to_message'] = {'message_id': reply}
    return {'update_id': uid[0], 'message': m}


def upd_cb(from_id, dados, uid=[0]):
    uid[0] += 1
    return {'update_id': 50000 + uid[0], 'callback_query': {'id': f'cb{uid[0]}', 'from': {'id': from_id},
                                                            'data': dados, 'message': {'message_id': 1,
                                                                                       'chat': {'id': from_id}}}}
