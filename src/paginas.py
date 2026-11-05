"""Páginas geradas no servidor: /meu/<token>, /ligar/<token>, /widget.js (seções 7 e 11)."""
import html
import json

from .core import ROOT, parse
from . import chamados


def status_lead(c, lead):
    """Devolve (texto, nome do colaborador ou None, retornar_em ou None)."""
    aberto = chamados.aberto_do_lead(c, lead['id'])
    if aberto and aberto['status'] == 'atendendo':
        nome = c.nome_colab(aberto['dono'])
        return f'{nome} está te atendendo', nome, None
    if aberto:
        return 'Alguém da equipe vai falar com você', None, None
    ret = c.db.execute('SELECT * FROM retornos WHERE lead_id=? AND enviado=0 ORDER BY em DESC LIMIT 1',
                       (lead['id'],)).fetchone()
    if lead['status'] == 'retornar' and ret:
        quando = parse(ret['em']).strftime('%d/%m às %H:%M')
        return f'Retorno marcado para {quando}', c.nome_colab(ret['colaborador']) if ret['colaborador'] else None, ret['em']
    textos = {'ganho': 'Atendimento concluído. Obrigado pela compra!', 'negociando': 'Estamos conversando sobre sua proposta',
              'perdido': 'Atendimento encerrado. Se precisar, é só chamar', 'invalido': 'Atendimento encerrado'}
    return textos.get(lead['status'], 'Recebemos sua mensagem'), None, None


def api_meu(c, token):
    lead = c.lead_token(token)
    texto, colab, ret = status_lead(c, lead)
    msgs = [{'de': r['de'], 'texto': r['texto'], 'em': r['em']} for r in
            c.db.execute("SELECT de, texto, em FROM mensagens WHERE lead_id=? ORDER BY id DESC LIMIT 50", (lead['id'],))]
    return {'nome': lead['nome'], 'status': lead['status'], 'colaborador': colab, 'retornar_em': ret,
            'texto': texto, 'negocio': c.cfg.get('nome'), 'mensagens': list(reversed(msgs))}


def _pagina(titulo, corpo, scripts=''):
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titulo)}</title><link rel="stylesheet" href="/web/style.css"></head>
<body>{corpo}{scripts}</body></html>'''


def pagina_meu(c, token):
    lead = c.lead_token(token)
    texto, colab, _ = status_lead(c, lead)
    negocio = html.escape(c.cfg.get('nome', ''))
    corpo = f'''
<header class="topo"><span class="marca">{negocio}</span><span class="chip">Meu atendimento</span></header>
<main class="estreito">
  <h1>Olá{', ' + html.escape(lead['nome'].split()[0]) if lead['nome'] and lead['nome'] != 'apagado' else ''}</h1>
  <section class="cartao">
    <p class="rotulo">Situação</p>
    <p class="status-grande" id="status">{html.escape(texto)}</p>
    {f'<p class="mut">Quem te atende: <strong>{html.escape(colab)}</strong></p>' if colab else ''}
  </section>
  <div class="acoes">
    <button id="falar" class="primario" data-token="{html.escape(token)}">Quero falar agora</button>
    <button id="apagar" class="secundario">Apagar meus dados</button>
  </div>
  <p id="aviso" class="aviso" role="status"></p>
</main>'''
    return _pagina(f'Meu atendimento · {c.cfg.get("nome", "")}', corpo, '<script src="/web/meu.js"></script>')


def pagina_ligar(c, token):
    ch = c.db.execute('SELECT * FROM chamados WHERE token=?', (token,)).fetchone()
    if not ch:
        return None
    lead = c.lead(ch['lead_id'])
    tel = '+' + lead['telefone'] if lead['telefone'].isdigit() else lead['telefone']
    alvo = html.escape(f'tel:{tel}')
    return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url={alvo}"><title>Ligar</title><link rel="stylesheet" href="/web/style.css"></head>
<body><main class="estreito"><h1>Ligando…</h1>
<p><a class="botao primario" href="{alvo}">Ligar para {html.escape(tel)}</a></p></main></body></html>'''


def widget_js(c):
    modelo = (ROOT / 'web' / 'widget.js').read_text(encoding='utf-8')
    return modelo.replace('__URL_PUBLICA__', json.dumps(c.url_publica()))
