"""Testes de aceitação caixa-preta do atende-leads (contrato: docs/ESPECIFICACAO.md).

Sobem `./atende serve --porta 0 --dados <tmp>` com relógio fixo (ATENDE_AGORA) e falam só
HTTP/CLI. Evolution e Telegram são servidores falsos locais que gravam cada pedido.
Nenhum teste chama rede externa.
"""
import csv
import datetime as _dt
import io
import json
import os
import pathlib
import shutil
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "negocio.json"
TOKEN = "segredo-teste"
AGORA = "2026-11-09T10:00"  # segunda-feira, dentro do expediente 08–18
NEGOCIO = "Loja Teste"
URL_PUBLICA = "https://loja.exemplo.test"

CODIGOS = {"ana": "ana-1234-teste", "bruno": "bruno-5678-teste", "carla": "carla-9012-teste"}
NOMES = {"ana": "Ana", "bruno": "Bruno", "carla": "Carla"}
TG_ID = {"ana": 7001, "bruno": 7002, "carla": 7003}
GRUPO = -100555

TEL = "(41) 99999-0001"          # lead padrão
TEL_D = "5541999990001"
TEL_FMT = "+55 (41) 99999-0001"
TEL2 = "(41) 98888-7777"         # telefone "marcado" para checar privacidade
TEL2_D = "5541988887777"
TEL2_FMT = "+55 (41) 98888-7777"

SEGREDO_WH = "wh-segredo"
SEGREDO_TG = "tg-segredo"
TG_TOKEN = "TOKEN123"
INSTANCIA = "loja"
APIKEY = "chave-evo"


# ----------------------------------------------------------------- utilidades

def mais(agora, minutos=0, dias=0):
    t = _dt.datetime.strptime(agora, "%Y-%m-%dT%H:%M") + _dt.timedelta(minutes=minutos, days=dias)
    return t.strftime("%Y-%m-%dT%H:%M")


def esperar(cond, timeout=3):
    """Polling curto: o contrato não diz que envios ao Telegram/Evolution são síncronos."""
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.05)
    try:
        return bool(cond())
    except Exception:
        return False


def buscar(obj, pred):
    """Todos os dicts (em qualquer profundidade) que satisfazem pred."""
    achados = []
    if isinstance(obj, dict):
        try:
            if pred(obj):
                achados.append(obj)
        except Exception:
            pass
        for v in obj.values():
            achados += buscar(v, pred)
    elif isinstance(obj, list):
        for v in obj:
            achados += buscar(v, pred)
    return achados


def eh_chamado(d):
    return "motivo" in d and "prioridade" in d and "status" in d


def lista(corpo, *chaves):
    """Aceita lista pura ou objeto que embrulha a lista (formato não fixado no contrato)."""
    if isinstance(corpo, list):
        return corpo
    if isinstance(corpo, dict):
        for k in chaves + ("mensagens", "saida", "itens", "leads", "dados", "lista"):
            if isinstance(corpo.get(k), list):
                return corpo[k]
        for v in corpo.values():
            if isinstance(v, list):
                return v
    raise AssertionError(f"esperava lista, veio {corpo!r}"[:300])


def ok(st):
    return st in (200, 201)


# ----------------------------------------------------------------- cliente HTTP

class Cliente:
    def __init__(self, base, agora=AGORA):
        self.base = base
        self.agora = agora

    def req(self, metodo, rota, corpo=None, token=TOKEN, codigo=None, headers=None, bruto=False):
        dados = None if corpo is None else (corpo if isinstance(corpo, bytes) else json.dumps(corpo).encode())
        r = urllib.request.Request(self.base + rota, data=dados, method=metodo)
        if dados is not None:
            r.add_header("Content-Type", "application/json")
        if codigo:
            r.add_header("X-Codigo", codigo)
        elif token:
            r.add_header("X-Token", token)
        for k, v in (headers or {}).items():
            r.add_header(k, v)
        try:
            with urllib.request.urlopen(r, timeout=15) as resp:
                b = resp.read()
                self.ultimo_tipo = resp.headers.get("Content-Type", "")
                if bruto:
                    return resp.status, b
                texto = b.decode("utf-8", "replace")
                if "json" in self.ultimo_tipo:
                    try:
                        return resp.status, json.loads(texto)
                    except ValueError:
                        return resp.status, texto
                return resp.status, texto
        except urllib.error.HTTPError as e:
            texto = e.read().decode("utf-8", "replace")
            self.ultimo_tipo = e.headers.get("Content-Type", "") if e.headers else ""
            try:
                return e.code, json.loads(texto)
            except ValueError:
                return e.code, texto

    def get(self, rota, **kw):
        return self.req("GET", rota, **kw)

    def post(self, rota, corpo=None, **kw):
        return self.req("POST", rota, {} if corpo is None else corpo, **kw)

    def put(self, rota, corpo=None, **kw):
        return self.req("PUT", rota, {} if corpo is None else corpo, **kw)

    # ---- conversa
    def msg_full(self, telefone=TEL, texto="oi", nome=None, canal="whatsapp"):
        corpo = {"telefone": telefone, "texto": texto, "canal": canal}
        if nome:
            corpo["nome"] = nome
        # §4: canal "whatsapp" por esta rota é a simulação do WhatsApp e exige [G]; o web é público (sessão).
        st, r = self.post("/api/mensagens", corpo, token=TOKEN if canal == "whatsapp" else None)
        assert st == 200, (st, r)
        assert isinstance(r.get("respostas"), list), r
        return r

    def msg(self, telefone=TEL, texto="oi", nome=None, canal="whatsapp"):
        return "\n".join(self.msg_full(telefone, texto, nome, canal)["respostas"])

    # ---- tempo
    def relogio(self, agora):
        st, r = self.post("/api/relogio", {"agora": agora})
        assert ok(st), (st, r)
        self.agora = agora

    def rodar(self):
        st, r = self.post("/api/tarefas/rodar")
        assert st == 200, (st, r)
        return r

    def avancar(self, minutos=0, dias=0, para=None):
        self.relogio(para or mais(self.agora, minutos, dias))
        return self.rodar()

    # ---- equipe
    def status(self, cid, st_novo):
        st, r = self.post("/api/equipe/status", {"status": st_novo}, codigo=CODIGOS[cid])
        assert ok(st), (cid, st_novo, st, r)
        return r

    def eu(self, cid):
        st, r = self.get("/api/equipe/eu", codigo=CODIGOS[cid])
        assert st == 200, (st, r)
        return r

    def painel(self):
        st, r = self.get("/api/painel")
        assert st == 200, (st, r)
        return r

    def fila(self):
        return self.painel()["fila"]

    def colab(self, cid):
        return next(c for c in self.painel()["equipe"] if c["id"] == cid)

    # ---- chamados
    def ficha(self, lead_id):
        st, r = self.get(f"/api/gestor/leads/{lead_id}")
        assert st == 200, (st, r)
        return r

    def chamados_do_lead(self, lead_id):
        vistos, saida = set(), []
        for c in buscar(self.ficha(lead_id), eh_chamado):
            if "id" in c and str(c["id"]) not in vistos:
                vistos.add(str(c["id"]))
                saida.append(c)
        return saida

    def chamado_aberto(self, lead_id):
        abertos = [c for c in self.chamados_do_lead(lead_id) if c.get("status") != "fechado"]
        assert abertos, f"lead {lead_id} sem chamado aberto: {self.chamados_do_lead(lead_id)}"
        return abertos[-1]

    def abrir(self, telefone=TEL, nome="Maria Souza", texto="quero falar com um atendente"):
        """Abre chamado (pediu_humano) e devolve (lead, id do chamado)."""
        r = self.msg_full(telefone, texto, nome=nome)
        lead = r["lead"]
        return lead, self.chamado_aberto(lead["id"])["id"]

    def assumir(self, cid, chamado):
        return self.post(f"/api/equipe/chamados/{chamado}/assumir", codigo=CODIGOS[cid])

    def fechar(self, cid, chamado, corpo):
        return self.post(f"/api/equipe/chamados/{chamado}/fechar", corpo, codigo=CODIGOS[cid])

    def atendendo(self, cid="ana", telefone=TEL, nome="Maria Souza"):
        """Chamado aberto, ofertado a cid e assumido por ele (cid precisa estar livre/1º da vez)."""
        lead, ch = self.abrir(telefone, nome)
        st, r = self.assumir(cid, ch)
        assert ok(st), (st, r)
        return lead, ch

    # ---- saída
    def saida(self):
        st, r = self.get("/api/saida")
        assert st == 200, (st, r)
        return lista(r)

    def saida_para(self, digitos):
        return [m for m in self.saida() if str(m.get("telefone", "")).endswith(digitos[-8:])]

    def textos_para(self, digitos):
        return "\n".join(str(m.get("texto", "")) for m in self.saida_para(digitos))

    # ---- csv
    def csv(self):
        st, b = self.get("/api/gestor/exportar.csv", bruto=True)
        assert st == 200, st
        texto = b.decode("utf-8").lstrip("﻿")
        return texto, list(csv.DictReader(io.StringIO(texto)))

    def lead_csv(self, lead_id):
        linhas = [l for l in self.csv()[1] if str(l.get("lead_id")) == str(lead_id)]
        assert linhas, f"lead {lead_id} não está no CSV"
        return linhas[-1]


def equipe_pronta(api, tg=None, quem=("ana", "bruno", "carla")):
    """Vincula (se houver Telegram) e põe cada um livre em minutos escalonados: ordem de vez = quem."""
    if tg is not None:
        for cid in quem:
            tg.entrar(cid)
    for i, cid in enumerate(quem):
        if i:
            api.relogio(mais(api.agora, 1))
        api.status(cid, "livre")


# ----------------------------------------------------------------- servidor

SERVIDORES = []


@pytest.fixture(autouse=True)
def _parar_servidores():
    yield
    while SERVIDORES:
        SERVIDORES.pop().parar()


class Servidor:
    def __init__(self, dados, agora=AGORA, env=None):
        SERVIDORES.append(self)  # o teardown autouse para todos, mesmo se o teste falhar
        self.dados = dados
        self.agora = agora
        self.env = env or {}
        self.proc = None

    def subir(self):
        exe = RAIZ / "atende"
        if not exe.exists():
            pytest.fail("./atende não existe (ponto de entrada da seção 1 da especificação)")
        prefixos = ("EVOLUTION_", "TELEGRAM_", "WEBHOOK_", "CEREBRO_", "ATENDE_", "WHISPER_")
        env = {k: v for k, v in os.environ.items() if not k.startswith(prefixos)}
        if self.agora:
            env["ATENDE_AGORA"] = self.agora
        env.update(self.env)
        self.proc = subprocess.Popen(
            [str(exe), "serve", "--porta", "0", "--dados", str(self.dados)],
            cwd=RAIZ, env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        )
        linha = {}

        def ler():
            linha["v"] = self.proc.stdout.readline()

        t = threading.Thread(target=ler, daemon=True)
        t.start()
        t.join(15)
        primeira = (linha.get("v") or "").strip()
        if not primeira.startswith("PORTA="):
            self.parar()
            pytest.fail(f"servidor não imprimiu PORTA=<n> na 1ª linha (veio {primeira!r})")
        threading.Thread(target=lambda: [None for _ in self.proc.stdout], daemon=True).start()
        self.porta = int(primeira.split("=", 1)[1])
        return Cliente(f"http://127.0.0.1:{self.porta}", agora=self.agora or AGORA)

    def parar(self):
        if self.proc and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGTERM)
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(5)


@pytest.fixture
def dados(tmp_path):
    d = tmp_path / "dados"
    d.mkdir()
    shutil.copy(FIXTURE, d / "negocio.json")
    return d


@pytest.fixture
def servidor(dados):
    return Servidor(dados)


@pytest.fixture
def api(servidor):
    """Servidor sem integrações (sem Telegram: oferta fica só no painel web)."""
    return servidor.subir()


# ----------------------------------------------------------------- externos falsos

class Externo:
    """Faz o papel da Evolution API e da API do Telegram. Grava cada pedido."""

    def __init__(self):
        import http.server
        self.pedidos = []
        self.falhas = 0            # próximos N pedidos (qualquer rota) devolvem 500
        self.falhar_metodo = {}    # método Telegram -> N próximas respostas com erro 400
        self.respostas = {}        # método Telegram -> lista de (status, corpo json) devolvidas antes das normais
        self.prox_msg = 1000
        self.pendurar = False      # True: aceita a conexão e não responde (API pendurada)
        self.solta = threading.Event()
        self.trava = threading.Lock()
        externo = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                corpo = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                if externo.pendurar:
                    with externo.trava:
                        externo.pedidos.append({"rota": self.path, "metodo": "PENDURADO", "headers": {},
                                                "json": {}, "status": 0})
                    externo.solta.wait(30)
                    return
                try:
                    dados = json.loads(corpo or b"{}")
                except ValueError:
                    dados = {}
                metodo = self.path.rstrip("/").rsplit("/", 1)[-1]
                pedido = {"rota": self.path, "metodo": metodo,
                          "headers": {k.lower(): v for k, v in self.headers.items()}, "json": dados}
                with externo.trava:
                    if externo.falhas > 0:
                        externo.falhas -= 1
                        pedido["status"] = 500
                        externo.pedidos.append(pedido)
                        self.send_response(500)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if externo.respostas.get(metodo):
                        st, resp = externo.respostas[metodo].pop(0)
                        pedido["status"] = st
                        externo.pedidos.append(pedido)
                        b = json.dumps(resp).encode()
                        self.send_response(st)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                        return
                    if externo.falhar_metodo.get(metodo, 0) > 0:
                        externo.falhar_metodo[metodo] -= 1
                        pedido["status"] = 400
                        externo.pedidos.append(pedido)
                        b = json.dumps({"ok": False, "error_code": 400,
                                        "description": "Bad Request: message to edit not found"}).encode()
                        self.send_response(400)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(b)))
                        self.end_headers()
                        self.wfile.write(b)
                        return
                    externo.prox_msg += 1
                    pedido["status"], pedido["message_id"] = 200, externo.prox_msg
                    externo.pedidos.append(pedido)
                resp = {"ok": True, "result": {"message_id": pedido["message_id"]},
                        "key": {"id": f"X{pedido['message_id']}"}}
                b = json.dumps(resp).encode()
                self.send_response(201 if "/message/" in self.path else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)

            def log_message(self, *a):
                pass

        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    # ---- Evolution
    def whats(self, ok=True):
        with self.trava:
            ps = list(self.pedidos)
        return [p for p in ps if p["rota"] == f"/message/sendText/{INSTANCIA}" and (not ok or p["status"] == 200)]

    def whats_texto(self, digitos=None):
        return "\n".join(str(p["json"].get("text", "")) for p in self.whats()
                         if digitos is None or str(p["json"].get("number", "")).endswith(digitos[-8:]))

    # ---- Telegram
    def tg(self, metodo=None, chat=None, todos=False):
        with self.trava:
            ps = list(self.pedidos)
        out = []
        for p in ps:
            if not p["rota"].startswith(f"/bot{TG_TOKEN}/"):
                continue
            if not todos and p["status"] != 200:
                continue
            if metodo and p["metodo"] != metodo:
                continue
            if chat is not None and str(p["json"].get("chat_id")) != str(chat):
                continue
            out.append(p)
        return out

    def enviadas(self, chat):
        return self.tg("sendMessage", chat)

    def privado(self, cid):
        return self.enviadas(TG_ID[cid])

    def grupo(self):
        """sendMessage + editMessageText ao grupo."""
        return [p for p in self.tg(chat=GRUPO) if p["metodo"] in ("sendMessage", "editMessageText")]

    def textos(self, pedidos):
        return "\n".join(str(p["json"].get("text", "")) for p in pedidos)

    def com_texto(self, pedidos, trecho):
        return [p for p in pedidos if trecho in str(p["json"].get("text", ""))]

    def quieto(self, janela=0.3, teto=3):
        """Espera os envios assíncronos assentarem (nenhum pedido novo por `janela` s)."""
        fim = time.time() + teto
        n = -1
        while time.time() < fim:
            with self.trava:
                atual = len(self.pedidos)
            if atual == n:
                return
            n = atual
            time.sleep(janela)

    def fechar(self):
        self.solta.set()
        self.srv.shutdown()
        self.srv.server_close()


def botoes(pedido):
    rm = pedido["json"].get("reply_markup") or {}
    if isinstance(rm, str):
        try:
            rm = json.loads(rm)
        except ValueError:
            return []
    return [b for linha in rm.get("inline_keyboard", []) for b in linha]


def callbacks(pedido):
    return [b.get("callback_data", "") for b in botoes(pedido)]


def urls(pedido):
    return [b.get("url", "") for b in botoes(pedido) if b.get("url")]


def env_integracoes(externo):
    return {
        "EVOLUTION_URL": externo.url, "EVOLUTION_API_KEY": APIKEY, "EVOLUTION_INSTANCIA": INSTANCIA,
        "WEBHOOK_SEGREDO": SEGREDO_WH,
        "TELEGRAM_API_URL": externo.url, "TELEGRAM_TOKEN": TG_TOKEN, "TELEGRAM_GRUPO_ID": str(GRUPO),
        "TELEGRAM_SEGREDO": SEGREDO_TG,
    }


@pytest.fixture
def externo():
    e = Externo()
    yield e
    e.fechar()


@pytest.fixture
def servidor_int(dados, externo):
    return Servidor(dados, env=env_integracoes(externo))


@pytest.fixture
def api_int(servidor_int):
    """Servidor com Evolution e Telegram apontando para o falso local."""
    return servidor_int.subir()


class Tg:
    """Manda updates ao webhook do Telegram do sistema, como o Telegram faria."""

    def __init__(self, api):
        self.api = api
        self.n = 0

    def update(self, corpo, segredo=SEGREDO_TG):
        self.n += 1
        corpo = dict(corpo, update_id=900000 + self.n)
        h = {"X-Telegram-Bot-Api-Secret-Token": segredo} if segredo else {}
        return self.api.post("/webhook/telegram", corpo, token=None, headers=h)

    def msg(self, from_id, texto, chat_id=None, reply_to=None, extra=None):
        chat_id = from_id if chat_id is None else chat_id
        m = {"message_id": 50000 + self.n, "date": 1700000000 + self.n,
             "from": {"id": from_id, "is_bot": False, "first_name": "X"},
             "chat": {"id": chat_id, "type": "private" if chat_id == from_id else "supergroup"}}
        if texto is not None:
            m["text"] = texto
        if reply_to is not None:
            m["reply_to_message"] = {"message_id": reply_to, "chat": {"id": chat_id}, "text": ""}
        if extra:
            m.update(extra)
        st, r = self.update({"message": m})
        assert st == 200, (st, r)
        return st, r

    def cb(self, from_id, data, message_id=1, chat_id=None):
        chat_id = from_id if chat_id is None else chat_id
        cbid = f"cb{self.n + 1}"
        st, r = self.update({"callback_query": {
            "id": cbid, "from": {"id": from_id, "is_bot": False, "first_name": "X"}, "data": data,
            "message": {"message_id": message_id, "chat": {"id": chat_id}, "text": ""}}})
        assert st == 200, (st, r)
        return cbid

    def entrar(self, cid):
        return self.msg(TG_ID[cid], f"/entrar {CODIGOS[cid]}")


@pytest.fixture
def tg(api_int):
    return Tg(api_int)
