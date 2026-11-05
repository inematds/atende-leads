"""Mais casos: Telegram (comandos, voz, vínculo), gestor (transferir, reabrir), backup, painel com edição falhando."""
import json
import os
import stat
import subprocess
import sys
import tempfile

from apoio_dev import RAIZ, Falso, Servidor, cfg_exemplo, env_tg, upd_cb, upd_msg

ANA, BRUNO, CARLA = 1001, 1002, 1003


def preparar(falhar_edicao=False, env_extra=None):
    tg = Falso(falhar_edicao=falhar_edicao)
    env = env_tg(tg)
    env.update(env_extra or {})
    s = Servidor(env=env, cfg=cfg_exemplo())
    for fid, cod in ((ANA, 'ana-1234'), (BRUNO, 'bruno-1234'), (CARLA, 'carla-1234')):
        s.tg(upd_msg(fid, f'/entrar {cod}'))
    return s, tg


def ultimo_ch(s, lead_id):
    return s.g('GET', f'/api/gestor/leads/{lead_id}')[1]['chamados'][-1]


def test_vinculo_e_comandos():
    s, tg = preparar()
    try:
        assert s.tg(upd_msg(7, 'oi'), segredo='errado')[0] == 401
        s.tg(upd_msg(7, '/entrar xxx'))
        assert 'Código inválido.' in tg.textos(chat=7)
        s.tg(upd_msg(7, '/livre'))
        assert 'Envie /entrar <seu código>.' in tg.textos(chat=7)
        s.tg(upd_cb(7, 'st:livre'))
        assert any('Envie /entrar' in c['corpo'].get('text', '') for c in tg.de('answerCallbackQuery'))
        s.tg(upd_msg(ANA, '/livre'))
        s.tg(upd_msg(BRUNO, '/status', chat_id=-100))
        assert any(t.startswith('EQUIPE AGORA') for t in tg.textos(chat=-100))
        st, r = s.msg('41999990040', 'quero falar com o vendedor', nome='Paulo Souza')
        ch = ultimo_ch(s, r['lead']['id'])
        s.tg(upd_cb(ANA, f"as:{ch['id']}"))
        s.tg(upd_msg(ANA, '/meus'))
        assert any('Paulo Souza' in t for t in tg.textos(chat=ANA) if t.startswith('Seus atendimentos'))
        s.tg(upd_msg(ANA, '/lead paulo'))
        assert any(t.startswith('Lead ') and '+55 (41) 99999-0040' in t for t in tg.textos(chat=ANA))
        s.tg(upd_msg(BRUNO, '/lead paulo'))
        assert any('Nenhum lead' in t for t in tg.textos(chat=BRUNO))
        s.tg(upd_msg(ANA, f"/fechar {ch['id']} sem preco achou caro"))
        ch = ultimo_ch(s, r['lead']['id'])
        assert ch['resultado'] == 'sem_interesse' and ch['motivo_fechamento'] == 'preco' and ch['nota_fechamento'] == 'achou caro'
        # todas as callbacks respondidas
        assert len(tg.de('answerCallbackQuery')) >= 2
    finally:
        s.parar()
        tg.parar()


def test_voz_como_nota():
    d = tempfile.mkdtemp()
    script = os.path.join(d, 'whisper.sh')
    with open(script, 'w') as f:
        f.write('#!/bin/sh\necho "cliente pediu desconto"\n')
    os.chmod(script, stat.S_IRWXU)
    s, tg = preparar(env_extra={'WHISPER_CMD': script})
    try:
        s.tg(upd_msg(ANA, '/livre'))
        st, r = s.msg('41999990041', 'atendente por favor', nome='Rosa')
        ch = ultimo_ch(s, r['lead']['id'])
        s.tg(upd_cb(ANA, f"as:{ch['id']}"))
        s.tg(upd_cb(ANA, f"fe:{ch['id']}:negociando"))
        u = upd_msg(ANA, '')
        u['message'].pop('text')
        u['message']['voice'] = {'file_id': 'F1', 'duration': 2}
        s.tg(u)
        ch = ultimo_ch(s, r['lead']['id'])
        assert ch['status'] == 'fechado' and ch['nota_fechamento'] == 'cliente pediu desconto', ch
        assert tg.de('getFile')
    finally:
        s.parar()
        tg.parar()


def test_retornar_pelo_telegram_e_devolver():
    s, tg = preparar()
    try:
        s.tg(upd_msg(ANA, '/livre'))
        s.tg(upd_msg(BRUNO, '/livre'))
        st, r = s.msg('41999990042', 'tenho um problema', nome='Caio')
        ch = ultimo_ch(s, r['lead']['id'])
        assert ch['motivo'] == 'precisa' and ch['prioridade'] == 'normal'
        s.tg(upd_cb(ANA, f"as:{ch['id']}"))
        s.tg(upd_cb(ANA, f"fe:{ch['id']}:retornar"))
        kb = [c for c in tg.de('sendMessage') if 'Quando retornar' in c['corpo']['text']][-1]['corpo']['reply_markup']
        rotulos = [b['text'] for l in kb['inline_keyboard'] for b in l]
        assert rotulos == ['Amanhã 09:00', 'Em 3 dias 09:00', 'Semana que vem 09:00']
        s.relogio('2026-11-09T10:05')
        s.tg(upd_cb(ANA, f"fr:{ch['id']}:3"))
        s.tg(upd_msg(ANA, 'ligar à tarde'))
        ch = ultimo_ch(s, r['lead']['id'])
        assert ch['resultado'] == 'retornar' and ch['retornar_em'] == '2026-11-12T09:00'
        st, m = s.req('GET', f"/api/meu/{r['lead']['token']}")
        assert m['status'] == 'retornar' and m['retornar_em'] == '2026-11-12T09:00'
        st, html = s.req('GET', f"/meu/{r['lead']['token']}", bruto=True)
        assert 'Retorno marcado para 12/11 às 09:00' in html
        # novo contato → oferta primeiro para Ana (lead que volta)
        st, p = s.g('GET', '/api/painel')
        assert [e['id'] for e in p['equipe'] if e['proximo']] == ['bruno']
        st, r2 = s.msg('41999990042', 'quero falar com um humano')
        ch2 = ultimo_ch(s, r['lead']['id'])
        assert ch2['ofertado_a'] == 'ana'  # Bruno é o próximo da vez, mas Ana é a dona anterior
    finally:
        s.parar()
        tg.parar()


def test_gestor_transferir_reabrir_config():
    s, tg = preparar()
    try:
        s.tg(upd_msg(ANA, '/livre'))
        s.tg(upd_msg(BRUNO, '/livre'))
        st, r = s.msg('41999990043', 'qual o valor do plano anual', nome='Duda')
        ch = ultimo_ch(s, r['lead']['id'])
        st, x = s.g('POST', f"/api/gestor/chamados/{ch['id']}/transferir", {'colaborador': 'bruno'})
        assert st == 200 and x['dono'] == 'bruno' and x['status'] == 'atendendo'
        st, x = s.g('POST', f"/api/gestor/chamados/{ch['id']}/transferir", {'colaborador': 'ana'})
        assert x['dono'] == 'ana'
        st, p = s.g('GET', '/api/painel')
        est = {e['id']: e['status'] for e in p['equipe']}
        assert est['bruno'] == 'livre' and est['ana'] == 'atendendo'
        st, x = s.e('ana-1234', 'POST', f"/api/equipe/chamados/{ch['id']}/devolver")
        assert st == 200 and x['resultado'] == 'devolvido'
        st, f = s.g('GET', f"/api/gestor/leads/{r['lead']['id']}")
        assert f['lead']['status'] == 'novo'
        st, x = s.g('POST', f"/api/gestor/chamados/{ch['id']}/reabrir")
        assert st == 200 and x['status'] == 'aguardando'
        st, cfg = s.g('GET', '/api/gestor/config')
        cfg['equipe'].append({'id': 'ana', 'nome': 'Outra', 'codigo': 'x'})
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 422
        cfg['equipe'][-1] = {'id': 'davi', 'nome': 'Davi', 'codigo': 'ana-1234'}
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 422
        cfg['equipe'][-1] = {'id': 'davi', 'nome': 'Davi', 'codigo': 'davi-1'}
        cfg['horarios']['seg'] = [['8:00', '18:00']]
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 422
        cfg['horarios']['seg'] = [['08:00', '18:00']]
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 200
        assert s.e('davi-1', 'GET', '/api/equipe/eu')[1]['status'] == 'fora'
        assert s.req('GET', '/api/gestor/config', headers={'X-Token': 'TROQUE-ESTE-TOKEN'})[0] == 200
        assert s.req('GET', '/api/gestor/hoje')[0] == 401
        assert s.e('errado', 'GET', '/api/painel')[0] == 401
        st, leads = s.g('GET', '/api/gestor/leads?colaborador=bruno')
        assert st == 200 and leads == []
    finally:
        s.parar()
        tg.parar()


def test_painel_edicao_falha_reenvia():
    s, tg = preparar(falhar_edicao=True)
    try:
        s.tg(upd_msg(ANA, '/livre'))
        s.tg(upd_msg(BRUNO, '/livre'))
        paineis = [c for c in tg.de('sendMessage') if c['corpo']['text'].startswith('EQUIPE AGORA')]
        assert len(paineis) >= 2 and len(tg.de('pinChatMessage')) >= 2
    finally:
        s.parar()
        tg.parar()


def test_backup_restaurar():
    s = Servidor()
    try:
        s.msg('41999990050', 'oi', nome='Bel')
        saida = os.path.join(tempfile.mkdtemp(), 'b.tar.gz')
        r = subprocess.run([sys.executable, str(RAIZ / 'atende'), 'backup', '--dados', s.dir, '--saida', saida],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        novo = tempfile.mkdtemp()
        r = subprocess.run([sys.executable, str(RAIZ / 'atende'), 'restaurar', '--dados', novo, '--arquivo', saida],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert json.load(open(os.path.join(novo, 'negocio.json')))['nome'] == 'Loja Exemplo'
        s2 = Servidor(dados=novo)
        try:
            leads = s2.g('GET', '/api/gestor/leads')[1]
            assert [l['nome'] for l in leads] == ['Bel']
        finally:
            s2.parar()
    finally:
        s.parar()


def test_nao_contatar_e_widget():
    s = Servidor()
    try:
        st, r = s.msg('41999990060', 'parar')
        assert r['lead']['nao_contatar'] is True
        st, r = s.msg('41999990060', 'oi')
        assert r['lead']['nao_contatar'] is False and r['respostas']
        st, js = s.req('GET', '/widget.js', bruto=True)
        assert st == 200 and 'http://localhost:8080' in js and '?widget=1' in js
        for rota in ('/', '/equipe', '/gestor', '/web/style.css'):
            assert s.req('GET', rota, bruto=True)[0] == 200, rota
        st, r = s.msg('41999990061', 'apagar meus dados')
        st, leads = s.g('GET', '/api/gestor/leads')
        ap = [l for l in leads if l['id'] == r['lead']['id']][0]
        assert ap['nome'] == 'apagado' and ap['telefone'] == f"apagado-{ap['id']}"
    finally:
        s.parar()


def test_faq_no_meio_da_qualificacao():
    s = Servidor()
    try:
        s.msg('41999990080', 'oi')
        st, r = s.msg('41999990080', 'qual o horario de atendimento?')
        assert r['respostas'] == ['Atendemos de segunda a sexta, das 8h às 18h.']
        st, r = s.msg('41999990080', 'Joana')
        assert 'Prazer, Joana' in r['respostas'][0]
    finally:
        s.parar()


def test_reinicio_mantem_estado():
    tg = Falso()
    s = Servidor(env=env_tg(tg), cfg=cfg_exemplo(), manter=True)
    try:
        s.tg(upd_msg(ANA, '/entrar ana-1234'))
        s.tg(upd_msg(ANA, '/livre'))
        st, r = s.msg('41999990090', 'falar com atendente', nome='Nina')
    finally:
        s.parar()
    s2 = Servidor(env=env_tg(tg), dados=s.dir)
    try:
        st, f = s2.g('GET', f"/api/gestor/leads/{r['lead']['id']}")
        assert f['chamados'][-1]['ofertado_a'] == 'ana' and f['lead']['nome'] == 'Nina'
        tg.limpar()
        s2.tg(upd_msg(ANA, '/meus'))
        assert tg.textos(chat=ANA) and 'Envie /entrar' not in tg.textos(chat=ANA)[0]
    finally:
        s2.parar()
        tg.parar()


def test_entrar_depois_recebe_oferta_e_imagem_primeiro():
    tg = Falso()
    s = Servidor(env=env_tg(tg), cfg=cfg_exemplo())
    try:
        s.g('POST', '/api/gestor/equipe/ana/status', {'status': 'livre'})
        st, r = s.msg('41999990091', 'falar com atendente', nome='Edu')
        ch = s.g('GET', f"/api/gestor/leads/{r['lead']['id']}")[1]['chamados'][-1]
        assert ch['ofertado_a'] is None and ch['status'] == 'alerta'
        s.tg(upd_msg(ANA, '/entrar ana-1234'))
        ch = s.g('GET', f"/api/gestor/leads/{r['lead']['id']}")[1]['chamados'][-1]
        assert ch['ofertado_a'] == 'ana'
    finally:
        s.parar()
        tg.parar()
    s = Servidor(env={'WEBHOOK_SEGREDO': 'w'})
    try:
        base = {'event': 'messages.upsert', 'data': {'key': {'remoteJid': '5541999990092@s.whatsapp.net', 'fromMe': False,
                                                              'id': 'I1'}, 'message': {'imageMessage': {}}}}
        s.req('POST', '/webhook/evolution/w', base)
        base['data']['key']['id'] = 'I2'
        base['data']['message'] = {'conversation': 'oi'}
        s.req('POST', '/webhook/evolution/w', base)
        saida = s.g('GET', '/api/saida')[1]
        assert 'Loja Exemplo' in saida[-1]['texto'], saida
    finally:
        s.parar()
