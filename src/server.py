"""CLI e HTTP. Cada requisição roda numa transação curta sob o mesmo lock (assumir é atômico).

Dentro do lock só há banco: envios ao Telegram/WhatsApp vão para a caixa de saída (src/saida.py) e
cérebro/áudio rodam fora do lock (App.executar + App.pronto).
"""
import argparse
import hmac
import ipaddress
import json
import os
import re
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from .core import App, Erro, ROOT, log, versao
from . import (backup, bot, cerebro, chamados, conversa, equipe, evolution, gestao, limite, paginas, polling,
               saida, tarefas)
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


# ---------- IP do cliente (proxy reverso confiável) ----------
PROXY_PADRAO = '127.0.0.1/32,::1/128,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16'


def redes_confiaveis(texto=None):
    """CIDRs de ATENDE_PROXY_CONFIAVEL (padrão: loopback + redes privadas, onde ficam o Caddy e a bridge do Docker).
    Vazio = nunca confia no X-Forwarded-For."""
    if texto is None:
        texto = os.environ.get('ATENDE_PROXY_CONFIAVEL', PROXY_PADRAO)
    redes = []
    for parte in texto.split(','):
        parte = parte.strip()
        if not parte:
            continue
        try:
            redes.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            log(f'ATENDE_PROXY_CONFIAVEL: ignorado {parte!r}')
    return redes


def _endereco(ip):
    try:
        a = ipaddress.ip_address(str(ip).strip())
    except ValueError:
        return None
    return a.ipv4_mapped if a.version == 6 and a.ipv4_mapped else a


def ip_cliente(peer, xff, redes):
    """IP da conexão; se ela vem de um proxy confiável, o primeiro IP não confiável do X-Forwarded-For,
    lido da direita para a esquerda (o proxy acrescenta o cliente no fim)."""
    def confia(ip):
        a = _endereco(ip)
        return a is not None and any(a in r for r in redes)
    if not xff or not confia(peer):
        return peer
    partes = [p.strip() for p in xff.split(',') if p.strip()]
    for p in reversed(partes):
        if not confia(p):
            return p
    return partes[0] if partes else peer


# ---------- autenticação ----------
def _ip(c):
    return getattr(c._local, 'ip', None) or '?'


def _errou(c):
    """Credencial errada: conta a falha; depois de 5 no minuto (por IP), as erradas recebem 429.
    A credencial certa nunca é barrada (equipe inteira atrás do mesmo proxy não fica trancada)."""
    chave = ('ip', _ip(c))
    if limite.bloqueado(chave):
        limite.falhou(chave)
        raise Erro(429, limite.MENSAGEM)
    limite.falhou(chave)


def eh_gestor(c, h):
    tok = h.get('X-Token') or ''
    if not tok:
        return False
    if hmac.compare_digest(tok.encode(), str(c.cfg.get('token_gestor', '')).encode()):
        return True
    _errou(c)
    return False


def colab_do_codigo(c, h):
    cod = h.get('X-Codigo') or ''
    if not cod:
        return None
    achado = None
    for m in c.cfg.get('equipe', []):
        if hmac.compare_digest(cod.encode(), str(m.get('codigo', '')).encode()):
            achado = m['id']
    if achado is None:
        _errou(c)
    return achado


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


# ---------- limites do chat web (seção 4) ----------
def cria_lead_web(metodo, rota, b):
    return (metodo == 'POST' and rota == '/api/mensagens' and (b.get('canal') or 'web') != 'whatsapp'
            and not b.get('sessao'))


def rota_publica_de_chamado(metodo, rota, b):
    """Rotas públicas que podem abrir chamado: chat web e 'Quero falar agora' da página do lead."""
    if metodo != 'POST':
        return False
    if rota == '/api/mensagens':
        return (b.get('canal') or 'web') != 'whatsapp'
    return bool(re.fullmatch(r'/api/meu/[\w-]+/falar', rota))


def saude(c):
    return {'ok': True, 'versao': versao(), 'evolution': evolution.configurado(),
            'telegram': tg.configurado(), 'telegram_modo': tg.modo(), 'cerebro': cerebro.tipo(c)}


# ---------- rotas ----------
def rotear(c, metodo, rota, q, b, h):
    if metodo == 'GET' and rota == '/api/saude':
        return 200, saude(c)
    if metodo == 'POST' and rota == '/api/mensagens':
        if (b.get('canal') or 'web') == 'whatsapp':
            # Simulação do WhatsApp (testes/demonstração): só o gestor. O WhatsApp real chega pelo webhook.
            exigir_gestor(c, h)
            lead, respostas = conversa.receber(c, b.get('telefone'), b.get('texto'), 'whatsapp', b.get('nome'))
            return 200, {'lead': lead, 'respostas': respostas}
        # Chat web: identidade = sessão. Sem `sessao` → lead web novo (o telefone é só contato).
        lead, respostas = conversa.receber(c, b.get('telefone'), b.get('texto'), 'web', b.get('nome'),
                                           sessao=b.get('sessao'))
        return 200, {'lead': lead, 'sessao': c.lead(lead['id'])['sessao'], 'respostas': respostas}
    m = re.fullmatch(r'/api/web/([\w-]+)', rota)
    if metodo == 'GET' and m:
        return 200, conversa.mensagens_web(c, m[1])
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
            return 200, conversa.apagar(c, m[1], b)

    # ---- gestor ----
    if rota == '/api/relogio' and metodo == 'POST':
        exigir_gestor(c, h)
        return 200, {'ok': True, 'agora': c.mudar_relogio(b.get('agora'))}
    if rota == '/api/tarefas/rodar' and metodo == 'POST':
        exigir_gestor(c, h)
        return 200, tarefas.rodar(c, forcar=True)
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
            if g:  # gestor por esta rota age como o colaborador indicado, sem a restrição da oferta
                return 200, chamados.assumir(c, ident, colab_do_corpo(c, b, q))
            return 200, chamados.assumir(c, ident, colab, restrito=True)
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


# ---------- segredos de exemplo (seção 1) ----------
LOCAIS = ('127.0.0.1', 'localhost', '::1')


def segredos_de_exemplo(app):
    """Texto do problema se o negocio.json ainda usa o token ou algum código do exemplo; senão None."""
    try:
        ex = json.loads((ROOT / 'exemplos' / 'negocio.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        ex = {}
    tokens = {'TROQUE-ESTE-TOKEN', str(ex.get('token_gestor') or 'TROQUE-ESTE-TOKEN')}
    if str(app.cfg.get('token_gestor', '')) in tokens:
        return 'token_gestor é o do exemplo'
    codigos = {str(m.get('codigo')) for m in ex.get('equipe', []) if m.get('codigo')}
    for m in app.cfg.get('equipe', []):
        if str(m.get('codigo')) in codigos:
            return f"o código de {m.get('id')} é o do exemplo"
    # Segredos dos webhooks: só valem se a integração está ligada.
    if evolution.configurado() and segredo_fraco(os.environ.get('WEBHOOK_SEGREDO')):
        return 'WEBHOOK_SEGREDO está vazio, curto (< 16 caracteres) ou é o do exemplo'
    if evolution.configurado() and 'troque' in (os.environ.get('EVOLUTION_API_KEY') or '').lower():
        return 'EVOLUTION_API_KEY é a do exemplo'
    # No modo polling o Telegram não chama o servidor: o segredo do webhook não é usado.
    if tg.configurado() and tg.modo() == 'webhook' and segredo_fraco(os.environ.get('TELEGRAM_SEGREDO')):
        return 'TELEGRAM_SEGREDO está vazio, curto (< 16 caracteres) ou é o do exemplo'
    return None


def segredo_fraco(valor):
    valor = (valor or '').strip()
    return len(valor) < 16 or 'troque' in valor.lower()


# ---------- entrega de webhook (HTTP ou polling do Telegram) ----------
def _painel(app):
    if app.sujo:
        equipe.atualizar_painel(app)


def entregar(app, origem, destino, b, junto=None):
    """Trata um update já lido (webhook ou getUpdates). `junto` roda na mesma transação (ex.: gravar o offset
    do polling), também quando o tratamento desiste e o update vai para `descartes`."""
    def tratar():
        destino(app, b)
        if junto:
            junto()
    if destino is bot.receber and isinstance(b, dict) and \
            isinstance((b.get('message') or {}).get('reply_to_message'), dict):
        saida.ocioso_tg(app)  # o reply precisa achar o message_id da mensagem que acabou de sair
    try:
        app.executar(tratar, depois=lambda: _painel(app))
        saida.aguardar(app, app.enfileirados())
    except Exception as e:
        log(f'webhook {origem}: ignorado: {type(e).__name__}: {e}')
        # Desistiu (ex.: 503 depois das tentativas, ou entrada que quebrou o tratamento): fica visível
        # em `descartes` no /gestor em vez de sumir no log.
        motivo = e.mensagem if isinstance(e, Erro) else f'erro ao tratar ({type(e).__name__})'
        detalhe = {'status': e.status} if isinstance(e, Erro) else {}
        if isinstance(b, dict):
            detalhe['id'] = ((b.get('data') or {}).get('key') or {}).get('id') \
                if isinstance(b.get('data'), dict) else b.get('update_id')

        def descartar():
            evolution.registrar_descarte(app, origem, motivo, detalhe)
            if junto:
                junto()
        try:
            app.executar(descartar)
        except Exception as e2:
            log(f'descartes: {type(e2).__name__}: {e2}')


# ---------- servidor ----------
def criar_handler(app):
    redes = redes_confiaveis()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        server_version = 'atende-leads'
        sys_version = ''
        timeout = 30  # cliente lento não segura a thread para sempre

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
            peer = self.client_address[0] if self.client_address else '?'
            ip = ip_cliente(peer, self.headers.get('X-Forwarded-For') or '', redes)
            app._local.ip = ip
            app._local.ip_publico = None
            app._local.abriu_publico = False
            if self.command == 'GET' and rota == '/api/saude':  # nunca espera o lock
                return self._json(200, saude(app))
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
                    # Chat web (público): limite de leads novos por IP e no total, de chamados por IP.
                    novo_web = cria_lead_web(self.command, rota, b)
                    if novo_web and not limite.checar_lead_web(ip):
                        raise Erro(429, limite.MSG_LEAD_WEB)
                    if rota_publica_de_chamado(self.command, rota, b):
                        app._local.ip_publico = ip
                    status, resposta = app.executar(
                        lambda: rotear(app, self.command, rota, q, b, self.headers), depois=self._painel)
                    if novo_web:
                        limite.contar_lead_web(ip)
                    if app._local.abriu_publico:
                        limite.contar_chamado_web(ip)
                    saida.aguardar(app, app.enfileirados())
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
            self._json(status, resposta)

        def _json(self, status, resposta):
            corpo = json.dumps(resposta, ensure_ascii=False).encode('utf-8')
            self._enviar(status, corpo, 'application/json')

        @staticmethod
        def _painel():
            _painel(app)

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
            entregar(app, rota.split('/')[2], destino, b)
            return 200, {'ok': True}

        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = processar

        def log_message(self, *args):
            pass

    return Handler


MAX_CONEXOES = 64


class Servidor(ThreadingHTTPServer):
    """Uma thread por conexão, no máximo `maximo` ao mesmo tempo; acima disso responde 503 e fecha.
    `GET /api/saude` fica fora do limite: com o servidor lotado, ele ainda responde (healthcheck)."""
    daemon_threads = True

    def __init__(self, endereco, handler, maximo=MAX_CONEXOES, saude=None):
        super().__init__(endereco, handler)
        self.vagas = threading.BoundedSemaphore(maximo)
        self.saude = saude

    def _pede_saude(self, request):
        """Espia (sem consumir) a 1ª linha do pedido, com prazo curto para não travar o accept."""
        if not self.saude:
            return False
        try:
            request.settimeout(0.5)
            inicio = request.recv(64, socket.MSG_PEEK)
        except OSError:
            return False
        return inicio.startswith((b'GET /api/saude ', b'GET /api/saude/ ', b'GET /api/saude?'))

    def process_request(self, request, client_address):
        if not self.vagas.acquire(blocking=False):
            try:
                if self._pede_saude(request):
                    corpo = json.dumps(self.saude(), ensure_ascii=False).encode('utf-8')
                    status = b'200 OK'
                else:
                    corpo = b'{"erro": "Servidor ocupado, tente de novo."}'
                    status = b'503 Service Unavailable'
                request.sendall(b'HTTP/1.1 %s\r\nContent-Type: application/json; charset=utf-8\r\n'
                                b'Content-Length: %d\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n%s'
                                % (status, len(corpo), corpo))
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.vagas.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.vagas.release()


def relogio_automatico(app, parar):
    def painel():
        if app.sujo:
            equipe.atualizar_painel(app)
    while not parar.wait(30):
        try:
            app.executar(lambda: tarefas.rodar(app), depois=painel)
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
    Path(a.dados).mkdir(parents=True, exist_ok=True)
    trava = backup.travar_servidor(a.dados)  # o `restaurar` recusa enquanto ela estiver presa
    if trava is None:
        p.exit(1, f'Já há um servidor rodando com {a.dados}.\n')
    app = App(a.dados)
    problema = segredos_de_exemplo(app)
    if problema and a.host not in LOCAIS and os.environ.get('ATENDE_PERMITIR_EXEMPLO') != '1':
        p.exit(2, f'Recusado: {problema} e o servidor escutaria em {a.host}. Rode ./instalar-vps.sh ou troque '
                  'os segredos (token_gestor e códigos da equipe em negocio.json; WEBHOOK_SEGREDO e '
                  'TELEGRAM_SEGREDO no .env, 16+ caracteres; EVOLUTION_API_KEY sem "troque"). '
                  'Só para teste/demonstração: '
                  'ATENDE_PERMITIR_EXEMPLO=1.\n')
    if problema:
        log(f'aviso: {problema} (aceito só em {a.host})')
    try:
        maximo = max(1, int(os.environ.get('ATENDE_MAX_CONEXOES') or MAX_CONEXOES))
    except ValueError:
        maximo = MAX_CONEXOES
    servidor = Servidor((a.host, a.porta), criar_handler(app), maximo, saude=lambda: saude(app))
    parar = threading.Event()
    despachantes = saida.iniciar(app)
    if not app.modo_teste:
        threading.Thread(target=relogio_automatico, args=(app, parar), daemon=True).start()
    leitor = None
    if tg.configurado() and tg.modo() == 'polling':  # também no modo ATENDE_AGORA
        leitor = polling.Leitor(app, lambda u, junto: entregar(app, 'telegram', bot.receber, u, junto)).iniciar()
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
        if leitor:
            leitor.encerrar()
        servidor.server_close()
        for d in despachantes:
            d.encerrar()
        time.sleep(0.05)
        app.fechar()
        trava.close()
