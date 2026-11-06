"""Playwright 1.7.8: sobe site falso + cérebro falso + atende (porta livre) e roda fluxo.js num tema. Uso: python3 harness.py claro|escuro|marinho"""
import json, os, shutil, socket, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
RAIZ = '/home/nmaldaner/projetos/atende-leads'
sys.path.insert(0, RAIZ + '/tests')
from falsos import FalsoLLM

tema = sys.argv[1]
paginas = {
 '/robots.txt': ('text/plain', 'User-agent: *\nDisallow: /privado\n'),
 '/': ('text/html', '<html><head><title>Padaria Exemplo</title></head><body><nav><a href="/contato">Contato</a><a href="/cardapio">Cardápio</a></nav><h1>Padaria Exemplo</h1><p>Pães artesanais.</p></body></html>'),
 '/cardapio': ('text/html', '<table><tr><td>Bolo de cenoura</td><td>R$ 25,00</td></tr><tr><td>Plano anual</td><td>R$ 999</td></tr></table>'),
 '/contato': ('text/html', '<p>Endereço: Rua das Flores, 123 - Centro, Curitiba - PR, CEP 80000-000</p><p>Segunda a sexta, das 7h às 19h</p>'),
}
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        t, c = paginas.get(self.path, ('text/plain', 'x')); b = c.encode()
        self.send_response(200 if self.path in paginas else 404); self.send_header('Content-Type', t + '; charset=utf-8')
        self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
    def log_message(self, *a): pass
site = ThreadingHTTPServer(('127.0.0.1', 0), H); threading.Thread(target=site.serve_forever, daemon=True).start()
sp = site.server_address[1]; SITE = f'http://127.0.0.1:{sp}'

def responder(corpo):
    sis = corpo['system'][0]['text']; u = corpo['messages'][0]['content']
    if 'montar a base de conhecimento' in sis:
        return json.dumps({'propostas': [
            {'tipo': 'info', 'campo': 'endereco', 'resposta': 'Rua das Flores, 123 - Centro, Curitiba - PR, CEP 80000-000', 'perguntas': [], 'nome': '', 'palavras': [], 'horarios': '', 'faq_id': '', 'produto_id': '', 'preco_novo': '', 'promocao': '', 'validade': '',
             'justificativa': 'O site traz o endereço com CEP; a base tem outro endereço no FAQ.', 'fonte': SITE + '/contato', 'evidencia': 'Endereço: Rua das Flores, 123 - Centro, Curitiba - PR, CEP 80000-000', 'contradiz': True},
            {'tipo': 'produto', 'nome': 'Bolo de cenoura', 'palavras': ['bolo', 'bolo de cenoura'], 'preco_novo': 'R$ 25,00', 'perguntas': [], 'resposta': '', 'campo': '', 'horarios': '', 'faq_id': '', 'produto_id': '', 'promocao': '', 'validade': '',
             'justificativa': 'Produto do cardápio que não está no cadastro.', 'fonte': SITE + '/cardapio', 'evidencia': 'Bolo de cenoura | R$ 25,00', 'contradiz': False},
            {'tipo': 'preco', 'produto_id': 'plano-anual', 'preco_novo': 'R$ 999', 'perguntas': [], 'resposta': '', 'campo': '', 'nome': '', 'palavras': [], 'horarios': '', 'faq_id': '', 'promocao': '', 'validade': '',
             'justificativa': 'A base diz R$ 1.200; o cardápio do site diz R$ 999.', 'fonte': SITE + '/cardapio', 'evidencia': 'Plano anual | R$ 999', 'contradiz': True}]}, ensure_ascii=False)
    if 'conferindo a base' in sis:
        if 'entreg' in u.lower():
            return json.dumps({'resposta': 'Isso não está na base. Não há nada sobre entrega.', 'fontes': [], 'lacuna': True, 'contradicao': '',
                               'proposta': {'tipo': 'info', 'perguntas': ['vocês entregam?'], 'resposta': '', 'campo': 'entrega', 'nome': '', 'preco_novo': '', 'produto_id': ''}}, ensure_ascii=False)
        return json.dumps({'resposta': 'O FAQ diz segunda a sexta, das 8h às 18h; os Horários dizem todos os dias, 00:00–23:59.',
                           'fontes': [{'secao': 'FAQ: qual o horario de atendimento', 'trecho': 'Atendemos de segunda a sexta, das 8h às 18h.'}, {'secao': 'Horários', 'trecho': 'Nosso atendimento: seg a dom 00:00–23:59.'}],
                           'lacuna': False, 'contradicao': 'O FAQ e os Horários cadastrados dizem horários diferentes.',
                           'proposta': {'tipo': '', 'perguntas': [], 'resposta': '', 'campo': '', 'nome': '', 'preco_novo': '', 'produto_id': ''}}, ensure_ascii=False)
    return 'SEM_RESPOSTA'
llm = FalsoLLM(); llm.texto = responder

dados = tempfile.mkdtemp()
cfg = json.load(open(RAIZ + '/tests/fixtures/negocio.json'))
cfg['cerebro'] = {'tipo': 'anthropic', 'modelo': 'claude-sonnet-5-5', 'esforco': 'low'}
cfg['cerebro_curadoria'] = {'tipo': 'anthropic', 'modelo': 'claude-opus-5-5', 'esforco': 'medium'}
cfg['horarios'] = {d: [['00:00', '23:59']] for d in ('seg', 'ter', 'qua', 'qui', 'sex', 'sab', 'dom')}
cfg['aparencia'] = {'tema': tema}
json.dump(cfg, open(dados + '/negocio.json', 'w'), ensure_ascii=False)
s = socket.socket(); s.bind(('127.0.0.1', 0)); porta = s.getsockname()[1]; s.close()
assert not 18090 <= porta <= 18093
env = {k: v for k, v in os.environ.items() if not k.startswith(('CEREBRO_', 'ATENDE_', 'TELEGRAM_', 'EVOLUTION_'))}
env.update({'CEREBRO_API_KEY': 'sk-falsa', 'CEREBRO_ANTHROPIC_URL': llm.url + '/v1/messages', 'ATENDE_FONTE_PERMITIR_LOCAL': f'127.0.0.1:{sp}'})
srv = subprocess.Popen([RAIZ + '/atende', 'serve', '--porta', str(porta), '--dados', dados], cwd=RAIZ, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
print(srv.stdout.readline().strip())
try:
    r = subprocess.run(['node', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fluxo.js'), f'http://127.0.0.1:{porta}', SITE, tema], timeout=240)
    rc = r.returncode
finally:
    srv.terminate(); srv.wait(5); llm.fechar(); site.shutdown(); shutil.rmtree(dados, ignore_errors=True)
sys.exit(rc)
