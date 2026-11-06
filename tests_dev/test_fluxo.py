"""Fluxos ponta a ponta com Telegram e Evolution falsos (testes do implementador)."""
import concurrent.futures as cf

from apoio_dev import RAIZ, Falso, Servidor, cfg_exemplo, env_tg, upd_cb, upd_msg

ANA, BRUNO, CARLA = 1001, 1002, 1003


def preparar(**kw):
    tg, evo = Falso(), Falso()
    s = Servidor(env=env_tg(tg, evo), cfg=cfg_exemplo(**kw))
    for fid, cod in ((ANA, 'ana-1234-dev01'), (BRUNO, 'bruno-1234-dev01'), (CARLA, 'carla-1234-dev01')):
        st, _ = s.tg(upd_msg(fid, f'/entrar {cod}'))
        assert st == 200
    return s, tg, evo


def chamado_de(s, lead_id):
    st, f = s.g('GET', f'/api/gestor/leads/{lead_id}')
    assert st == 200, f
    return f['chamados'][-1]


def test_saude_e_porta():
    s = Servidor()
    try:
        st, r = s.req('GET', '/api/saude')
        assert st == 200 and r['ok'] is True and r['versao'] == (RAIZ / 'VERSION').read_text().strip()
        assert r['telegram'] is False and r['evolution'] is False and r['cerebro'] == 'regras'
    finally:
        s.parar()


def test_fluxo_completo():
    s, tg, evo = preparar()
    try:
        assert 'Olá, Ana!' in tg.textos(chat=ANA)
        s.tg(upd_cb(ANA, 'st:livre'))
        s.relogio('2026-11-09T10:01')
        s.tg(upd_cb(BRUNO, 'st:livre'))
        st, r = s.msg('41999990001', 'quero falar com um atendente', nome='Maria Silva')
        assert st == 200 and 'vou chamar' in r['respostas'][0], r
        assert not any('Acompanhe aqui:' in x for x in r['respostas'])  # desligado por padrão (05/11)
        lead = r['lead']
        ch = chamado_de(s, lead['id'])
        assert ch['status'] == 'aguardando' and ch['ofertado_a'] == 'ana' and ch['motivo'] == 'pediu_humano'
        grupo = tg.textos(chat=-100)
        linha = [t for t in grupo if f"#{ch['id']}" in t and t.startswith('🙋')]
        assert linha and '→ Ana' in linha[0] and 'Maria' in linha[0] and '99999' not in linha[0], grupo
        oferta = [c for c in tg.de('sendMessage') if c['corpo']['chat_id'] == str(ANA) and f"#{ch['id']}" in c['corpo']['text']]
        assert oferta and '+55 (41) 99999-0001' in oferta[-1]['corpo']['text']
        kb = oferta[-1]['corpo']['reply_markup']['inline_keyboard']
        dados = [b.get('callback_data') for linha_ in kb for b in linha_]
        assert f"as:{ch['id']}" in dados and f"pa:{ch['id']}" in dados
        urls = [b.get('url') for linha_ in kb for b in linha_ if b.get('url')]
        assert any('/ligar/' in u for u in urls) and 'https://wa.me/5541999990001' in urls
        # ligar
        tok = [u for u in urls if '/ligar/' in u][0].rsplit('/', 1)[1]
        st, html = s.req('GET', f'/ligar/{tok}', bruto=True)
        assert st == 200 and 'tel:+5541999990001' in html
        assert s.req('GET', '/ligar/naoexiste12345678', bruto=True)[0] == 404
        # assumir pelo Telegram
        s.tg(upd_cb(ANA, f"as:{ch['id']}"))
        ch = chamado_de(s, lead['id'])
        assert ch['status'] == 'atendendo' and ch['dono'] == 'ana'
        edits = tg.textos('editMessageText')
        assert any(t == f"✅ Ana assumiu #{ch['id']}" for t in edits), edits
        st, saida = s.g('GET', '/api/saida')
        assert any(m['texto'] == 'Ana vai te atender agora.' and m['tipo'] == 'aviso' for m in saida), saida
        assert any(m['status'] == 'enviado' for m in saida)
        assert evo.de(f"loja") or evo.chamadas
        assert evo.chamadas[-1]['headers'].get('apikey') == 'k'
        # segundo a assumir → 409
        st, r2 = s.e('bruno-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/assumir")
        assert st == 409 and 'já foi assumido por Ana' in r2['erro']
        # lead manda mensagem → vai ao dono
        st, r = s.msg('41999990001', 'tenho pressa')
        assert r['respostas'] == []
        assert '💬 Maria Silva: tenho pressa' in tg.textos(chat=ANA)
        # dono responde pelo reply ao cartão
        cartao = [c for c in tg.de('sendMessage') if c['corpo']['chat_id'] == str(ANA)
                  and 'Você está atendendo' in c['corpo']['text']][-1]
        mid = cartao['mid']
        s.tg(upd_msg(ANA, 'Oi Maria, posso ajudar?', reply=mid))
        st, saida = s.g('GET', '/api/saida')
        assert any(m['texto'] == 'Oi Maria, posso ajudar?' and m['tipo'] == 'humano' for m in saida), saida
        # painel
        st, p = s.g('GET', '/api/painel')
        assert [e['status'] for e in p['equipe']] == ['atendendo', 'livre', 'fora']
        assert p['equipe'][1]['proximo'] is True
        painel = [t for t in tg.textos(chat=-100) + tg.textos('editMessageText') if t.startswith('EQUIPE AGORA')]
        assert painel and '🟡 Ana atendendo Maria' in painel[-1] and '(próxima da vez)' in painel[-1]
        assert tg.de('pinChatMessage')
        # fechar vendeu pelo Telegram
        s.relogio('2026-11-09T10:05')
        s.tg(upd_cb(ANA, f"fe:{ch['id']}:vendeu"))
        s.tg(upd_msg(ANA, '1.200,50'))
        s.tg(upd_cb(ANA, f"fp:{ch['id']}"))
        ch = chamado_de(s, lead['id'])
        assert ch['status'] == 'fechado' and ch['resultado'] == 'vendeu' and ch['valor'] == 1200.5
        st, f = s.g('GET', f"/api/gestor/leads/{lead['id']}")
        assert f['lead']['status'] == 'ganho' and f['historico'][-1]['valor'] == 1200.5
        assert f['historico'][-1]['minutos_ate_assumir'] == 0
        st, p = s.g('GET', '/api/painel')
        assert p['equipe'][0]['status'] == 'livre'
        assert p['equipe'][1]['proximo'] is True  # Ana foi para o fim da fila
        ultimo_painel = [c for c in tg.de('editMessageText') if c['corpo']['text'].startswith('EQUIPE AGORA')][-1]
        assert '🟢 Ana livre há 0 min' in ultimo_painel['corpo']['text']
        st, hoje = s.g('GET', '/api/gestor/hoje')
        assert hoje['vendas'] == 1 and hoje['valor_vendido'] == 1200.5
        st, csv = s.g('GET', '/api/gestor/exportar.csv', bruto=True)
        assert csv.splitlines()[0] == 'lead_id,nome,telefone,status,nota,interesse,colaborador,resultado,valor,criado_em,ultimo_contato'
    finally:
        err = s.parar()
        tg.parar(), evo.parar()
    assert 'erro interno' not in err.lower(), err


def test_oferta_vencida_e_alerta():
    s, tg, evo = preparar()
    try:
        s.tg(upd_cb(ANA, 'st:livre'))
        s.relogio('2026-11-09T10:01')
        s.tg(upd_cb(BRUNO, 'st:livre'))
        st, r = s.msg('41999990002', 'quanto custa o plano anual?', nome='João')
        assert 'Plano anual: R$ 1.200' in r['respostas'][0] and 'vou chamar' in r['respostas'][0]
        lead = r['lead']
        assert lead['nota'] == 'quente'
        ch = chamado_de(s, lead['id'])
        assert ch['prioridade'] == 'quente' and ch['ofertado_a'] == 'ana'
        assert any(t.startswith('🔥') and f"#{ch['id']}" in t for t in tg.textos(chat=-100))
        r = s.relogio('2026-11-09T10:03')
        assert r['acoes'] >= 2, r
        ch = chamado_de(s, lead['id'])
        assert ch['ofertado_a'] == 'bruno' and ch['recusaram'] == ['ana'] and ch['status'] == 'alerta', ch
        assert f"⌛ #{ch['id']} passou para o próximo" in tg.textos('editMessageText')
        alertas = [t for t in tg.textos(chat=-100) if t.startswith('🚨')]
        assert len(alertas) == 1 and f"#{ch['id']}" in alertas[0] and '99999' not in alertas[0]
        # Bruno passa → ninguém → continua em alerta, sem novo alerta
        s.tg(upd_cb(BRUNO, f"pa:{ch['id']}"))
        ch = chamado_de(s, lead['id'])
        assert ch['ofertado_a'] is None and ch['status'] == 'alerta'
        assert len([t for t in tg.textos(chat=-100) if t.startswith('🚨')]) == 1
        # Carla fica livre → recebe oferta
        s.tg(upd_cb(CARLA, 'st:livre'))
        ch = chamado_de(s, lead['id'])
        assert ch['ofertado_a'] == 'carla'
        # corrida pelo assumir
        with cf.ThreadPoolExecutor(3) as ex:
            res = list(ex.map(lambda cod: s.e(cod, 'POST', f"/api/equipe/chamados/{ch['id']}/assumir")[0],
                              ['ana-1234-dev01', 'bruno-1234-dev01', 'carla-1234-dev01']))
        assert sorted(res) == [200, 409, 409], res
        # Telegram para quem perdeu
        s.tg(upd_cb(ANA, f"as:{ch['id']}"))
        respostas = [c['corpo'].get('text', '') for c in tg.de('answerCallbackQuery')]
        assert any('já foi assumido por' in t for t in respostas)
    finally:
        s.parar()
        tg.parar(), evo.parar()


def test_fora_do_horario_e_abertura():
    s, tg, evo = preparar()
    try:
        s.relogio('2026-11-09T20:00')
        st, r = s.msg('41999990003', 'quero falar com alguem', nome='Lia')
        assert 'fora do horário' in r['respostas'][0] and '10/11 às 08:00' in r['respostas'][0], r
        ch = chamado_de(s, r['lead']['id'])
        assert ch['status'] == 'aguardando' and ch['ofertado_a'] is None
        s.tg(upd_cb(ANA, 'st:livre'))
        assert chamado_de(s, r['lead']['id'])['ofertado_a'] is None
        s.relogio('2026-11-10T08:00')
        ch = chamado_de(s, r['lead']['id'])
        assert ch['ofertado_a'] == 'ana'
    finally:
        s.parar()
        tg.parar(), evo.parar()


def test_regras_conversa():
    s = Servidor()
    try:
        st, r = s.msg('41 99999-0004', 'oi')
        assert 'Loja Exemplo' in r['respostas'][0] and 'nome' in r['respostas'][0]
        assert r['lead']['status'] == 'novo' and r['lead']['nota'] == 'frio' and len(r['lead']['token']) >= 16
        st, r = s.msg('41999990004', 'Maria')
        assert '1 - Plano anual' in r['respostas'][0] and '0 - Outro assunto' in r['respostas'][0]
        st, r = s.msg('41999990004', '9')
        assert '1 - Plano anual' in r['respostas'][0]
        st, r = s.msg('41999990004', '1')
        assert '1 - Hoje / esta semana' in r['respostas'][0]
        st, r = s.msg('41999990004', '2')
        assert 'Quer que eu chame alguém para te atender?' in r['respostas'][0] and r['lead']['nota'] == 'morno'
        st, r = s.msg('41999990004', 'sim')
        assert 'vou chamar' in r['respostas'][0]
        st, r = s.msg('41999990004', 'oi de novo')
        assert 'já avisei' in r['respostas'][0]
        st, r = s.msg('41999990005', 'qual o horário de atendimento?')
        assert r['respostas'] == ['Atendemos de segunda a sexta, das 8h às 18h.']
        st, r = s.msg('41999990005', 'blablabla')
        assert 'não sei responder' in r['respostas'][0] and 'alguém da equipe' in r['respostas'][0]
        st, r = s.msg('41999990005', 'xyzzy')
        assert 'vou chamar' in r['respostas'][0]
        st, r = s.msg('41999990006', 'parar')
        assert 'não vai mais receber' in r['respostas'][0]
        st, r = s.msg('41999990006', 'apagar meus dados')
        assert 'apagados' in r['respostas'][0]
        assert s.msg('123', 'oi')[0] == 422
        st, r = s.msg('41999990007', 'meu produto deu defeito')
        assert 'vou chamar' in r['respostas'][0]
        st, r = s.msg('41999990008', 'tenho interesse no plano anual', nome='Rui')
        assert 'Plano anual' in r['respostas'][0] and 'Quer que eu chame alguém para te atender?' in r['respostas'][0]
        st, r = s.msg('41999990009', 'quero pesquisar', nome='Bia')
        st, r = s.msg('41999990009', '0')
        st, r = s.msg('41999990009', '3')
        assert 'qualquer dúvida' in r['respostas'][0]
        # meu atendimento
        st, r = s.msg('41999990010', 'oi', nome='Zé')
        tok = r['lead']['token']
        st, m = s.req('GET', f'/api/meu/{tok}')
        assert st == 200 and m['status'] == 'novo'
        st, html = s.req('GET', f'/meu/{tok}', bruto=True)
        assert 'Recebemos sua mensagem' in html and 'Quero falar agora' in html and 'Apagar meus dados' in html
        st, r = s.req('POST', f'/api/meu/{tok}/falar')
        assert st == 200 and 'vou chamar' in r['respostas'][0]
        st, html = s.req('GET', f'/meu/{tok}', bruto=True)
        assert 'Alguém da equipe vai falar com você' in html
        assert s.req('GET', '/api/meu/naoexiste1234567890')[0] == 404
        assert s.g('POST', '/api/relogio', {'agora': 'x'})[0] == 422
        assert s.req('POST', '/api/relogio', {'agora': '2026-11-09T10:00'})[0] == 401
    finally:
        s.parar()


def test_relogio_403_sem_atende_agora():
    s = Servidor(agora=None)
    try:
        assert s.g('POST', '/api/relogio', {'agora': '2026-11-09T10:00'})[0] == 403
    finally:
        s.parar()


def test_whatsapp_webhook_simulado():
    s = Servidor(env={'WEBHOOK_SEGREDO': 'seg'})
    try:
        corpo = {'event': 'messages.upsert', 'instance': 'x', 'data': {
            'key': {'remoteJid': '5541999990020@s.whatsapp.net', 'fromMe': False, 'id': 'ABC'},
            'pushName': 'Maria', 'message': {'conversation': 'oi'}, 'messageType': 'conversation'}}
        assert s.req('POST', '/webhook/evolution/errado', corpo)[0] == 404
        assert s.req('POST', '/webhook/evolution/seg', corpo)[0] == 200
        assert s.req('POST', '/webhook/evolution/seg', corpo)[0] == 200  # repetido
        st, saida = s.g('GET', '/api/saida')
        assert len(saida) == 1 and saida[0]['status'] == 'simulado' and 'Posso te chamar de Maria?' in saida[0]['texto']
        corpo['data']['key']['id'] = 'DEF'
        corpo['data']['message'] = {'extendedTextMessage': {'text': 'sim'}}
        s.req('POST', '/webhook/evolution/seg', corpo)
        st, leads = s.g('GET', '/api/gestor/leads')
        assert leads[0]['nome'] == 'Maria'
        corpo['data']['key']['id'] = 'GHI'
        corpo['data']['message'] = {'imageMessage': {}}
        s.req('POST', '/webhook/evolution/seg', corpo)
        st, saida = s.g('GET', '/api/saida')
        assert saida[-1]['texto'] == 'Por enquanto só consigo ler mensagens de texto.'
    finally:
        s.parar()


def test_config_e_fechamento_validacoes():
    s, tg, evo = preparar()
    try:
        st, cfg = s.g('GET', '/api/gestor/config')
        assert cfg['token_gestor'] == '***'
        cfg['prazos']['oferta_min'] = 0
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 422
        cfg['prazos']['oferta_min'] = 3
        assert s.g('PUT', '/api/gestor/config', cfg)[0] == 200
        assert s.g('GET', '/api/gestor/config')[0] == 200  # token mantido
        s.e('ana-1234-dev01', 'POST', '/api/equipe/status', {'status': 'livre'})
        st, r = s.msg('41999990030', 'falar com uma pessoa', nome='Téo')
        ch = chamado_de(s, r['lead']['id'])
        s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/assumir")
        assert s.e('ana-1234-dev01', 'POST', '/api/equipe/status', {'status': 'fora'})[0] == 409
        assert s.e('bruno-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar", {'resultado': 'negociando'})[0] == 403
        assert s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar", {'resultado': 'vendeu'})[0] == 422
        assert s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar",
                   {'resultado': 'sem_interesse', 'motivo': 'spam'})[0] == 422
        assert s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar",
                   {'resultado': 'retornar', 'retornar_em': '2026-11-01T10:00'})[0] == 422
        st, r = s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar",
                    {'resultado': 'retornar', 'retornar_em': '2026-11-10T09:00'})
        assert st == 200, r
        assert s.e('ana-1234-dev01', 'POST', f"/api/equipe/chamados/{ch['id']}/fechar", {'resultado': 'negociando'})[0] == 409
        st, saida = s.g('GET', '/api/saida')
        assert any(m['texto'] == 'Combinado! Vamos te procurar em 10/11 às 09:00.' for m in saida)
        s.relogio('2026-11-10T09:00')
        assert any(t.startswith('📅 Retorno: Téo +55 (41) 99999-0030') for t in tg.textos(chat=ANA)), tg.textos(chat=ANA)
        s.tg(upd_cb(ANA, f"ra:{ch['id']}"))
        st, f = s.g('GET', f"/api/gestor/leads/{r['lead_id']}")
        assert f['chamados'][-1]['status'] == 'atendendo' and f['chamados'][-1]['dono'] == 'ana'
        # lembrete
        s.relogio('2026-11-10T09:31')
        assert any(t.startswith('Ainda com Téo?') for t in tg.textos(chat=ANA))
        # fim do expediente
        s.relogio('2026-11-10T18:00')
        assert 'Fim do expediente: feche seus atendimentos' in tg.textos(chat=ANA)
    finally:
        s.parar()
        tg.parar(), evo.parar()
