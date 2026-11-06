"""1.7.8 — seção 13c: gerar base a partir de link ou arquivo. Site falso local (com link para outro domínio,
redirecionamento para endereço interno, página grande e robots.txt), DOCX montado aqui com zipfile, PDF por um
cérebro falso que recebe o bloco `document`. Nenhum site real nem API real."""
import base64
import io
import json
import os
import sqlite3
import sys
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from conftest import RAIZ, Servidor, esperar
from falsos import FalsoLLM, cfg_cerebro

sys.path.insert(0, str(RAIZ))
from src import fontes as F  # noqa: E402  (funções puras: SSRF, HTML, DOCX, horários)

CURADORIA = {"tipo": "anthropic", "modelo": "claude-opus-5-5", "esforco": "medium"}
UA = "atende-leads (+https://loja.exemplo.test)"


class Site:
    """Servidor HTTP falso: `paginas[path] = (status, headers, corpo)`; grava (path, User-Agent) de cada pedido."""

    def __init__(self):
        self.paginas, self.pedidos = {}, []
        dono = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                dono.pedidos.append((self.path, self.headers.get("User-Agent")))
                st, cab, corpo = dono.paginas.get(self.path, (404, {}, b"nada"))
                corpo = corpo.encode() if isinstance(corpo, str) else corpo
                self.send_response(st)
                cab = {"Content-Type": "text/html; charset=utf-8", **cab}
                for k, v in cab.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                try:
                    self.wfile.write(corpo)
                except OSError:
                    pass

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.porta = self.srv.server_address[1]
        self.url = f"http://127.0.0.1:{self.porta}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def caminhos(self):
        return [p for p, _ua in self.pedidos]

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def sites():
    a, b = Site(), Site()  # b = "rede interna": ninguém pode chegar nele
    yield a, b
    a.fechar()
    b.fechar()


def montar_site(a, b):
    a.paginas["/robots.txt"] = (200, {"Content-Type": "text/plain"}, "User-agent: *\nDisallow: /privado\n")
    a.paginas["/"] = (200, {}, f"""<!doctype html><html><head><title>Padaria Exemplo</title>
<script>var x = "NAO-DEVE-APARECER";</script><style>.a{{color:red}}</style></head><body>
<nav><a href="/contato">Contato</a> <a href="/cardapio#topo">Cardápio</a> menu-secreto</nav>
<h1>Padaria Exemplo</h1><p>Pães artesanais desde 1990.</p>
<ul><li>Pão francês</li><li>Pão de queijo</li></ul>
<a href="/privado/x">área</a> <a href="http://localhost:{a.porta}/fora">fora</a>
<a href="/redir-interno">r</a> <a href="/grande">g</a> <a href="/foto.jpg">foto</a>
<footer>rodape-secreto</footer></body></html>""")
    a.paginas["/cardapio"] = (200, {}, """<html><body><h2>Cardápio</h2><table>
<tr><th>Item</th><th>Preço</th></tr><tr><td>Bolo de cenoura</td><td>R$ 25,00</td></tr>
<tr><td>Plano anual</td><td>R$ 999</td></tr></table></body></html>""")
    a.paginas["/contato"] = (200, {}, """<html><body><h2>Contato</h2>
<p>Telefone: (41) 3333-4444</p><p>E-mail: contato@padaria.test</p>
<p>Endereço: Rua das Flores, 123 - Centro, Curitiba - PR, CEP 80000-000</p>
<p>Segunda a sexta, das 7h às 19h</p><p>Sábado, das 8h às 12h</p></body></html>""")
    a.paginas["/privado/x"] = (200, {}, "<p>não podia ler</p>")
    a.paginas["/fora"] = (200, {}, "<p>outro domínio</p>")
    a.paginas["/redir-interno"] = (302, {"Location": f"{b.url}/alvo"}, "")
    a.paginas["/grande"] = (200, {}, "<p>" + "x" * (2 * 1024 * 1024 + 10) + "</p>")
    b.paginas["/alvo"] = (200, {}, "<p>segredo interno</p>")


def subir(dados, site, llm=None, extra=None):
    env = {"ATENDE_FONTE_PERMITIR_LOCAL": f"127.0.0.1:{site.porta}"}
    if llm:
        env.update({"CEREBRO_API_KEY": "sk-falsa-teste", "CEREBRO_ANTHROPIC_URL": llm.url + "/v1/messages"})
    env.update(extra or {})
    return Servidor(dados, env=env).subir()


def esperar_fonte(api, fid, timeout=20):
    def pronto():
        st, r = api.get("/api/gestor/base/fontes")
        f = next(x for x in r["fontes"] if x["id"] == fid)
        return f if f["status"] in ("pronto", "erro") else None
    assert esperar(pronto, timeout), "a fonte não terminou"
    return pronto()


def propostas_da(api, fid):
    st, ps = api.get("/api/gestor/propostas?status=nova")
    assert st == 200, ps
    return [p for p in ps if p.get("fonte_id") == fid]


# ------------------------------------------------------------------ link: BFS, SSRF, robots, limites, regras
def test_link_mesmo_dominio_ssrf_robots_limites_e_propostas_por_regras(dados, sites):
    a, b = sites
    montar_site(a, b)
    api = subir(dados, a)
    st, r = api.post("/api/gestor/base/fonte", {"url": a.url + "/", "max_paginas": 20})
    assert st == 200, r
    assert r["fonte"]["status"] == "lendo"
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "pronto", f
    caminhos = a.caminhos()
    assert "/" in caminhos and "/cardapio" in caminhos and "/contato" in caminhos
    assert "/privado/x" not in caminhos                       # robots.txt: Disallow para *
    assert "/fora" not in caminhos                            # outro domínio (localhost ≠ 127.0.0.1): não segue
    assert "/foto.jpg" not in caminhos
    assert b.pedidos == []                                    # redirecionamento para endereço interno: recusado
    assert caminhos.count("/cardapio") == 1                   # #fragmento não repete a página
    assert all(ua == UA for _p, ua in a.pedidos)              # User-Agent atende-leads (+url_publica)
    avisos = " ".join(f["avisos"])
    assert "redir-interno" in avisos and "interno" in avisos
    assert "/grande" in avisos and "2 MB" in avisos
    assert f["paginas"] == 3 and f["caracteres"] > 50
    ps = propostas_da(api, f["id"])
    assert f["propostas"] == len(ps) > 0
    assert all(p["origem"] == "fonte" and p["fonte"].startswith(a.url) and p["evidencia"] for p in ps)
    por = {(p["tipo"], p.get("campo") or p.get("produto_id") or p.get("nome")): p for p in ps}
    end = por[("info", "endereco")]
    assert "CEP 80000-000" in end["resposta"] and end["fonte"] == a.url + "/contato"
    assert any(p["tipo"] == "info" and p["campo"] == "observacoes" and "(41) 3333-4444" in p["resposta"] for p in ps)
    assert any(p["tipo"] == "info" and "contato@padaria.test" in p["resposta"] for p in ps)
    preco = por[("preco", "plano-anual")]
    assert preco["preco_novo"] == "R$ 999" and preco["contradiz"] is True and "Plano anual" in preco["evidencia"]
    assert por[("produto", "Bolo de cenoura")]["preco_novo"] == "R$ 25,00"
    hor = next(p for p in ps if p["tipo"] == "horario")
    assert hor["horarios"]["seg"] == [["07:00", "19:00"]] and hor["horarios"]["sex"] == [["07:00", "19:00"]]
    assert hor["horarios"]["sab"] == [["08:00", "12:00"]] and hor["contradiz"] is True
    tudo = json.dumps(ps, ensure_ascii=False)
    assert "NAO-DEVE-APARECER" not in tudo and "rodape-secreto" not in tudo and "menu-secreto" not in tudo
    # a lista do Aprendizado mostra a fonte e a evidência; o destino estruturado continua ("Vai alterar")
    assert "Cadastros → Produtos → Plano anual" in preco["destino"]


def test_limite_de_paginas_e_validacao(dados, sites):
    a, b = sites
    montar_site(a, b)
    api = subir(dados, a)
    st, r = api.post("/api/gestor/base/fonte", {"url": a.url + "/", "max_paginas": 2})
    assert st == 200, r
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "pronto" and f["paginas"] == 2
    paginas = [p for p in a.caminhos() if p != "/robots.txt"]
    assert len(paginas) == 2, paginas
    for corpo in ({"url": a.url, "max_paginas": 0}, {"url": a.url, "max_paginas": 21}, {"url": a.url, "max_paginas": "8"},
                  {"url": "ftp://exemplo.test/"}, {"url": "http://usuario:senha@exemplo.test/"}, {"url": ""},
                  {"url": "http://10.0.0.5/"}, {"url": "http://169.254.169.254/latest/meta-data"},
                  {"url": "http://[::1]:80/"}):
        st, r = api.post("/api/gestor/base/fonte", corpo)
        assert st == 422, (corpo, st, r)
    st, r = api.post("/api/gestor/base/fonte", {"url": a.url + "/"}, token="errado")
    assert st == 401


def test_sem_liberacao_local_o_proprio_host_local_e_recusado(dados, sites):
    a, b = sites
    montar_site(a, b)
    api = Servidor(dados).subir()  # sem ATENDE_FONTE_PERMITIR_LOCAL (como em produção)
    st, r = api.post("/api/gestor/base/fonte", {"url": a.url + "/"})
    assert st == 422 and "interno" in r["erro"], r
    st, r = api.post("/api/gestor/base/fonte", {"url": f"http://localhost:{a.porta}/"})  # nome que resolve p/ loopback
    assert st == 200, r
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "erro" and "interno" in f["erro"], f
    assert a.pedidos == []


def test_ssrf_e_extracao_funcoes_puras(monkeypatch):
    monkeypatch.delenv("ATENDE_FONTE_PERMITIR_LOCAL", raising=False)
    import ipaddress
    for ip in ("127.0.0.1", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254", "100.64.0.1", "0.0.0.0",
               "::1", "fe80::1", "::ffff:127.0.0.1", "240.0.0.1"):
        assert F.ip_proibido(ipaddress.ip_address(ip)), ip
    assert not F.ip_proibido(ipaddress.ip_address("8.8.8.8"))
    with pytest.raises(F.Recusado):
        F.resolver("localhost", 80)
    with pytest.raises(F.Recusado):
        F.checar_url("file:///etc/passwd")
    monkeypatch.setenv("ATENDE_FONTE_PERMITIR_LOCAL", "127.0.0.1:5555")
    assert F.resolver("127.0.0.1", 5555) == "127.0.0.1"
    with pytest.raises(F.Recusado):
        F.resolver("127.0.0.1", 5556)                         # só o host:porta liberado
    texto, links = F.extrair_html("<html><head><title>Loja</title><style>x{}</style></head><body><nav>menu</nav>"
                                  "<h2>Preços</h2><ul><li>Pão R$ 1,00</li></ul><table><tr><td>Bolo</td><td>R$ 25</td>"
                                  "</tr></table><script>oculto()</script><footer>rodapé</footer>"
                                  "<a href='/x'>x</a></body></html>")
    assert texto.splitlines()[0] == "# Loja"
    assert "## Preços" in texto and "- Pão R$ 1,00" in texto and "Bolo | R$ 25" in texto
    assert "menu" not in texto and "oculto" not in texto and "rodapé" not in texto
    assert links == ["/x"]
    assert F.horarios_de_texto("seg a sex 08:00-18:00; sab 09:00-13:00; dom fechado") == {
        "seg": [["08:00", "18:00"]], "ter": [["08:00", "18:00"]], "qua": [["08:00", "18:00"]],
        "qui": [["08:00", "18:00"]], "sex": [["08:00", "18:00"]], "sab": [["09:00", "13:00"]], "dom": []}


# ------------------------------------------------------------------ arquivos
def docx(paragrafos, tabela=()):
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ps = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragrafos)
    tb = ("<w:tbl>" + "".join("<w:tr>" + "".join(f"<w:tc><w:p><w:r><w:t>{c}</w:t></w:r></w:p></w:tc>" for c in linha)
                              + "</w:tr>" for linha in tabela) + "</w:tbl>") if tabela else ""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("word/document.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:document {w}><w:body>{ps}{tb}</w:body></w:document>')
    return buf.getvalue()


def b64(dados):
    return base64.b64encode(dados).decode()


@pytest.fixture
def llm():
    f = FalsoLLM()
    f.saida = {"propostas": []}
    f.texto = lambda corpo: json.dumps(f.saida, ensure_ascii=False)
    yield f
    f.fechar()


def chamadas_curadoria(llm):
    return [p["json"] for p in llm.lista() if "montar a base de conhecimento" in p["json"]["system"][0]["text"]]


def test_docx_pela_curadoria_com_fonte_evidencia_bastidor_e_repeticao(dados, sites, llm):
    a, _b = sites
    api = subir(dados, a, llm)
    cfg_cerebro(api, {"tipo": "regras"}, extra={"cerebro_curadoria": CURADORIA})
    llm.saida = {"propostas": [
        {"tipo": "info", "campo": "entrega", "resposta": "Entregamos em toda Curitiba.", "fonte": "cardapio.docx",
         "evidencia": "Entregamos em toda Curitiba", "justificativa": "o documento cita", "contradiz": False},
        {"tipo": "produto", "nome": "Combo família", "palavras": ["combo"], "preco_novo": "R$ 89,90",
         "fonte": "cardapio.docx", "evidencia": "Combo família | R$ 89,90", "justificativa": "", "contradiz": False},
        {"tipo": "info", "campo": "observacoes", "resposta": "A base diz outra coisa; confirmar com a equipe.",
         "fonte": "cardapio.docx", "evidencia": "x", "justificativa": "", "contradiz": True},     # bastidor → fora
        {"tipo": "faq", "perguntas": ["onde fica a loja"], "resposta": "Na Rua X.", "fonte": "cardapio.docx",
         "evidencia": "x", "justificativa": "", "contradiz": False},                            # já no FAQ → fora
        {"tipo": "preco", "produto_id": "plano-anual", "preco_novo": "R$ 1.200", "fonte": "cardapio.docx",
         "evidencia": "x", "justificativa": "", "contradiz": False},                            # igual à base → fora
        {"tipo": "preco", "produto_id": "nao-existe", "preco_novo": "R$ 5", "fonte": "?", "evidencia": "x",
         "justificativa": "", "contradiz": False}]}                                             # produto inválido
    arq = docx(["Entregamos em toda Curitiba.", "Pedidos pelo WhatsApp."], [["Combo família", "R$ 89,90"]])
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "cardapio.docx", "conteudo_base64": b64(arq)})
    assert st == 200, r
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "pronto", f
    ch = chamadas_curadoria(llm)
    assert len(ch) == 1
    corpo = ch[0]
    assert corpo["model"] == "claude-opus-5-5" and corpo["max_tokens"] == 4096
    assert corpo["output_config"]["format"]["type"] == "json_schema"
    assert "propostas" in corpo["output_config"]["format"]["schema"]["properties"]
    usuario = corpo["messages"][0]["content"]
    assert "=== Fonte: cardapio.docx ===" in usuario and "Combo família | R$ 89,90" in usuario
    assert "Base de conhecimento" in corpo["system"][1]["text"] and "Plano anual" in corpo["system"][1]["text"]
    ps = propostas_da(api, f["id"])
    assert sorted(p["tipo"] for p in ps) == ["info", "produto"]
    assert all(p["fonte"] == "cardapio.docx" and p["evidencia"] for p in ps)
    assert f["propostas"] == 2
    # nada do arquivo fica guardado além das propostas: a tabela de fontes só tem metadados
    db = sqlite3.connect(dados / "leads.db")
    linha = db.execute("SELECT * FROM fontes WHERE id=?", (f["id"],)).fetchone()
    db.close()
    assert "Pedidos pelo WhatsApp" not in json.dumps(linha, ensure_ascii=False)
    assert not [x for x in os.listdir(dados) if x.endswith(".docx")]


def test_pdf_vai_como_bloco_document_para_a_curadoria_anthropic(dados, sites, llm):
    a, _b = sites
    api = subir(dados, a, llm)
    cfg_cerebro(api, {"tipo": "regras"}, extra={"cerebro_curadoria": CURADORIA})
    llm.saida = {"propostas": [{"tipo": "info", "campo": "garantia", "resposta": "Garantia de 90 dias.",
                                "fonte": "politica.pdf", "evidencia": "garantia de 90 dias", "justificativa": "",
                                "contradiz": False}]}
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "politica.pdf", "conteudo_base64": b64(pdf)})
    assert st == 200, r
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "pronto", f
    corpo = chamadas_curadoria(llm)[0]
    blocos = corpo["messages"][0]["content"]
    assert isinstance(blocos, list) and blocos[0]["type"] == "document"
    assert blocos[0]["source"] == {"type": "base64", "media_type": "application/pdf", "data": b64(pdf)}
    assert blocos[1]["type"] == "text"
    ps = propostas_da(api, f["id"])
    assert len(ps) == 1 and ps[0]["campo"] == "garantia" and ps[0]["fonte"] == "politica.pdf"


def test_pdf_sem_anthropic_nem_pdftotext_422_e_limites_do_arquivo(dados, sites):
    a, _b = sites
    api = subir(dados, a, extra={"ATENDE_PDFTOTEXT_BIN": "/nao/existe/pdftotext"})
    pdf = b"%PDF-1.4\n%%EOF\n"
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "x.pdf", "conteudo_base64": b64(pdf)})
    assert st == 422 and "PDF precisa do cérebro Anthropic ou do pdftotext" in r["erro"], r
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "x.exe", "conteudo_base64": b64(b"MZ")})
    assert st == 422
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "x.txt", "conteudo_base64": "@@@"})
    assert st == 422
    grande = b64(b"a" * (10 * 1024 * 1024 + 1))
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "grande.txt", "conteudo_base64": grande})
    assert st == 413, (st, r)
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "ruim.docx", "conteudo_base64": b64(b"PK nada")})
    assert st == 200
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "erro" and "DOCX" in f["erro"]


def test_texto_longo_em_blocos_com_deduplicacao(dados, sites, llm):
    a, _b = sites
    api = subir(dados, a, llm)
    cfg_cerebro(api, {"tipo": "regras"}, extra={"cerebro_curadoria": CURADORIA})
    llm.saida = {"propostas": [{"tipo": "faq", "perguntas": ["vocês abrem no feriado?"],
                                "resposta": "Abrimos nos feriados das 9h às 13h.", "fonte": "longo.md",
                                "evidencia": "feriados das 9h às 13h", "justificativa": "", "contradiz": False}]}
    texto = "\n".join(f"Linha {i}: abrimos nos feriados das 9h às 13h e temos pães de fermentação natural." for i in range(600))
    assert len(texto) > 40000
    st, r = api.post("/api/gestor/base/arquivo", {"nome": "longo.md", "conteudo_base64": b64(texto.encode())})
    f = esperar_fonte(api, r["fonte"]["id"])
    assert f["status"] == "pronto", f
    ch = chamadas_curadoria(llm)
    assert len(ch) >= 3
    assert all(len(c["messages"][0]["content"]) < 20000 for c in ch)
    assert "bloco 1 de" in ch[0]["messages"][0]["content"]
    assert len(propostas_da(api, f["id"])) == 1                # mesma proposta em todos os blocos → uma só


def test_incorporar_selecionadas_em_lote(dados, sites):
    a, b = sites
    montar_site(a, b)
    api = subir(dados, a)
    st, r = api.post("/api/gestor/base/fonte", {"url": a.url + "/contato"})
    f = esperar_fonte(api, r["fonte"]["id"])
    ps = propostas_da(api, f["id"])
    end = next(p for p in ps if p.get("campo") == "endereco")
    hor = next(p for p in ps if p["tipo"] == "horario")
    st, r = api.post("/api/gestor/propostas/incorporar-lote", {"itens": [
        {"id": end["id"], "resposta": "Rua das Flores, 123 - Centro, Curitiba - PR, CEP 80000-000"},
        {"id": hor["id"]}, {"id": 99999}]})
    assert st == 200, r
    assert sorted(r["incorporadas"]) == sorted([end["id"], hor["id"]])
    assert r["erros"] and r["erros"][0]["id"] == 99999
    st, cfg = api.get("/api/gestor/config")
    assert "CEP 80000-000" in cfg["info"]["endereco"]
    assert cfg["horarios"]["seg"] == [["07:00", "19:00"]] and cfg["horarios"]["sab"] == [["08:00", "12:00"]]
    st, r = api.post("/api/gestor/propostas/incorporar-lote", {"itens": [{"id": end["id"]}]})
    assert st == 200 and r["incorporadas"] == [] and r["erros"][0]["id"] == end["id"]   # já tratada
    st, r = api.post("/api/gestor/propostas/incorporar-lote", {"itens": []})
    assert st == 422
