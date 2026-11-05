"""CLI e HTTP. Cada requisição roda numa transação sob o mesmo lock (assumir é atômico)."""
import argparse
import hmac
import json
import re
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlsplit

from .core import App, Erro, ROOT, log, versao
from . import backup, bot, cerebro, chamados, conversa, equipe, evolution, gestao, paginas, tarefas
from . import telegram as tg


class Bruto:
    def __init__(self, conteudo, tipo, extra=None):
        self.conteudo = conteudo.encode('utf-8') if isinstance(conteudo, str) else conteudo
        self.tipo = tipo
        self.extra = extra or {}


ESTATICOS = {
    '/': ('index.html', 'text/html'), '/equipe': ('equipe.html', 'text/html'), '/gestor': ('gestor.html', 'text/html'),
    '/web/style.css': ('style.css', 'text/css'), '/web/chat.js': ('chat.js', 'text/javascript'),
    '/web/meu.js': ('meu.js', 'text/javascript'), '/web/equipe.js': ('equipe.js', 'text/javascript'),
    '/web/gestor.js': ('gestor.js', 'text/javascript'), '/web/comum.js': ('comum.js', 'text/javascript'),
}


# ---------- autenticação ----------
def eh_gestor(c, h):
    tok = h.get('X-Token') or ''
    return bool(tok) and hmac.compare_digest(tok.encode(), str(c.cfg.get('token_gestor', '')).encode())


def colab_do_codigo(c, h):
    cod = h.get('X-Codigo') or ''
    if not cod:
        return None
    for m in c.cfg.get('equipe', []):
        if hmac.compare_digest(cod.encode(), str(m.get('codigo', '')).encode()):
            return m['id']
    return None


def exigir_gestor(c, h):
    if not eh_gestor(c, h):
        raise Erro(401, 'Token do gestor inválido')


def quem_equipe(c, h):
    """Devolve ('E', colab) ou ('G', None). 401 se nenhum."""
    colab = colab_do_codigo(c, h)
    if colab:
        return 'E', colab
    if eh_gestor(c, h):
        return 'G', None
    raise Erro(401, 'Código inválido')


def colab_do_corpo(c, b, q, obrigatorio=True):
    ident = (b or {}).get('colaborador') or q.get('colaborador')
    if not ident:
        if obrigatorio:
            raise Erro(422, 'Informe "colaborador"')
        return None
    c.colab(ident)
    return ident


# ---------- rotas ----------
def rotear(c, metodo, rota, q, b, h):
    if metodo == 'GET' and rota == '/api/saude':
        return 200, {'ok': True, 'versao': versao(), 'evolution': evolution.configurado(),
                     'telegram': tg.configurado(), 'cerebro': cerebro.tipo(c)}
    if metodo == 'POST' and rota == '/api/mensagens':
        lead, respostas = conversa.receber(c, b.get('telefone'), b.get('texto'), b.get('canal') or 'web',
                                           b.get('nome'))
        return 200, {'lead': lead, 'respostas': respostas}
    if metodo == 'GET' and rota == '/widget.js':
        return 200, Bruto(paginas.widget_js(c), 'text/javascript')
    m = re.fullmatch(r'/ligar/([\w-]+)', rota)
    if metodo == 'GET' and m:
        pag = paginas.pagina_ligar(c, m[1])
        if pag is None:
            raise Erro(404, 'Não encontrado')
        return 200, Bruto(pag, 'text/html')
    m = re.fullmatch(r'/meu/([\w-]+)', rota)
    if metodo == 'GET' and m:
        return 200, Bruto(paginas.pagina_meu(c, m[1]), 'text/html')
    m = re.fullmatch(r'/api/meu/([\w-]+)(?:/(falar|apagar))?', rota)
    if m:
        if metodo == 'GET' and not m[2]:
            return 200, paginas.api_meu(c, m[1])
        if metodo == 'POST' and m[2] == 'falar':
            return 200, conversa.falar(c, m[1])
        if metodo == 'POST' and m[2] == 'apagar':
            return 200, conversa.apagar(c, m[1])

    # ---- gestor ----
    if rota == '/api/relogio' and metodo == 'POST':
        exigir_gestor(c, h)
        return 200, {'ok': True, 'agora': c.mudar_relogio(b.get('agora'))}
    if rota == '/api/tarefas/rodar' and metodo == 'POST':
        exigir_gestor(c, h)
        return 200, tarefas.rodar(c)
    if rota == '/api/saida' and metodo == 'GET':
        exigir_gestor(c, h)
        return 200, evolution.listar(c)
    if rota.startswith('/api/gestor/'):
        exigir_gestor(c, h)
        return rotear_gestor(c, metodo, rota[len('/api/gestor'):], q, b)

    # ---- painel / equipe ----
    if rota == '/api/painel' and metodo == 'GET':
        quem_equipe(c, h)
        return 200, equipe.painel(c)
    if rota.startswith('/api/equipe/'):
        papel, colab = quem_equipe(c, h)
        return rotear_equipe(c, metodo, rota[len('/api/equipe'):], q, b, papel, colab)
    raise Erro(404, 'Rota inexistente')


def rotear_equipe(c, metodo, rota, q, b, papel, colab):
    g = papel == 'G'
    if metodo == 'GET' and rota == '/eu':
        ident = colab_do_corpo(c, b, q) if g else colab
        return 200, eu(c, ident)
    if metodo == 'POST' and rota == '/status':
        ident = colab_do_corpo(c, b, q) if g else colab
        return 200, equipe.mudar_status(c, ident, b.get('status'))
    m = re.fullmatch(r'/chamados/(\d+)/(assumir|passar|responder|fechar|devolver)', rota)
    if metodo == 'POST' and m:
        ident, acao = int(m[1]), m[2]
        c.chamado(ident)
        if acao == 'assumir':
            return 200, chamados.assumir(c, ident, colab_do_corpo(c, b, q) if g else colab)
        if acao == 'passar':
            alvo = colab_do_corpo(c, b, q, obrigatorio=False) if g else colab
            return 200, chamados.passar(c, ident, alvo or c.chamado(ident)['ofertado_a'])
        if acao == 'responder':
            return 200, chamados.responder(c, ident, None if g else colab, b.get('texto'))
        if acao == 'fechar':
            return 200, chamados.fechar(c, ident, None if g else colab, b)
        if acao == 'devolver':
            return 200, chamados.devolver(c, ident, None if g else colab)
    m = re.fullmatch(r'/leads/(\d+)', rota)
    if metodo == 'GET' and m:
        lead_id = int(m[1])
        c.lead(lead_id)
        if not g and not bot.pode_ver(c, colab, lead_id):
            raise Erro(403, 'Você não pode ver este lead')
        return 200, gestao.ficha(c, lead_id)
    raise Erro(404, 'Rota inexistente')


def eu(c, colab):
    d = equipe.dados_colab(c, colab)
    d['chamados'] = [chamados.json_chamado(c, ch) for ch in equipe.atendendo_de(c, colab)]
    d['ofertas'] = [chamados.json_chamado(c, ch) for ch in c.db.execute(
        "SELECT * FROM chamados WHERE status IN ('aguardando','alerta') AND (ofertado_a=? OR status='alerta') "
        'ORDER BY aberto_em, id', (colab,))]
    d['retornos_hoje'] = bot.retornos_hoje(c, colab)
    d['produtos'] = [{'id': p['id'], 'nome': p['nome']} for p in c.cfg.get('produtos', [])]
    return d


def rotear_gestor(c, metodo, rota, q, b):
    if metodo == 'GET' and rota == '/ao-vivo':
        return 200, gestao.ao_vivo(c)
    if metodo == 'GET' and rota == '/hoje':
        return 200, gestao.hoje(c)
    if metodo == 'GET' and rota == '/leads':
        return 200, gestao.leads(c, q)
    m = re.fullmatch(r'/leads/(\d+)', rota)
    if metodo == 'GET' and m:
        return 200, gestao.ficha(c, int(m[1]))
    m = re.fullmatch(r'/chamados/(\d+)/(transferir|reabrir)', rota)
    if metodo == 'POST' and m:
        ident = int(m[1])
        if m[2] == 'transferir':
            return 200, chamados.transferir(c, ident, colab_do_corpo(c, b, q))
        return 200, chamados.reabrir(c, ident)
    m = re.fullmatch(r'/equipe/([^/]+)/status', rota)
    if metodo == 'POST' and m:
        return 200, equipe.mudar_status(c, unquote(m[1]), b.get('status'))
    if rota == '/config':
        if metodo == 'GET':
            return 200, gestao.config_publica(c)
        if metodo == 'PUT':
            return 200, gestao.gravar_config(c, b)
    if metodo == 'GET' and rota == '/exportar.csv':
        return 200, Bruto(gestao.exportar_csv(c), 'text/csv',
                          {'Content-Disposition': 'attachment; filename="leads.csv"'})
    raise Erro(404, 'Rota inexistente')


# ---------- servidor ----------
def criar_handler(app):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'atende-leads'
        sys_version = ''

        def _enviar(self, status, corpo, tipo, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', tipo + '; charset=utf-8')
            self.send_header('Content-Length', str(len(corpo)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(corpo)

        def processar(self):
            url = urlsplit(self.path)
            rota = url.path.rstrip('/') or '/'
            if self.command == 'GET' and rota in ESTATICOS:
                nome, tipo = ESTATICOS[rota]
                try:
                    conteudo = (ROOT / 'web' / nome).read_bytes()
                except OSError:
                    return self._enviar(404, b'{"erro": "N\\u00e3o encontrado"}', 'application/json')
                extra = {}
                if tipo == 'text/html' and rota != '/':
                    extra['X-Frame-Options'] = 'DENY'
                return self._enviar(200, conteudo, tipo, extra)
            webhook = rota.startswith('/webhook/')
            try:
                tamanho = int(self.headers.get('Content-Length') or 0)
                if tamanho < 0 or tamanho > 2 * 1024 * 1024:
                    raise Erro(413, 'Corpo muito grande')
                bruto = self.rfile.read(tamanho) if tamanho else b''
                if webhook:
                    status, resposta = self.webhook(rota, bruto)
                else:
                    try:
                        b = json.loads(bruto.decode('utf-8')) if bruto.strip() else {}
                    except (ValueError, UnicodeDecodeError):
                        raise Erro(400, 'JSON inválido')
                    if not isinstance(b, dict):
                        raise Erro(400, 'Objeto JSON esperado')
                    q = {k: v[-1] for k, v in parse_qs(url.query).items()}
                    with app.transacao():
                        status, resposta = rotear(app, self.command, rota, q, b, self.headers)
                        if app.sujo:
                            equipe.atualizar_painel(app)
            except Erro as e:
                status, resposta = e.status, {'erro': e.mensagem}
            except (ValueError, KeyError, TypeError) as e:
                log(f'pedido inválido: {type(e).__name__}: {e}')
                status, resposta = 400, {'erro': 'Pedido inválido'}
            except Exception as e:
                log(f'erro interno: {type(e).__name__}: {e}')
                status, resposta = 500, {'erro': 'Erro interno'}
            if isinstance(resposta, Bruto):
                return self._enviar(status, resposta.conteudo, resposta.tipo, resposta.extra)
            corpo = json.dumps(resposta, ensure_ascii=False).encode('utf-8')
            self._enviar(status, corpo, 'application/json')

        def webhook(self, rota, bruto):
            m = re.fullmatch(r'/webhook/evolution/([^/]+)', rota)
            if self.command == 'POST' and m:
                evolution.autorizar(unquote(m[1]))
                destino = evolution.receber
            elif self.command == 'POST' and rota == '/webhook/telegram':
                bot.autorizar(self.headers)
                destino = bot.receber
            else:
                raise Erro(404, 'Rota inexistente')
            try:
                b = json.loads(bruto.decode('utf-8')) if bruto.strip() else {}
            except (ValueError, UnicodeDecodeError):
                return 200, {'ok': True}
            try:
                with app.transacao():
                    destino(app, b)
                    if app.sujo:
                        equipe.atualizar_painel(app)
            except Exception as e:
                log(f'webhook {rota.split("/")[2]}: ignorado: {type(e).__name__}: {e}')
            return 200, {'ok': True}

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = processar

        def log_message(self, *args):
            pass

    return Handler


def relogio_automatico(app, parar):
    while not parar.wait(30):
        try:
            with app.transacao():
                tarefas.rodar(app)
                if app.sujo:
                    equipe.atualizar_painel(app)
        except Exception as e:
            log(f'tarefas: {type(e).__name__}: {e}')


def main(argv=None):
    p = argparse.ArgumentParser(prog='atende', description='Atendimento de leads (WhatsApp → equipe no Telegram)')
    sub = p.add_subparsers(dest='comando', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--porta', type=int, default=8080)
    s.add_argument('--host', default='127.0.0.1')
    s.add_argument('--dados', required=True)
    bk = sub.add_parser('backup')
    bk.add_argument('--dados', required=True)
    bk.add_argument('--saida', required=True)
    rs = sub.add_parser('restaurar')
    rs.add_argument('--dados', required=True)
    rs.add_argument('--arquivo', required=True)
    a = p.parse_args(argv)
    if a.comando == 'backup':
        try:
            backup.copiar(a.dados, a.saida)
        except Exception as e:
            p.exit(1, f'Falha no backup: {e}\n')
        print(f'Backup gravado em {a.saida}', file=sys.stderr)
        return
    if a.comando == 'restaurar':
        try:
            backup.restaurar(a.dados, a.arquivo)
        except Exception as e:
            p.exit(1, f'Falha na restauração: {e}\n')
        print(f'Restaurado em {a.dados}', file=sys.stderr)
        return
    app = App(a.dados)
    servidor = ThreadingHTTPServer((a.host, a.porta), criar_handler(app))
    servidor.daemon_threads = True
    parar = threading.Event()
    if not app.modo_teste:
        threading.Thread(target=relogio_automatico, args=(app, parar), daemon=True).start()
    def _sair(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, _sair)
    print(f'PORTA={servidor.server_port}', flush=True)
    try:
        servidor.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        parar.set()
        servidor.server_close()
        time.sleep(0.05)
        app.fechar()
