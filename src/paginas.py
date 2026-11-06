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
    """Só a situação: o texto das mensagens nunca sai por aqui (o link pode ser repassado)."""
    lead = c.lead_token(token)
    _texto, colab, ret = status_lead(c, lead)
    return {'nome': lead['nome'], 'status': lead['status'], 'colaborador': colab, 'retornar_em': ret}


def _tema(c):
    tema = (c.cfg.get('aparencia') or {}).get('tema') or 'claro'
    return tema if tema in ('claro', 'escuro', 'marinho') else 'claro'


def _pagina(c, titulo, corpo, scripts=''):
    return f'''<!doctype html>
<html lang="pt-BR" data-tema="{_tema(c)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(titulo)}</title><link rel="stylesheet" href="/web/style.css"></head>
<body class="pagina-simples">{corpo}{scripts}</body></html>'''


def pagina_meu(c, token):
    lead = c.lead_token(token)
    texto, colab, _ = status_lead(c, lead)
    negocio = html.escape(c.cfg.get('nome', ''))
    corpo = f'''
<header class="topo"><div class="marca"><h1>{negocio}</h1><span class="sub">Meu atendimento</span></div></header>
<main>
  <h2>Olá{', ' + html.escape(lead['nome'].split()[0]) if lead['nome'] and lead['nome'] != 'apagado' else ''}</h2>
  <section class="cartao">
    <p class="rotulo">Situação</p>
    <p class="status-grande" id="status">{html.escape(texto)}</p>
    {f'<p class="mut">Quem te atende: <strong>{html.escape(colab)}</strong></p>' if colab else ''}
  </section>
  <div class="acoes">
    <button id="falar" class="btn pri" data-token="{html.escape(token)}">Quero falar agora</button>
    <button id="apagar" class="btn">Apagar meus dados</button>
  </div>
  <p id="aviso" class="aviso" role="status"></p>
</main>'''
    return _pagina(c, f'Meu atendimento · {c.cfg.get("nome", "")}', corpo, '<script src="/web/meu.js"></script>')


def pagina_ligar(c, token):
    ch = c.db.execute('SELECT * FROM chamados WHERE token=?', (token,)).fetchone()
    if not ch:
        return None
    lead = c.lead(ch['lead_id'])
    tel = '+' + lead['telefone'] if lead['telefone'].isdigit() else lead['telefone']
    alvo = html.escape(f'tel:{tel}')
    return f'''<!doctype html>
<html lang="pt-BR" data-tema="{_tema(c)}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="0;url={alvo}"><title>Ligar</title><link rel="stylesheet" href="/web/style.css"></head>
<body class="pagina-simples"><main><h1>Ligando…</h1>
<p><a class="btn pri" href="{alvo}">Ligar para {html.escape(tel)}</a></p></main></body></html>'''


def widget_js(c):
    modelo = (ROOT / 'web' / 'widget.js').read_text(encoding='utf-8')
    from .gestao import aparencia
    return (modelo.replace('__URL_PUBLICA__', json.dumps(c.url_publica()))
            .replace('__APARENCIA__', json.dumps(aparencia(c), ensure_ascii=False).replace('</', '<\\/')))
