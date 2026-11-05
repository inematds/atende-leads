"""Cérebro ollama/openai contra servidor falso local; erro cai na regra."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from apoio_dev import Servidor, cfg_exemplo


def falso_llm(resposta):
    vistos = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get('Content-Length') or 0)
            corpo = json.loads(self.rfile.read(n))
            vistos.append((self.path, corpo, dict(self.headers)))
            if self.path.endswith('/api/chat'):
                r = {'message': {'role': 'assistant', 'content': resposta}}
            else:
                r = {'choices': [{'message': {'role': 'assistant', 'content': resposta}}]}
            d = json.dumps(r).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(d)))
            self.end_headers()
            self.wfile.write(d)

        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_port}', vistos


def test_ollama_responde_duvida():
    srv, url, vistos = falso_llm('Entregamos em todo o Brasil.')
    s = Servidor(cfg=cfg_exemplo(cerebro={'tipo': 'ollama', 'url': url, 'modelo': 'qwen'}))
    try:
        s.msg('41999990070', 'qual o horario de atendimento', nome='Ivo')
        st, r = s.msg('41999990070', 'vocês entregam em Curitiba?')
        assert r['respostas'] == ['Entregamos em todo o Brasil.']
        assert vistos and vistos[-1][0] == '/api/chat'
        assert s.req('GET', '/api/saude')[1]['cerebro'] == 'ollama'
    finally:
        s.parar()
        srv.shutdown()


def test_openai_resumo_e_chave():
    srv, url, vistos = falso_llm('Quer o plano anual\nUrgência: hoje')
    s = Servidor(cfg=cfg_exemplo(cerebro={'tipo': 'openai', 'url': url + '/v1', 'modelo': 'm'}),
                 env={'CEREBRO_API_KEY': 'sk-falsa'})
    try:
        st, r = s.msg('41999990071', 'quero falar com um atendente', nome='Lu')
        st, f = s.g('GET', f"/api/gestor/leads/{r['lead']['id']}")
        assert f['chamados'][-1]['resumo'].startswith('Quer o plano anual')
        assert vistos[-1][0] == '/v1/chat/completions' and vistos[-1][2].get('Authorization') == 'Bearer sk-falsa'
    finally:
        s.parar()
        srv.shutdown()


def test_cerebro_fora_do_ar_cai_na_regra():
    s = Servidor(cfg=cfg_exemplo(cerebro={'tipo': 'ollama', 'url': 'http://127.0.0.1:9', 'modelo': 'x'}))
    try:
        s.msg('41999990072', 'qual o horario de atendimento', nome='Gil')
        st, r = s.msg('41999990072', 'zzzz qqqq')
        assert 'não entendi' in r['respostas'][0]
        st, r = s.msg('41999990073', 'falar com atendente', nome='Ana')
        st, f = s.g('GET', f"/api/gestor/leads/{r['lead']['id']}")
        assert 'Disse: "falar com atendente"' in f['chamados'][-1]['resumo']
    finally:
        s.parar()
