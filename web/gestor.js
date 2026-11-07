// Painel do gestor: token na aba (sessionStorage) ou no aparelho (localStorage, se "lembrar").
(function () {
  const $ = id => document.getElementById(id);
  const ic = AL.ic, esc = AL.esc;
  let token = null, cfg = null, aba = 'aovivo', timer = null, sujoBase = false;
  const api = (m, r, c) => AL.api(m, r, c, {'X-Token': token});
  let tAviso = null;
  const aviso = (t, erro) => {
    const el = $('aviso'); el.textContent = t || ''; el.className = 'toast' + (erro ? ' erro' : '');
    clearTimeout(tAviso); if (t) tAviso = setTimeout(() => { el.textContent = ''; }, erro ? 8000 : 3500);
  };
  const TITULOS = {aovivo: 'Ao vivo', hoje: 'Hoje', leads: 'Leads', base: 'Base de conhecimento', consolidada: 'Base consolidada', aprendizado: 'Aprendizado', cadastros: 'Cadastros', exportar: 'Exportar'};
  const nomeColab = id => { const m = (cfg && cfg.equipe || []).find(x => x.id === id); return m ? m.nome : (id || ''); };
  const extremo = () => ((cfg && cfg.prazos) || {}).assumir_extremo_min || 10;
  const vazio = t => '<p class="vazio">' + esc(t) + '</p>';

  AL.seletorTema('tema'); AL.seletorTema('tema-login');

  // ---------- Ao vivo: equipe | em atendimento | fila ----------
  function opcoesTransf(atual) {
    const ordem = {livre: 0, atendendo: 1, ocupado: 2, fora: 3};
    return '<option value="">Transferir para…</option>' + (cfg ? cfg.equipe : []).filter(m => m.id !== atual)
      .map(m => '<option value="' + esc(m.id) + '">' + esc(m.nome) + '</option>').join('');
  }
  function transf(ch, atual) {
    return '<div class="acao"><label class="sr" for="tr-' + ch + '">Transferir #' + ch + ' para</label><select id="tr-' + ch + '" data-transf-sel="' + ch + '">' +
      opcoesTransf(atual) + '</select><button type="button" class="btn peq" data-transf="' + ch + '">' + ic('swap') + 'Transferir</button></div>';
  }
  // identificação comum a todo cartão: #lead · nome · telefone
  const ident = (id, nome, tel) => '<strong>#' + id + ' ' + esc(nome || 'sem nome') + '</strong>' +
    (tel && !String(tel).startsWith('apagado-') ? '<span class="tel">' + esc(AL.fone(tel)) + '</span>' : '');
  let voltaram = new Set();  // leads de "Encerradas hoje" que voltaram a escrever (estão no Robô atendendo)
  const verConversa = id => '<div class="acao"><button type="button" class="btn sutil peq" data-ficha="' + id + '">' + ic('file') + 'Ver conversa</button></div>';
  const cartoes = {
    robo: r => '<div class="it' + (r.nota === 'quente' ? ' t-quente' : '') + '"><div class="l1">' + ident(r.lead_id, r.nome, r.telefone) + AL.nota(r.nota) + '<span class="dir">' + esc(AL.ha(r.minutos_desde_contato)) + '</span></div>' +
      (r.ultima_mensagem ? '<p>“' + esc(r.ultima_mensagem) + '”</p>' : '') +
      '<div class="acao"><label class="sr" for="at-' + r.lead_id + '">Passar #' + r.lead_id + ' para</label><select id="at-' + r.lead_id + '" data-atrib-sel="' + r.lead_id + '">' +
      opcoesTransf(null) + '</select><button type="button" class="btn peq" data-atribuir="' + r.lead_id + '">' + ic('swap') + 'Passar</button></div>' + verConversa(r.lead_id) + '</div>',
    espera: (ch, ext) => {
      const demais = ch.status === 'alerta' || ch.minutos > ext;
      const q = ch.nota === 'quente';
      return '<div class="it' + (demais ? ' ext' : '') + (q ? ' t-quente' : '') + '"><div class="l1">' + ident(ch.lead_id, ch.lead_nome, ch.telefone) + (q ? AL.nota('quente') : AL.nota(ch.nota)) +
        '<span class="espera' + (demais ? ' demais' : '') + '" style="margin-left:auto">' + ic('clock') + esc(AL.dur(ch.minutos)) + '</span></div>' +
        '<p>chamado #' + ch.id + ' · ' + esc(AL.MOTIVO[ch.motivo] || '') + ' · ' + (ch.ofertado_a ? 'oferecido a ' + esc(nomeColab(ch.ofertado_a)) : 'ninguém aceitou ainda') +
        (demais ? ' · <strong class="ruim">esperando demais</strong>' : '') + '</p>' +
        (ch.silencioso ? '<p class="peq mut">' + ic('spark') + ' chance de venda: o cliente não sabe que alguém vai falar com ele</p>' : '') + transf(ch.id, null) + '</div>';
    },
    atendendo: (ch, ext) => {
      const sr = ch.sem_resposta_min, grave = sr != null && sr > ext;
      return '<div class="it' + (grave ? ' ext' : '') + '"><div class="l1">' + ident(ch.lead_id, ch.lead_nome, ch.telefone) + AL.nota(ch.nota) +
        '<span class="dir">aberto há ' + esc(AL.dur(ch.minutos)) + '</span></div><p>com <strong>' + esc(nomeColab(ch.dono)) + '</strong> · chamado #' + ch.id +
        (ch.interesse_nome ? ' · ' + esc(ch.interesse_nome) : '') + '</p>' +
        (sr != null ? '<p><span class="espera' + (grave ? ' demais' : '') + '">' + ic('clock') + 'cliente sem resposta há ' + esc(AL.dur(sr)) + '</span></p>' : '<p class="ok-t">respondido</p>') +
        tempos(ch.tempos) +
        transf(ch.id, ch.dono) + verConversa(ch.lead_id) + '</div>';
    },
    encerrados: ch => '<div class="it"><div class="l1">' + ident(ch.lead_id, ch.lead_nome, ch.telefone) + '<span class="dir">' + esc(AL.hm(ch.fechado_em)) + '</span></div>' +
      '<p>' + esc(AL.RESULTADO[ch.resultado] || ch.resultado || '—') + (ch.valor ? ' · ' + esc(AL.brl(ch.valor)) : '') + (ch.dono ? ' · ' + esc(nomeColab(ch.dono)) : '') + ' · chamado #' + ch.id + '</p>' +
      (voltaram.has(ch.lead_id) ? '<p><span class="sit s-robo">voltou a escrever · o robô está respondendo</span></p>' : '') +
      tempos(ch.tempos) + verConversa(ch.lead_id) + '</div>',
  };
  // espera até assumir (quanto dela com o robô conversando) · 1ª resposta da equipe
  function tempos(t) {
    if (!t) return '';
    const p = ['esperou ' + AL.dur(t.espera_min) + (t.espera_sem_resposta_min ? ' (' + AL.dur(t.espera_sem_resposta_min) + ' sem resposta nenhuma)' : '')];
    if (t.robo_msgs) p.push('robô respondeu ' + t.robo_msgs + (t.robo_msgs === 1 ? ' vez' : ' vezes') + (t.espera_robo_min ? ' em ' + AL.dur(t.espera_robo_min) + ' de conversa' : '') + ' na espera');
    if (t.primeira_resposta_min != null) p.push('1ª resposta em ' + AL.dur(t.primeira_resposta_min));
    return '<p class="peq mut">' + esc(p.join(' · ')) + '</p>';
  }
  function alertaResposta(lista) {
    if (!lista.length) return '';
    const p = lista[0];
    return '<div class="alerta" role="alert">' + ic('alert') + '<p><strong>' + lista.length + (lista.length === 1 ? ' cliente sem resposta' : ' clientes sem resposta') + ' no atendimento</strong> — ' +
      esc(p.lead_nome || 'Lead') + ' espera resposta de ' + esc(nomeColab(p.dono)) + ' há ' + esc(AL.dur(p.sem_resposta_min)) + '.</p>' +
      (aba !== 'aovivo' ? '<button type="button" class="btn pri" data-ir="aovivo">Ver no Ao vivo' + ic('arrow') + '</button>' : '') + '</div>';
  }
  async function aoVivo() {
    const p = await api('GET', '/api/gestor/ao-vivo');
    $('data').textContent = 'atualizado ' + AL.hm(p.agora);
    const ordem = {livre: 0, atendendo: 1, ocupado: 2, fora: 3};
    const eq = p.equipe.slice().sort((a, b) => (b.proximo - a.proximo) || (ordem[a.status] - ordem[b.status]));
    const atendendoDe = {}; p.atendendo.forEach(ch => { (atendendoDe[ch.dono] = atendendoDe[ch.dono] || []).push(ch.lead_nome || 'Lead'); });
    $('av-livres').textContent = p.equipe.filter(e => e.status === 'livre').length + ' livre(s)';
    $('av-equipe').innerHTML = eq.length ? eq.map(e => '<div class="it"><div class="l1">' + AL.ponto(e.status) + '<strong>' + esc(e.nome) + '</strong>' +
      '<span class="dir">' + esc(AL.COLAB[e.status] || e.status) + (e.status === 'atendendo' ? ' ' + (atendendoDe[e.id] || []).length : ' há ' + esc(AL.dur(e.minutos))) + '</span></div>' +
      '<p>' + (e.proximo ? '<strong>Próximo da vez</strong>' : '') + (atendendoDe[e.id] ? esc(atendendoDe[e.id].join(' · ')) : '') + '</p>' +
      '<button type="button" class="btn sutil peq interr" data-robo-colab="' + esc(e.id) + '" aria-pressed="' + !!e.robo_por_mim + '">' + ic('spark') + 'Robô responde por ' + esc(e.nome.split(' ')[0]) +
      '<b class="estado">' + (e.robo_por_mim ? 'ligado' : 'desligado') + '</b></button>' +
      '<div class="seg" role="group" aria-label="Status de ' + esc(e.nome) + '">' + ['livre', 'ocupado', 'fora'].map(s => '<button type="button" data-colab="' + esc(e.id) +
        '" data-st="' + s + '" aria-pressed="' + (e.status === s) + '">' + AL.ponto(s) + s + '</button>').join('') + '</div></div>').join('')
      : vazio('Ninguém da equipe cadastrado.');
    const ext = extremo();
    voltaram = new Set(p.robo.map(r => r.lead_id));
    $('av-robo-ajuda').textContent = 'Conversas das últimas ' + (p.conversa_ativa_h || 24) + ' h só com o assistente.';
    const col = (id, nid, lista, f, vaz) => { $(nid).textContent = lista.length; $(id).innerHTML = lista.length ? lista.map(x => f(x, ext)).join('') : vazio(vaz); };
    col('av-robo', 'av-robo-n', p.robo, cartoes.robo, 'Nenhuma conversa só com o robô agora.');
    const quenteP = ch => ch.nota === 'quente' ? 1 : 0;
    col('av-fila', 'av-fila-n', p.espera.slice().sort((a, b) => quenteP(b) - quenteP(a)), cartoes.espera, 'Ninguém esperando atendente.');
    col('av-atendendo', 'av-at-n', p.atendendo, cartoes.atendendo, 'Ninguém em atendimento agora.');
    col('av-encerrados', 'av-enc-n', p.encerrados, cartoes.encerrados, 'Nada encerrado hoje ainda.');
    $('nav-fila').hidden = !p.espera.length; $('nav-fila').textContent = p.espera.length;
    const atrasados = p.espera.filter(ch => ch.status === 'alerta' || ch.minutos > ext);
    $('av-alerta').innerHTML = alertaResposta(p.sem_resposta) + (atrasados.length ? alerta(atrasados.map(ch => ({nome: ch.lead_nome, minutos: ch.minutos})), false) : '') +
      (p.perfis_pendentes ? '<div class="alerta aten" role="status">' + ic('users') + '<p><strong>' + p.perfis_pendentes + (p.perfis_pendentes === 1 ? ' pedido' : ' pedidos') +
        ' de mudança de cadastro</strong> esperando sua aprovação.</p><button type="button" class="btn pri" data-ir="cadastros">Ver em Cadastros' + ic('arrow') + '</button></div>' : '');
  }
  function alerta(lista, comBotao) {
    const ext = extremo(), n = lista.length, pior = lista.slice().sort((a, b) => b.minutos - a.minutos)[0];
    return '<div class="alerta" role="alert">' + ic('alert') + '<p><strong>' + n + (n === 1 ? ' lead esperando' : ' leads esperando') + ' há mais de ' + esc(AL.dur(ext)) +
      '</strong> — ' + esc(pior.nome || 'Lead') + ', ' + esc(AL.dur(pior.minutos)) + '. Ninguém assumiu ainda.</p>' +
      (comBotao ? '<button type="button" class="btn pri" data-ir="aovivo">Ver na fila e transferir' + ic('arrow') + '</button>' : '') + '</div>';
  }

  // ---------- Hoje ----------
  function regua(a) {
    const ts = a.tempos || [], imed = a.imediato_min, ext = a.extremo_min, maior = Math.max(a.maior_min || 0, ext + 1);
    const zonas = [[], [], []];
    ts.forEach((t, i) => {
      let z, x;
      if (t <= imed) { z = 0; x = imed ? t / imed : 0.5; }
      else if (t <= ext) { z = 1; x = (t - imed) / (ext - imed); }
      else { z = 2; x = maior > ext ? (t - ext) / (maior - ext) : 0.5; }
      zonas[z].push({t, x: 6 + Math.min(1, Math.max(0, x)) * 88, y: [30, 62, 46][zonas[z].length % 3]});
    });
    const pts = z => zonas[z].map(p => '<i class="pt" style="left:' + p.x.toFixed(1) + '%;top:' + p.y + '%" title="' + esc(AL.dur(p.t)) + '"></i>').join('');
    // linha da média, na faixa onde ela cai
    const m = a.media_min || 0;
    let mz = 0, mx = 0;
    if (m <= imed) mx = imed ? m / imed : 0; else if (m <= ext) { mz = 1; mx = (m - imed) / (ext - imed); } else { mz = 2; mx = (m - ext) / (maior - ext); }
    const med = ts.length ? '<span class="med" style="left:' + (6 + Math.min(1, mx) * 88).toFixed(1) + '%"><span>média ' + esc(AL.dur(m)) + '</span></span>' : '';
    const zona = z => '<div class="z' + (z + 1) + '">' + pts(z) + (mz === z ? med : '') + '</div>';
    const pct = n => ts.length ? ' · ' + Math.round(n * 100 / ts.length) + '%' : '';
    return '<div class="painel regua-p"><div class="l1"><h2 style="margin:0">Tempo para assumir</h2><span class="sub">' +
      (ts.length ? ts.length + (ts.length === 1 ? ' chamado assumido hoje' : ' chamados assumidos hoje') + '. Cada ponto é um chamado, na faixa do tempo que levou para alguém assumir.'
        : 'Nenhum chamado assumido hoje ainda.') + '</span></div>' +
      '<div class="faixas"><div class="fx z1"><b>' + a.imediatos + '</b>Imediatos <span>até ' + esc(AL.dur(imed)) + pct(a.imediatos) + '</span></div>' +
      '<div class="fx z2"><b>' + a.medios + '</b>Médios <span>até ' + esc(AL.dur(ext)) + pct(a.medios) + '</span></div>' +
      '<div class="fx z3"><b>' + a.extremos + '</b>Extremos <span>acima de ' + esc(AL.dur(ext)) + pct(a.extremos) + '</span></div></div>' +
      '<div class="regua" role="img" aria-label="' + esc(a.imediatos + ' imediatos, ' + a.medios + ' médios, ' + a.extremos + ' extremos; média ' + AL.dur(m) + ', maior ' + AL.dur(a.maior_min)) + '">' +
      zona(0) + zona(1) + zona(2) + '</div>' +
      '<div class="eixo" aria-hidden="true"><span><em>0</em><em>' + esc(AL.dur(imed)) + '</em></span><span><em></em><em>' + esc(AL.dur(ext)) + '</em></span><span><em></em><em>maior do dia: ' +
      esc(AL.dur(a.maior_min)) + '</em></span></div></div>';
  }
  async function hoje() {
    const h = await api('GET', '/api/gestor/hoje');
    $('data').textContent = AL.ddmm(h.dia) + ' · até ' + AL.hm(h.agora);
    const a = h.assumir, ext = a.extremo_min;
    const g = h.grupos;
    voltaram = new Set(g.robo.map(r => r.lead_id));
    const atrasados = g.espera.filter(ch => ch.status === 'alerta' || ch.minutos > ext);
    const met = (rot, v) => '<div><dt>' + esc(rot) + '</dt><dd>' + esc(v) + '</dd></div>';
    $('hoje').innerHTML = alertaResposta(g.sem_resposta) + (atrasados.length ? alerta(atrasados.map(ch => ({nome: ch.lead_nome, minutos: ch.minutos})), true) : '') + regua(a) +
      '<dl class="painel metricas">' + met('Leads novos', h.leads_novos) + met('Chamados abertos', h.chamados_abertos) + met('Assumidos', h.assumidos) +
      met('Vendas', h.vendas) + met('Valor vendido', AL.brl(h.valor_vendido)) + met('Abertos agora', h.abertos_agora) +
      met('Média p/ assumir', AL.dur(h.tempo_medio_assumir_min)) + met('Maior espera', AL.dur(a.maior_min)) +
      met('Robô conversando na espera (média)', h.tempos && h.tempos.espera_robo_media_min != null ? AL.dur(h.tempos.espera_robo_media_min) : '—') +
      met('Espera sem resposta (média)', h.tempos && h.tempos.espera_sem_resposta_media_min != null ? AL.dur(h.tempos.espera_sem_resposta_media_min) : '—') +
      met('1ª resposta humana (média)', h.tempos && h.tempos.primeira_resposta_media_min != null ? AL.dur(h.tempos.primeira_resposta_media_min) : '—') + '</dl>' +
      '<h2 class="bloco">Por pessoa</h2><div class="painel tab"><table><thead><tr><th>Colaborador</th><th class="num">Assumidos</th><th class="num">Imediatos</th><th class="num">Médios</th>' +
      '<th class="num">Extremos</th><th class="num">Maior espera</th><th class="num">Vendas</th><th class="num">Valor</th></tr></thead><tbody>' +
      h.por_colaborador.map(p => '<tr><td><strong>' + esc(p.nome) + '</strong></td><td class="num">' + p.assumidos + '</td><td class="num">' + p.assumir.imediatos +
        '</td><td class="num">' + p.assumir.medios + '</td><td class="num">' + (p.assumir.extremos ? '<span class="selo st-perdido">' + p.assumir.extremos + '</span>' : 0) +
        '</td><td class="num">' + esc(AL.dur(p.assumir.maior_min)) + '</td><td class="num">' + p.vendas + '</td><td class="num">' + esc(AL.brl(p.valor)) + '</td></tr>').join('') +
      '</tbody></table></div>' +
      '<h2 class="bloco">Agora</h2><div class="grupos-hoje">' + grupoHoje('Robô atendendo', 'spark', g.robo, cartoes.robo, ext, 'Nenhuma conversa só com o robô.') +
      grupoHoje('Esperando atendente', 'inbox', g.espera, cartoes.espera, ext, 'Ninguém esperando.') +
      grupoHoje('Em atendimento', 'msg', g.atendendo, cartoes.atendendo, ext, 'Ninguém em atendimento.') +
      grupoHoje('Encerradas hoje', 'check', g.encerrados, cartoes.encerrados, ext, 'Nada encerrado hoje ainda.') + '</div>' +
      '<h2 class="bloco">Leads de hoje</h2><div class="painel tab" id="hoje-leads">' + (h.leads_hoje.length ? tabelaLeads(h.leads_hoje, 'hoje-leads') : vazio('Nenhum lead hoje.')) + '</div>';
  }

  function grupoHoje(titulo, icone, lista, f, ext, vaz) {
    return '<details class="painel grupo"' + (lista.length ? ' open' : '') + '><summary>' + ic(icone) + esc(titulo) + ' <span class="cont leve">' + lista.length + '</span></summary>' +
      (lista.length ? lista.map(x => f(x, ext)).join('') : vazio(vaz)) + '</details>';
  }

  // Tabela de leads: clicar no título ordena; 2º clique inverte (o resto da ordem é a "por nível" do servidor).
  const SITUACAO = {robo: 'robô atendendo', espera: 'esperando atendente', atendendo: 'em atendimento', encerrado: 'encerrado', parado: 'sem conversa ativa'};
  const NIVEL = {em_atendimento: 0, retornar: 1, negociando: 2, novo: 3, ganho: 4, perdido: 5, invalido: 6};
  const NOTA = {quente: 0, morno: 1, frio: 2};
  const SIT_ORD = {espera: 0, atendendo: 1, robo: 2, encerrado: 3, parado: 4};
  const COLS = [
    ['nome', 'Lead', l => l.nome || null], ['situacao', 'Situação', l => SIT_ORD[l.situacao] ?? 9], ['status', 'Status', l => NIVEL[l.status] ?? 9],
    ['nota', 'Nota', l => NOTA[l.nota] ?? 9], ['telefone', 'Telefone', l => l.telefone || ''], ['colaborador', 'Colaborador', l => l.colaborador ? nomeColab(l.colaborador) : null],
    ['resultado', 'Resultado', l => AL.RESULTADO[l.resultado] || l.resultado || null], ['contato', 'Último contato', l => l.minutos_desde_contato ?? 1e12, 'num'],
    ['conversa', 'Conversa', l => l.minutos_conversa || 0, 'num']];
  const tabelas = {}, ordemTab = {};
  function corContato(m) { return m == null ? '' : m < 60 ? 'c-agora' : m < 1440 ? 'c-hoje' : m < 10080 ? 'c-semana' : 'c-velho'; }
  function tabelaLeads(ls, onde) {
    tabelas[onde] = ls;
    const o = ordemTab[onde];
    let lista = ls;
    if (o) { const col = COLS.find(c => c[0] === o.campo); lista = ls.map((l, i) => [l, i]).sort((x, y) => { const a = col[2](x[0]), b = col[2](y[0]);
      if (a == null || b == null) return a == null && b == null ? x[1] - y[1] : a == null ? 1 : -1;  // vazio sempre no fim
      const d = typeof a === 'string' ? a.localeCompare(b, 'pt-BR', {sensitivity: 'base'}) : (a < b ? -1 : a > b ? 1 : 0);
      return d ? d * o.dir : x[1] - y[1]; }).map(x => x[0]); }
    const th = c => { const at = o && o.campo === c[0];
      return '<th' + (c[3] ? ' class="num"' : '') + (at ? ' aria-sort="' + (o.dir > 0 ? 'ascending' : 'descending') + '"' : '') + '><button type="button" class="ord" data-ord="' + c[0] + '" data-tab="' + onde + '">' +
        esc(c[1]) + '<span aria-hidden="true">' + (at ? (o.dir > 0 ? ' ▲' : ' ▼') : ' ↕') + '</span></button></th>'; };
    return '<table class="ordenavel"><thead><tr>' + COLS.map(th).join('') + '<th><span class="sr">Ação</span></th></tr></thead><tbody>' +
      lista.map(l => '<tr class="clic" data-linha="' + l.id + '"><td><strong>' + esc(l.nome || 'sem nome') + '</strong> <span class="mut peq">#' + l.id + '</span></td>' +
        '<td><span class="sit s-' + esc(l.situacao) + '">' + esc(SITUACAO[l.situacao] || l.situacao || '—') + '</span></td><td>' + AL.selo(l.status) +
        (l.retornar_em ? ' <span class="mut peq">' + esc(AL.hora(l.retornar_em)) + '</span>' : '') + '</td><td>' + AL.nota(l.nota) + '</td><td class="nw">' + esc(AL.fone(l.telefone)) +
        '</td><td>' + esc(l.colaborador ? nomeColab(l.colaborador) : '—') + '</td><td>' + esc(AL.RESULTADO[l.resultado] || l.resultado || '—') +
        (l.valor ? ' · ' + esc(AL.brl(l.valor)) : '') + '</td><td class="num"><span class="contato ' + corContato(l.minutos_desde_contato) + '">' + esc(AL.ha(l.minutos_desde_contato) || '—') + '</span>' +
        (l.dia_anterior ? '<br><span class="mut peq">também em ' + esc(AL.ddmm(l.dia_anterior)) + '</span>' : '') + '</td><td class="num mut peq">' + (l.minutos_conversa ? esc(AL.dur(l.minutos_conversa)) : '—') +
        '</td><td><button type="button" class="btn peq" data-ficha="' + l.id + '">Ficha</button></td></tr>').join('') +
      '</tbody></table>';
  }
  function ordenarTab(onde, campo) {
    const o = ordemTab[onde];
    ordemTab[onde] = o && o.campo === campo ? (o.dir > 0 ? {campo, dir: -1} : null) : {campo, dir: 1};
    $(onde).innerHTML = tabelaLeads(tabelas[onde], onde);
    const bt = $(onde).querySelector('[data-ord="' + campo + '"]'); if (bt) bt.focus();
  }

  async function leads() {
    const q = new URLSearchParams();
    ['status', 'situacao', 'contato', 'colab', 'de', 'ate'].forEach(k => { const v = $('fl-' + k).value; if (v) q.set(k === 'colab' ? 'colaborador' : k, v); });
    const ls = await api('GET', '/api/gestor/leads?' + q);
    $('fl-total').textContent = ls.length + (ls.length === 1 ? ' lead' : ' leads') + ' · filtra ao mudar';
    $('leads').innerHTML = ls.length ? tabelaLeads(ls, 'leads') : vazio('Nenhum lead neste filtro.');
  }

  async function ficha(id) {
    const f = await api('GET', '/api/gestor/leads/' + id);
    const el = $('ficha');
    el.hidden = false;
    el.innerHTML = '<div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap"><h2 style="margin:0">' + esc(f.lead.nome || 'Lead') + ' <span class="mut peq">#' + f.lead.id + '</span></h2>' +
      AL.selo(f.lead.status) + AL.nota(f.lead.nota) + '<button type="button" class="btn sutil ic" data-fechar-ficha aria-label="Fechar ficha" style="margin-left:auto">' + ic('x') + '</button></div>' +
      '<p class="mut">' + esc(AL.fone(f.lead.telefone)) + (AL.tempos(f.lead) ? ' · ' + AL.tempos(f.lead) : '') + '</p>' +
      '<h3>Chamados</h3><div class="chs">' + (f.chamados.length ? f.chamados.map(ch => '<div><strong>#' + ch.id + '</strong> ' + esc(AL.MOTIVO[ch.motivo] || '') +
        ' <span class="selo st-' + esc(ch.status) + '">' + esc(AL.CHAMADO[ch.status] || ch.status) + '</span>' +
        (ch.resultado ? ' · ' + esc(AL.RESULTADO[ch.resultado] || ch.resultado) : '') + (ch.valor ? ' · ' + esc(AL.brl(ch.valor)) : '') + (ch.dono ? ' · ' + esc(nomeColab(ch.dono)) : '') +
        (ch.status === 'fechado' ? ' <button type="button" class="btn peq" data-reabrir="' + ch.id + '">' + ic('reopen') + 'Reabrir</button>' : '') + '</div>').join('') : '<p class="mut">Nenhum chamado.</p>') + '</div>' +
      '<h3>Mensagens</h3><div class="conv">' + (f.mensagens.map(m => AL.bolhaEquipe(m, f.lead.nome)).join('') || '<p class="mut">Sem mensagens.</p>') + '</div>';
    const cv = el.querySelector('.conv'); cv.scrollTop = 1e9;
    el.scrollIntoView({behavior: 'smooth', block: 'start'}); el.focus({preventScroll: true});
  }

  // ---------- Base de conhecimento ----------
  const CAMPOS = ['horario_atendimento', 'endereco', 'pagamento', 'entrega', 'garantia', 'site', 'observacoes'];
  let faqEd = [];
  const linhas = t => String(t || '').split('\n').map(x => x.trim()).filter(Boolean);
  function renderFaq() {
    $('faq-lista').innerHTML = faqEd.length ? faqEd.map((f, i) => '<div class="faq-item" data-faq="' + i + '">' +
      '<div class="l1"><h3>' + esc(f.id || 'nova') + '</h3><button type="button" class="btn perigo peq" data-faq-rm="' + i + '">' + ic('trash') + 'Remover</button></div>' +
      '<div class="grade2"><label class="campo">Formas da pergunta (uma por linha) <textarea data-faq-perg="' + i + '" rows="3">' + esc((f.perguntas || []).join('\n')) + '</textarea></label>' +
      '<label class="campo">Resposta <textarea data-faq-resp="' + i + '" rows="3">' + esc(f.resposta || '') + '</textarea></label></div></div>').join('')
      : vazio('Nenhuma pergunta ainda.');
  }
  function lerFaq() {
    document.querySelectorAll('[data-faq-perg]').forEach(t => { faqEd[+t.dataset.faqPerg].perguntas = linhas(t.value); });
    document.querySelectorAll('[data-faq-resp]').forEach(t => { faqEd[+t.dataset.faqResp].resposta = t.value.trim(); });
  }
  function novoId(lista, prefixo) {
    let n = lista.length + 1, id;
    do { id = prefixo + n++; } while (lista.some(f => f.id === id));
    return id;
  }
  function addFaq(perguntas, resposta) {
    lerFaq(); faqEd.push({id: novoId(faqEd, 'faq-'), perguntas: perguntas || [], resposta: resposta || ''}); renderFaq(); sujoBase = true;
    const ult = document.querySelector('[data-faq="' + (faqEd.length - 1) + '"]');
    if (ult) { ult.scrollIntoView({behavior: 'smooth', block: 'center'}); ult.querySelector('textarea').focus(); }
  }
  function camposCuradoria() {
    const t = $('c-tipo').value;
    if (t === 'anthropic' && !$('c-modelo').value) { $('c-modelo').value = 'claude-opus-5-5'; }
    document.querySelector('[data-cur=modelo]').hidden = !t || t === 'regras';
    document.querySelector('[data-cur=esforco]').hidden = t !== 'anthropic';
    document.querySelector('[data-cur=url]').hidden = !['ollama', 'openai'].includes(t);
  }
  function camposCerebro() {
    const t = $('b-tipo').value;
    document.querySelector('[data-cer=modelo]').hidden = t === 'regras';
    document.querySelector('[data-cer=esforco]').hidden = t !== 'anthropic';
    document.querySelector('[data-cer=url]').hidden = !['ollama', 'openai'].includes(t);
    $('b-modelo').placeholder = {anthropic: 'claude-sonnet-5-5', openrouter: 'anthropic/claude-sonnet-5.5', claude_cli: 'sonnet',
      codex_cli: 'gpt-6-luna', ollama: 'qwen3', openai: 'gpt-x'}[t] || '';
  }
  async function base() {
    cfg = await api('GET', '/api/gestor/config');
    sujoBase = false;
    const info = cfg.info || {};
    CAMPOS.forEach(k => { $('i-' + k).value = info[k] || ''; });
    $('i-horario-gerado').textContent = 'Vazio = gerado dos horários dos Cadastros.';
    faqEd = JSON.parse(JSON.stringify(cfg.faq || [])); renderFaq();
    const c = cfg.cerebro || {tipo: 'regras'};
    $('b-tipo').value = c.tipo || 'regras'; $('b-modelo').value = c.modelo || ''; $('b-esforco').value = c.esforco || 'low'; $('b-url').value = c.url || '';
    camposCerebro();
    const k = cfg.cerebro_curadoria || {};
    $('c-tipo').value = k.tipo || ''; $('c-modelo').value = k.modelo || ''; $('c-esforco').value = k.esforco || 'medium'; $('c-url').value = k.url || '';
    camposCuradoria();
    try {
      const s = await AL.api('GET', '/api/saude');
      $('b-saude').textContent = 'Agora no servidor: ' + s.cerebro + (s.cerebro_ok ? ' · ligado' : ' · desligado — ' + (s.cerebro_motivo || '') + ' (respondendo por regras)');
      const cu = s.cerebro_curadoria || {};
      $('c-saude').textContent = 'Curadoria agora: ' + (cu.propria ? cu.tipo + (cu.modelo ? ' · ' + cu.modelo : '') + (cu.esforco ? ' · ' + cu.esforco : '') : 'usa o cérebro do agente') + (cu.ok ? ' · ligado' : ' · desligado — ' + (cu.motivo || '') + ' (propostas por regras)');
    } catch (e) { $('b-saude').textContent = ''; }
  }
  async function salvarBase() {
    lerFaq();
    const info = {}; CAMPOS.forEach(k => { info[k] = $('i-' + k).value.trim(); });
    const t = $('b-tipo').value, cer = {tipo: t};
    if (t !== 'regras' && $('b-modelo').value.trim()) cer.modelo = $('b-modelo').value.trim();
    if (t === 'anthropic') cer.esforco = $('b-esforco').value;
    if (['ollama', 'openai'].includes(t)) cer.url = $('b-url').value.trim();
    const ct = $('c-tipo').value, cur = {};
    if (ct) {
      cur.tipo = ct;
      if (ct !== 'regras' && $('c-modelo').value.trim()) cur.modelo = $('c-modelo').value.trim();
      if (ct === 'anthropic') cur.esforco = $('c-esforco').value;
      if (['ollama', 'openai'].includes(ct)) cur.url = $('c-url').value.trim();
    }
    const faq = faqEd.filter(f => f.perguntas.length || f.resposta);
    if (faq.some(f => !f.perguntas.length || !f.resposta)) throw new Error('Cada pergunta do FAQ precisa de ao menos uma forma e de uma resposta.');
    cfg = await api('PUT', '/api/gestor/config', Object.assign({}, cfg, {token_gestor: '***', info, faq, cerebro: cer, cerebro_curadoria: cur}));
    sujoBase = false; aviso('Base de conhecimento salva.'); await base();
  }

  // ---------- Aprendizado ----------
  const ORIGEM = {sugestao_ok: 'sugestão sem editar', sugestao_editada: 'sugestão editada', livre: 'livre'};
  let aprItens = [];
  async function aprendizado() {
    const q = new URLSearchParams();
    if ($('a-de').value) q.set('de', $('a-de').value);
    if ($('a-ate').value) q.set('ate', $('a-ate').value);
    if ($('a-colab').value) q.set('colaborador', $('a-colab').value);
    if ($('a-origem').value) q.set('origem', $('a-origem').value);
    const r = await api('GET', '/api/gestor/aprendizado?' + q);
    aprItens = r.itens;
    $('a-periodo').value = r.periodo;
    const k = r.contadores;
    $('a-contadores').innerHTML = '<div class="painel pad resumo"><strong style="font-family:var(--titulo)">' + k.total + (k.total === 1 ? ' resposta registrada' : ' respostas registradas') + '</strong>' +
      (k.com_sugestao ? '<div class="prop" role="img" aria-label="' + esc(k.pct_ok + '% enviadas como estavam, ' + k.pct_editadas + '% editadas, ' + k.pct_ignoradas + '% ignoradas') + '">' +
        '<div class="z1" style="flex:' + k.sugestao_ok + '"></div><div class="z2" style="flex:' + k.sugestao_editada + '"></div><div class="z3" style="flex:' + k.ignoradas + '"></div></div>' : '') +
      '<span>Sugestão da IA: <strong>' + k.pct_ok + '%</strong> enviada sem editar · <strong>' + k.pct_editadas + '%</strong> editada · <strong>' + k.pct_ignoradas + '%</strong> ignorada · ' +
      (k.livre - k.ignoradas) + ' livres (sem sugestão)</span></div>';
    $('a-itens').innerHTML = aprItens.length ? '<table><thead><tr><th>Quando</th><th>Cliente disse</th><th>Sugestão da IA</th><th>Vendedor mandou</th><th>Origem</th><th class="num">Diferença</th><th><span class="sr">Ação</span></th></tr></thead><tbody>' +
      aprItens.map((i, ix) => '<tr><td class="peq">' + esc(AL.hora(i.em)) + '<br>' + esc(i.colaborador_nome || nomeColab(i.colaborador)) + '</td><td>' + esc(i.msg_lead) +
        '</td><td>' + (i.sugestao ? esc(i.sugestao) : '<span class="mut">—</span>') + '</td><td>' + esc(i.enviado) + '</td><td><span class="selo">' + esc(ORIGEM[i.origem] || i.origem) +
        '</span></td><td class="num">' + (i.distancia == null ? '—' : Math.round(i.distancia * 100) + '%') + '</td><td><button type="button" class="btn peq" data-virar="' + ix + '">' + ic('plus') + 'Virar FAQ</button></td></tr>').join('') + '</tbody></table>'
      : vazio('Nenhum registro neste filtro.');
    await propostas();
  }
  let propLista = [];
  async function propostas() {
    const ps = await api('GET', '/api/gestor/propostas');
    propLista = ps;
    const novas = ps.filter(p => p.status === 'nova'), velhas = ps.filter(p => p.status !== 'nova').slice(0, 10);
    const TIPO = {faq: 'FAQ novo', info: 'informação do negócio', correcao: 'correção do FAQ', preco: 'preço de produto', produto: 'produto novo', horario: 'horário de atendimento'};
    const ORIG = {cerebro: 'pelo cérebro da curadoria', regras: 'pelas regras', vendedor: 'pedido do vendedor', fonte: 'de link ou arquivo',
      chat: 'do chat da base', gestor: 'escrita pelo gestor'};
    const nomeProd = id => { const x = (cfg && cfg.produtos || []).find(p => p.id === id); return x ? x.nome : id; };
    $('a-propostas').innerHTML = (novas.length ? novas.map(p => '<div class="proposta" data-prop="' + p.id + '"><div class="l1">' +
      '<label class="sel-prop"><input type="checkbox" data-sel="' + p.id + '"' + (selecionadas.has(p.id) ? ' checked' : '') + '><span class="sr">Selecionar a proposta</span></label><h3>#' + p.id + ' · ' +
      esc(TIPO[p.tipo] || p.tipo) + (p.campo ? ' · ' + esc(p.campo) : '') + (p.faq_id ? ' · ' + esc(p.faq_id) : '') + (p.produto_id ? ' · ' + esc(nomeProd(p.produto_id)) : '') +
      '</h3><span class="selo">' + esc(ORIG[p.origem] || p.origem) + '</span>' + (p.contradiz ? '<span class="selo contradiz">' + ic('alert') + 'contradiz a base</span>' : '') + '</div>' +
      (p.fonte ? '<p class="de-fonte">Fonte: ' + linkFonte(p.fonte) + '</p>' : '') +
      (p.evidencia ? '<blockquote class="evid" aria-label="Trecho que comprova">' + esc(p.evidencia) + '</blockquote>' : '') +
      (p.destino ? '<p class="destino"><strong>Vai alterar:</strong> ' + esc(p.destino) + '</p>' : '') +
      (p.justificativa ? '<p class="mut" style="white-space:pre-wrap">Para o gestor (não vai para a base): ' + esc(p.justificativa) + '</p>' : '') + '<div class="grade2">' +
      (p.tipo === 'produto'
        ? '<label class="campo">Nome <input data-prop-nome="' + p.id + '" value="' + esc(p.nome) + '"></label>' +
          '<label class="campo">Preço <input data-prop-preco="' + p.id + '" value="' + esc(p.preco_novo) + '" placeholder="R$ 0,00"></label>' +
          '<label class="campo">Palavras (vírgula) <input data-prop-pal="' + p.id + '" value="' + esc((p.palavras || []).join(', ')) + '"></label>'
        : p.tipo === 'horario'
        ? '<label class="campo">Horários (um dia por linha: seg 08:00-18:00; vazio = fechado) <textarea rows="4" data-prop-hor="' + p.id + '">' +
          esc(Object.keys(p.horarios || {}).map(d => d + ' ' + (p.horarios[d] || []).map(j => j[0] + '-' + j[1]).join(', ')).join('\n')) + '</textarea></label>' +
          '<label class="campo">Texto para o cliente (opcional) <textarea rows="2" data-prop-resp="' + p.id + '">' + esc(p.resposta) + '</textarea></label>'
        : p.tipo === 'preco'
        ? '<label class="campo">Preço novo <input data-prop-preco="' + p.id + '" value="' + esc(p.preco_novo) + '" placeholder="R$ 670"></label>' +
          '<label class="campo">Promoção (opcional) <input data-prop-promo="' + p.id + '" value="' + esc(p.promocao) + '" placeholder="Promoção Black"></label>' +
          '<label class="campo">Válida até (opcional) <input type="date" data-prop-val="' + p.id + '" value="' + esc(p.validade) + '"></label>'
        : (p.tipo !== 'info' ? '<label class="campo">Perguntas (uma por linha) <textarea rows="3" data-prop-perg="' + p.id + '">' + esc((p.perguntas || []).join('\n')) + '</textarea></label>' : '') +
          '<label class="campo">Texto que vai para a base (como o cliente vai ler) <textarea rows="3" data-prop-resp="' + p.id + '">' + esc(p.resposta) + '</textarea></label>') +
      '</div><div class="previa" data-prop-previa="' + p.id + '" hidden></div>' +
      '<div class="acoes"><button type="button" class="btn pri" data-incorporar="' + p.id + '">' + ic('plus') + 'Revisar e incorporar</button><button type="button" class="btn sutil" data-descartar="' + p.id + '">Descartar</button></div></div>').join('')
      : vazio('Nenhuma proposta nova.')) +
      (velhas.length ? '<p class="vazio peq">Já tratadas: ' + velhas.map(p => '#' + p.id + ' ' + esc(p.status)).join(' · ') + '</p>' : '');
    selecionadas.forEach(id => { if (!novas.some(p => p.id === id)) selecionadas.delete(id); });
    $('a-lote').hidden = novas.length < 2; $('a-lote-previa').hidden = true; contarLote();
  }
  const selecionadas = new Set();
  const linkFonte = f => /^https?:\/\//i.test(f) ? '<a href="' + esc(f) + '" target="_blank" rel="noopener noreferrer">' + esc(f) + '</a>' : esc(f);
  function contarLote() {
    const n = selecionadas.size;
    $('a-lote-btn').disabled = !n;
    $('a-lote-n').textContent = n ? n + (n === 1 ? ' proposta marcada.' : ' propostas marcadas.') : 'Marque as propostas que quer incorporar de uma vez.';
  }
  function previaLote() {
    const ids = propLista.filter(p => selecionadas.has(p.id) && p.status === 'nova').map(p => p.id);
    $('a-lote-previa').hidden = false;
    $('a-lote-previa').innerHTML = '<h3 style="margin:0">Prévia: ' + ids.length + (ids.length === 1 ? ' proposta vai' : ' propostas vão') + ' para a base</h3><ol>' +
      ids.map(id => { const p = propLista.find(x => x.id === id);
        return '<li><strong>#' + id + '</strong> · ' + esc(p.destino || '') + '<div class="previa">' + esc(previaProposta(id)) + '</div></li>'; }).join('') + '</ol>' +
      '<div class="acoes"><button type="button" class="btn pri" id="a-lote-ok">' + ic('check') + 'Confirmar incorporação (' + ids.length + ')</button>' +
      '<button type="button" class="btn sutil" id="a-lote-cancelar">Cancelar</button></div>';
    $('a-lote-previa').scrollIntoView({behavior: 'smooth', block: 'nearest'});
  }
  async function incorporarLote() {
    const ids = propLista.filter(p => selecionadas.has(p.id) && p.status === 'nova').map(p => p.id);
    const r = await api('POST', '/api/gestor/propostas/incorporar-lote', {itens: ids.map(id => Object.assign({id}, corpoProposta(id)))});
    selecionadas.clear();
    aviso(r.incorporadas.length + ' incorporada(s)' + (r.erros.length ? '; ' + r.erros.length + ' não: ' + r.erros.map(e => '#' + e.id + ' ' + e.erro).join(' · ') : '') + '.', !!r.erros.length);
    await recarregarCfg(); await propostas();
  }
  function corpoProposta(id) {
    const q = k => document.querySelector('[data-prop-' + k + '="' + id + '"]'), corpo = {};
    if (q('resp')) corpo.resposta = q('resp').value;
    if (q('perg')) corpo.perguntas = linhas(q('perg').value);
    if (q('preco')) corpo.preco_novo = q('preco').value.trim();
    if (q('promo')) { corpo.promocao = q('promo').value.trim(); corpo.validade = q('val').value; }
    if (q('nome')) { corpo.nome = q('nome').value.trim(); corpo.palavras = q('pal').value.split(',').map(x => x.trim()).filter(Boolean); }
    if (q('hor')) {
      corpo.horarios = {};
      linhas(q('hor').value).forEach(l => { const m = l.trim().split(/\s+/), d = m.shift();
        corpo.horarios[d] = m.join(' ').split(',').map(x => x.trim()).filter(Boolean).map(x => x.split(/\s*[-–]\s*/)); });
    }
    return corpo;
  }
  // Prévia: como o alvo da base fica depois de incorporar (info acrescenta uma linha; preço troca o do produto).
  function previaProposta(id) {
    const p = propLista.find(x => String(x.id) === String(id)), b = corpoProposta(id);
    if (!p) return '';
    if (p.tipo === 'preco') {
      const promo = b.promocao || b.validade;
      return 'Antes: ' + (p.atual || '—') + '\nDepois: ' + (b.preco_novo || '?') + (promo ? ' (' + (b.promocao || 'promoção') + (b.validade ? ' até ' + b.validade.split('-').reverse().slice(0, 2).join('/') : '') + '; o preço normal continua valendo depois)' : '');
    }
    if (p.tipo === 'produto') return 'Cadastros → Produtos → novo: ' + (b.nome || '?') + ' — ' + (b.preco_novo || 'sem preço') + ' · palavras: ' + (b.palavras || []).join(', ');
    if (p.tipo === 'horario') return 'Antes: ' + (p.atual || '—') + '\nDepois: ' + Object.keys(b.horarios || {}).map(d => d + ' ' + ((b.horarios[d] || []).map(j => j.join('–')).join(' e ') || 'fechado')).join('; ');
    if (p.tipo === 'info') return 'Como fica ' + p.campo + ':\n' + ((p.atual ? p.atual + '\n' : '') + (b.resposta || '').trim());
    if (p.tipo === 'correcao') return 'Antes: ' + (p.atual || '—') + '\nDepois: ' + (b.resposta || '').trim();
    return 'P: ' + (b.perguntas || []).join(' / ') + '\nR: ' + (b.resposta || '').trim();
  }

  // A configuração muda por incorporar/importar/salvar: relê do servidor para nenhuma aba gravar um cfg velho.
  async function recarregarCfg() {
    cfg = await api('GET', '/api/gestor/config');
    if (typeof preencherColabs === 'function' && cfg.equipe) preencherColabs();
    return cfg;
  }

  // ---------- Base consolidada ----------
  const ROT_INFO = {endereco: 'Endereço', pagamento: 'Formas de pagamento', entrega: 'Entrega', garantia: 'Garantia e trocas', site: 'Site', observacoes: 'Observações'};
  async function consolidada() {
    const d = await api('GET', '/api/gestor/base'), s = d.secoes;
    $('bc-texto').textContent = d.texto;
    $('bc-conflitos').innerHTML = '<h3 style="margin:0 0 6px">' + (d.conflitos.length ? d.conflitos.length + ' conflito(s)' : 'Nenhum conflito encontrado') + '</h3>' +
      (d.conflitos.length ? '<ul class="lista-conf">' + d.conflitos.map((x, i) => '<li data-conf="' + esc(x.tipo) + '" data-conf-i="' + i + '">' + ic('alert') + '<span>' + esc(x.mensagem) +
        '</span> <button type="button" class="btn peq" data-editar="' + esc(x.alvo) + '">editar</button></li>').join('') + '</ul>' : '');
    const bloco = (t, h) => '<fieldset class="painel form-sec"><legend>' + esc(t) + '</legend>' + h + '</fieldset>';
    $('bc-secoes').innerHTML =
      bloco('Negócio e horário', '<p><strong>' + esc(s.negocio) + '</strong></p><p>' + esc(s.horario) + '</p>') +
      bloco('Informações', Object.keys(s.info).filter(k => s.info[k]).map(k => '<p><strong>' + esc(ROT_INFO[k] || k) + ':</strong> <span style="white-space:pre-wrap">' + esc(s.info[k]) + '</span></p>').join('') || vazio('Nenhuma informação.')) +
      bloco('Perguntas frequentes', s.faq.map(f => '<p><strong>' + esc(f.perguntas.join(' / ')) + '</strong><br>' + esc(f.resposta) + '</p>').join('') || vazio('Nenhuma pergunta.')) +
      bloco('Produtos', s.produtos.map(p => '<p><strong>' + esc(p.nome) + '</strong>: ' + esc(p.preco_vigente || 'sem preço informado') +
        (p.preco_promocao && !p.promocao_ativa ? ' <span class="mut">(promoção ' + esc(p.preco_promocao) + ' vencida)</span>' : '') + '</p>').join('') || vazio('Nenhum produto.'));
  }
  async function baixar(rota, nome) {
    const r = await fetch(rota, {headers: {'X-Token': token}});
    if (!r.ok) throw new Error('Erro ' + r.status);
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement('a'); a.href = url; a.download = nome; a.click(); URL.revokeObjectURL(url);
  }
  let importando = null;
  async function previaImportar(json) {
    importando = json;
    const r = await api('POST', '/api/gestor/base/importar', json);
    $('bc-importar').hidden = false;
    $('bc-importar').innerHTML = '<h3 style="margin:0 0 6px">Prévia da importação: ' + (r.mudancas.length ? r.mudancas.length + ' mudança(s)' : 'nada muda') + '</h3>' +
      r.mudancas.map(m => '<div class="previa"><strong>' + esc(m.onde) + '</strong>\nAntes: ' + esc(m.antes || '—') + '\nDepois: ' + esc(m.depois || '(removido)') + '</div>').join('') +
      '<div class="acoes">' + (r.mudancas.length ? '<button type="button" class="btn pri" id="bc-aplicar">' + ic('check') + 'Gravar na base</button>' : '') +
      '<button type="button" class="btn sutil" id="bc-cancelar">Cancelar</button></div>';
  }
  async function irPara(alvo) {
    const [tipo, id] = [alvo.slice(0, alvo.indexOf(':')), alvo.slice(alvo.indexOf(':') + 1)];
    if (tipo === 'produto') { await mostrar('cadastros'); const el = document.querySelector('[data-pr][data-k="preco"]'); if (el) el.focus(); return; }
    await mostrar('base');
    let el = null;
    if (tipo === 'info') el = $('i-' + id);
    if (tipo === 'faq') { const i = faqEd.findIndex(f => f.id === id); el = i >= 0 ? document.querySelector('[data-faq-resp="' + i + '"]') : null; }
    if (el) { el.scrollIntoView({behavior: 'smooth', block: 'center'}); el.focus(); }
  }

  // ---------- Cadastros (formulário) ----------
  const DIAS = [['seg', 'Segunda'], ['ter', 'Terça'], ['qua', 'Quarta'], ['qui', 'Quinta'], ['sex', 'Sexta'], ['sab', 'Sábado'], ['dom', 'Domingo']];
  const PRAZOS = [['oferta_min', 'Oferta: tempo para aceitar', 2], ['alerta_quente_min', 'Alerta de lead quente', 2], ['alerta_normal_min', 'Alerta de lead normal', 5],
    ['lembrete_min', 'Lembrete de atendimento parado', 30], ['assumir_imediato_min', 'Imediato até', 1], ['assumir_extremo_min', 'Extremo acima de', 10], ['conversa_ativa_h', 'Conversa ativa por (horas)', 24]];
  let eqEd = [], prEd = [], horEd = {}, sujo = false;
  const marcarSujo = () => { sujo = true; $('c-estado').textContent = 'Alterações não salvas.'; };
  const slug = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'item';
  function idUnico(base, lista) { let id = base, n = 2; while (lista.some(x => x.id === id)) id = base + '-' + n++; return id; }
  function gerarCodigo() {
    const abc = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789', v = new Uint32Array(16);
    crypto.getRandomValues(v); return Array.from(v, x => abc[x % abc.length]).join('');
  }
  function renderEquipe() {
    $('c-equipe').innerHTML = '<div class="linha-f eq-linha cab"><span class="lbl">Nome</span><span class="lbl">Telefone (WhatsApp)</span><span class="lbl">Código de acesso</span><span></span></div>' +
      (eqEd.length ? eqEd.map((m, i) => '<div class="linha-f eq-linha">' +
        '<label class="campo"><span class="sr">Nome</span><input data-eq="' + i + '" data-k="nome" value="' + esc(m.nome) + '" placeholder="Nome" aria-label="Nome"></label>' +
        '<label class="campo"><span class="sr">Telefone</span><input data-eq="' + i + '" data-k="telefone" value="' + esc(m.telefone || '') + '" inputmode="tel" placeholder="5541999990000" aria-label="Telefone de ' + esc(m.nome) + '"></label>' +
        '<div class="cod"><input type="password" data-eq="' + i + '" data-k="codigo" value="' + esc(m.codigo || '') + '" autocomplete="off" aria-label="Código de acesso de ' + esc(m.nome) + '">' +
        '<button type="button" class="btn ic" data-ver="' + i + '" aria-label="Mostrar código" title="Mostrar código">' + ic('eye') + '</button>' +
        '<button type="button" class="btn peq" data-gerar="' + i + '" title="Gerar um código novo">' + ic('refresh') + 'Gerar novo</button></div>' +
        '<button type="button" class="btn sutil ic" data-eq-rm="' + i + '" aria-label="Remover ' + esc(m.nome) + '" title="Remover">' + ic('trash') + '</button></div>').join('')
        : vazio('Ninguém na equipe.'));
  }
  function renderProdutos() {
    $('c-produtos').innerHTML = '<div class="linha-f pr-linha cab"><span class="lbl">Nome</span><span class="lbl">Preço</span><span class="lbl">Palavras que indicam interesse</span><span></span></div>' +
      (prEd.length ? prEd.map((p, i) => '<div class="linha-f pr-linha">' +
        '<input data-pr="' + i + '" data-k="nome" value="' + esc(p.nome) + '" placeholder="Nome do produto" aria-label="Nome do produto">' +
        '<input data-pr="' + i + '" data-k="preco" value="' + esc(p.preco || '') + '" placeholder="R$ 0,00" aria-label="Preço de ' + esc(p.nome) + '">' +
        '<input class="pal" data-pr="' + i + '" data-k="palavras" value="' + esc(Array.isArray(p.palavras) ? p.palavras.join(', ') : String(p.palavras || '')) + '" placeholder="mensal, mês, plano" aria-label="Palavras de ' + esc(p.nome) + '">' +
        '<button type="button" class="btn sutil ic" data-pr-rm="' + i + '" aria-label="Remover ' + esc(p.nome) + '" title="Remover">' + ic('trash') + '</button></div>').join('')
        : vazio('Nenhum produto.'));
  }
  function renderHorarios() {
    $('c-horarios').innerHTML = DIAS.map(([d, nome]) => '<div class="linha-f dia-l"><span class="lbl" style="padding-top:10px">' + nome + '</span><div class="janelas">' +
      (horEd[d] || []).map((j, k) => '<span class="janela"><input type="time" data-hor="' + d + '" data-j="' + k + '" data-p="0" value="' + esc(j[0]) + '" aria-label="' + nome + ' início">' +
        '<span aria-hidden="true">–</span><input type="time" data-hor="' + d + '" data-j="' + k + '" data-p="1" value="' + esc(j[1]) + '" aria-label="' + nome + ' fim">' +
        '<button type="button" class="btn sutil ic" data-hor-rm="' + d + '" data-j="' + k + '" aria-label="Remover janela de ' + nome + '">' + ic('x') + '</button></span>').join('') +
      ((horEd[d] || []).length ? '' : '<span class="mut peq">fechado</span>') +
      '<button type="button" class="btn sutil peq" data-hor-add="' + d + '">' + ic('plus') + 'Janela</button></div></div>').join('');
  }
  function renderPrazos() {
    const pz = cfg.prazos || {};
    $('c-prazos').innerHTML = PRAZOS.map(([k, rot, pad]) => '<label class="campo">' + rot + ' <input type="number" min="1" step="1" inputmode="numeric" id="pz-' + k + '" value="' +
      esc(pz[k] != null ? pz[k] : pad) + '"></label>').join('');
    previaPrazos();
    const rb = cfg.robo || {};
    $('c-robo-assume').checked = !!rb.assume_espera; $('c-robo-min').value = rb.apos_min || 10;
    const al = cfg.alertas || {};
    $('c-bip-quente').checked = !!al.bip_quente; $('c-bip-s').value = al.bip_s || 20;
    $('c-perfil-livre').checked = !!(cfg.permissoes || {}).perfil_sem_aprovacao;
  }
  function previaPrazos() {
    const im = $('pz-assumir_imediato_min').value, ex = $('pz-assumir_extremo_min').value;
    $('c-prazos-previa').textContent = 'Faixas da aba Hoje: imediato até ' + im + ' min · médio até ' + ex + ' min · extremo acima de ' + ex + ' min.' +
      (+im >= +ex ? ' O "imediato" precisa ser menor que o "extremo".' : '');
  }
  // contraste (prévia; quem decide é o servidor)
  function lum(h) { return [1, 3, 5].map(i => { const v = parseInt(h.slice(i, i + 2), 16) / 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); })
    .reduce((s, v, i) => s + v * [.2126, .7152, .0722][i], 0); }
  const razao = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  function previaCor() {
    const c = $('c-cor').value.trim();
    if (!c) { $('c-cor-pick').value = '#facc15'; $('c-cor-previa').innerHTML = 'Sem cor própria: o chat usa o amarelo do tema.'; return; }
    if (!/^#[0-9a-fA-F]{6}$/.test(c)) { $('c-cor-previa').innerHTML = '<span class="erro">Use o formato #RRGGBB.</span>'; return; }
    const [t, r] = [['#1a1206', razao(c, '#1a1206')], ['#ffffff', razao(c, '#ffffff')]].sort((a, b) => b[1] - a[1])[0];
    $('c-cor-pick').value = c.toLowerCase();
    $('c-cor-previa').innerHTML = '<span class="amostra" style="background:' + esc(c) + ';color:' + t + '">' + ic('send') + 'Botão Enviar</span> ' +
      (r >= 4.5 ? 'Contraste ' + r.toFixed(1).replace('.', ',') + ':1 — passa (AA).' : '<span class="erro">Contraste ' + r.toFixed(1).replace('.', ',') + ':1 — abaixo de 4,5:1; o servidor vai recusar.</span>');
  }
  async function cadastros() {
    cfg = await api('GET', '/api/gestor/config');
    $('c-nome').value = cfg.nome || ''; $('c-urlpub').value = cfg.url_publica || '';
    const ap = cfg.aparencia || {};
    $('c-tema').value = ap.tema || 'claro'; $('c-cor').value = ap.cor_destaque || ''; $('c-nome-exibido').value = ap.nome_exibido || '';
    previaCor();
    eqEd = JSON.parse(JSON.stringify(cfg.equipe || [])); prEd = JSON.parse(JSON.stringify(cfg.produtos || []));
    horEd = JSON.parse(JSON.stringify(cfg.horarios || {}));
    renderEquipe(); renderProdutos(); renderHorarios(); renderPrazos();
    sujo = false; $('c-estado').textContent = 'Nenhuma alteração.';
    await perfis();
  }
  // 1.10.8: pedidos de mudança de cadastro da equipe (nome/telefone)
  async function perfis(lista) {
    const ls = lista || await api('GET', '/api/gestor/perfis');
    $('perfis-sec').hidden = !ls.length; $('perfis-n').textContent = ls.length;
    const linha = (rot, de, para) => para == null ? '' : '<p>' + rot + ': <span class="de">' + esc(de || '—') + '</span> → <strong>' + esc(para || '(sem telefone)') + '</strong></p>';
    $('c-perfis').innerHTML = ls.map(x => '<div class="it"><div class="l1"><strong>' + esc(x.atual.nome || x.colaborador) + '</strong><span class="dir">pediu ' + esc(AL.hm(x.em)) + '</span></div>' +
      linha('Nome', x.atual.nome, x.dados.nome) + linha('Telefone', AL.fone(x.atual.telefone), x.dados.telefone != null ? AL.fone(x.dados.telefone) : null) +
      '<div class="acao"><button type="button" class="btn pri peq" data-perfil="' + x.id + '" data-aprovar="1">' + ic('check') + 'Aprovar</button>' +
      '<button type="button" class="btn sutil peq" data-perfil="' + x.id + '" data-aprovar="0">Recusar</button></div></div>').join('');
  }
  $('c-perfis').addEventListener('click', async ev => {
    const b = ev.target.closest('[data-perfil]'); if (!b) return;
    const aprovar = b.dataset.aprovar === '1';
    let motivo = null;
    if (!aprovar) { motivo = prompt('Motivo da recusa (opcional, a pessoa vê):', ''); if (motivo === null) return; }
    try {
      await perfis(await api('POST', '/api/gestor/perfis/' + b.dataset.perfil, {aprovar, motivo}));
      // a equipe mudou no servidor: traz nome/telefone novos, mas não apaga o que o gestor está editando e ainda não salvou
      lerCadastros();
      const novo = await api('GET', '/api/gestor/config');
      (novo.equipe || []).forEach(m => {
        const e = eqEd.find(x => x.id === m.id), o = (cfg.equipe || []).find(x => x.id === m.id);
        if (e && o) ['nome', 'telefone'].forEach(k => { if (String(e[k] ?? '') === String(o[k] ?? '')) e[k] = m[k]; });
      });
      cfg.equipe = novo.equipe; cfg._versao = novo._versao; renderEquipe(); preencherColabs();
      aviso(aprovar ? 'Cadastro aprovado.' : 'Pedido recusado.');
    } catch (e) { aviso(e.message, true); }
  });
  function lerCadastros() {
    document.querySelectorAll('[data-eq]').forEach(el => { eqEd[+el.dataset.eq][el.dataset.k] = el.value; });
    document.querySelectorAll('[data-pr]').forEach(el => { prEd[+el.dataset.pr][el.dataset.k] = el.value; });
    document.querySelectorAll('[data-hor]').forEach(el => { horEd[el.dataset.hor][+el.dataset.j][+el.dataset.p] = el.value; });
  }
  async function salvarCadastros() {
    lerCadastros();
    const equipe = [], produtos = [];
    eqEd.forEach(m => {
      const n = Object.assign({}, m, {nome: String(m.nome || '').trim(), telefone: String(m.telefone || '').replace(/\D/g, ''), codigo: String(m.codigo || '').trim()});
      if (!n.id) n.id = idUnico(slug(n.nome), equipe.concat(eqEd.filter(x => x.id)));
      equipe.push(n);
    });
    prEd.forEach(p => {
      const pal = Array.isArray(p.palavras) ? p.palavras : String(p.palavras || '').split(',').map(x => x.trim()).filter(Boolean);
      const n = Object.assign({}, p, {nome: String(p.nome || '').trim(), palavras: pal});
      if (String(p.preco || '').trim()) n.preco = String(p.preco).trim(); else delete n.preco;
      if (!n.id) n.id = idUnico(slug(n.nome), produtos.concat(prEd.filter(x => x.id)));
      produtos.push(n);
    });
    const prazos = Object.assign({}, cfg.prazos);
    PRAZOS.forEach(([k]) => { const v = $('pz-' + k).value.trim(); prazos[k] = /^\d+$/.test(v) ? parseInt(v, 10) : v; });
    const aparencia = {tema: $('c-tema').value};
    if ($('c-cor').value.trim()) aparencia.cor_destaque = $('c-cor').value.trim();
    if ($('c-nome-exibido').value.trim()) aparencia.nome_exibido = $('c-nome-exibido').value.trim();
    const novo = Object.assign({}, cfg, {nome: $('c-nome').value.trim(), url_publica: $('c-urlpub').value.trim(), token_gestor: '***',
      equipe, produtos, horarios: horEd, prazos, aparencia,
      robo: {assume_espera: $('c-robo-assume').checked, apos_min: /^\d+$/.test($('c-robo-min').value.trim()) ? parseInt($('c-robo-min').value, 10) : $('c-robo-min').value},
      alertas: {bip_quente: $('c-bip-quente').checked, bip_s: /^\d+$/.test($('c-bip-s').value.trim()) ? parseInt($('c-bip-s').value, 10) : $('c-bip-s').value},
      permissoes: Object.assign({}, cfg.permissoes, {perfil_sem_aprovacao: $('c-perfil-livre').checked})});
    cfg = await api('PUT', '/api/gestor/config', novo);
    try { localStorage.setItem('al_tema_negocio', aparencia.tema); if (!localStorage.getItem('al_tema')) AL.aplicarTema(aparencia.tema); } catch (e) { /* */ }
    aviso('Cadastros salvos.'); await cadastros(); preencherColabs();
    $('negocio-nav').textContent = cfg.nome;
  }

  // ---------- abas ----------
  async function mostrar(nova) {
    if (nova && nova !== aba && aba === 'cadastros' && sujo && !confirm('Há alterações não salvas em Cadastros. Sair mesmo assim?')) return;
    const trocou = !!nova;
    aba = nova || aba;
    document.querySelectorAll('[role=tab]').forEach(b => { const on = b.dataset.aba === aba; b.setAttribute('aria-selected', String(on)); b.tabIndex = on ? 0 : -1; });
    document.querySelectorAll('[data-painel]').forEach(s => { s.hidden = s.dataset.painel !== aba; });
    $('titulo').textContent = TITULOS[aba];
    if (trocou && !['aovivo', 'hoje'].includes(aba)) $('data').textContent = '';
    try {
      if (aba === 'aovivo') await aoVivo();
      if (aba === 'hoje') await hoje();
      if (aba === 'leads' && trocou) await leads();
      if (aba === 'cadastros' && trocou) await cadastros();
      if (aba === 'base' && trocou) { await base(); await carregarFontes(); }
      if (aba === 'aprendizado' && trocou) await aprendizado();
      if (aba === 'consolidada' && trocou) await consolidada();
    } catch (e) { aviso(e.message, true); }
  }
  function preencherColabs() {
    const ops = '<option value="">Todos</option>' + cfg.equipe.map(m => '<option value="' + esc(m.id) + '">' + esc(m.nome) + '</option>').join('');
    const a = $('fl-colab').value, b = $('a-colab').value;
    $('fl-colab').innerHTML = ops; $('a-colab').innerHTML = ops; $('fl-colab').value = a; $('a-colab').value = b;
  }

  const CHAVE = 'al_token_gestor';
  async function entrar(valor, lembrar) {
    token = valor;
    try {
      cfg = await api('GET', '/api/gestor/config');
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      preencherColabs();
      $('negocio-nav').textContent = cfg.nome; $('logo').textContent = AL.iniciais(cfg.nome);
      $('login').hidden = true; $('painel').hidden = false;
      mostrar('aovivo'); timer = setInterval(() => { if (aba === 'aovivo' || aba === 'hoje') mostrar(); }, 10000);
    } catch (e) {
      token = null; localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE);
      $('erro-login').textContent = e.status === 401 ? 'Token inválido.' : e.message;
    }
  }
  $('form-login').addEventListener('submit', ev => {
    ev.preventDefault();
    const v = $('token').value; $('token').value = '';
    entrar(v, $('lembrar').checked);
  });
  $('sair').addEventListener('click', () => { localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE); location.reload(); });
  { const salvo = sessionStorage.getItem(CHAVE) || localStorage.getItem(CHAVE);
    if (salvo) entrar(salvo, !!localStorage.getItem(CHAVE)); }

  const tabs = Array.from(document.querySelectorAll('[role=tab]'));
  tabs.forEach(b => b.addEventListener('click', () => mostrar(b.dataset.aba)));
  document.querySelector('.nav').addEventListener('keydown', ev => {
    const i = tabs.indexOf(document.activeElement); if (i < 0) return;
    const d = {ArrowDown: 1, ArrowRight: 1, ArrowUp: -1, ArrowLeft: -1}[ev.key]; if (!d) return;
    ev.preventDefault(); const n = tabs[(i + d + tabs.length) % tabs.length]; n.focus(); mostrar(n.dataset.aba);
  });
  ['fl-status', 'fl-situacao', 'fl-contato', 'fl-colab', 'fl-de', 'fl-ate'].forEach(id => $(id).addEventListener('change', () => leads().catch(e => aviso(e.message, true))));
  $('form-filtro').addEventListener('submit', ev => { ev.preventDefault(); leads().catch(e => aviso(e.message, true)); });
  ['a-de', 'a-ate', 'a-colab', 'a-origem'].forEach(id => $(id).addEventListener('change', () => aprendizado().catch(e => aviso(e.message, true))));
  $('form-apr').addEventListener('submit', ev => { ev.preventDefault(); aprendizado().catch(e => aviso(e.message, true)); });

  document.body.addEventListener('click', async ev => {
    const linha = ev.target.closest('tr[data-linha]');
    const b = ev.target.closest('button');
    if (!b && linha) { ev.preventDefault(); if (aba !== 'leads') await mostrar('leads'); ficha(linha.dataset.linha).catch(e => aviso(e.message, true)); return; }
    if (!b) return;
    if (b.dataset.ord) { ordenarTab(b.dataset.tab, b.dataset.ord); return; }
    if (b.dataset.atribuir) {
      const sel = document.querySelector('[data-atrib-sel="' + b.dataset.atribuir + '"]');
      if (!sel || !sel.value) { aviso('Escolha para quem passar.', true); return; }
      try { await api('POST', '/api/gestor/leads/' + b.dataset.atribuir + '/atribuir', {colaborador: sel.value}); aviso('Conversa passada para ' + nomeColab(sel.value) + '.'); await mostrar(); }
      catch (e) { aviso(e.message, true); }
      return;
    }
    if (b.dataset.roboColab) {
      const ativo = b.getAttribute('aria-pressed') !== 'true';
      try { await api('POST', '/api/gestor/equipe/' + encodeURIComponent(b.dataset.roboColab) + '/robo', {ativo}); await aoVivo(); }
      catch (e) { aviso(e.message, true); }
      return;
    }
    try {
      if (b.dataset.ir) await mostrar(b.dataset.ir);
      if (b.dataset.st) { await api('POST', '/api/gestor/equipe/' + encodeURIComponent(b.dataset.colab) + '/status', {status: b.dataset.st}); await aoVivo(); }
      if (b.dataset.transf) {
        const sel = document.querySelector('[data-transf-sel="' + b.dataset.transf + '"]');
        if (!sel || !sel.value) { aviso('Escolha para quem transferir.', true); if (sel) sel.focus(); return; }
        if (!confirm('Transferir o chamado #' + b.dataset.transf + ' para ' + nomeColab(sel.value) + '?')) return;
        await api('POST', '/api/gestor/chamados/' + b.dataset.transf + '/transferir', {colaborador: sel.value});
        aviso('Chamado #' + b.dataset.transf + ' transferido para ' + nomeColab(sel.value) + '.'); await aoVivo();
      }
      if (b.dataset.ficha) { if (aba !== 'leads') await mostrar('leads'); await ficha(b.dataset.ficha); }
      if (b.hasAttribute('data-fechar-ficha')) $('ficha').hidden = true;
      if (b.dataset.reabrir) {
        if (!confirm('Reabrir o chamado #' + b.dataset.reabrir + '? Ele volta para a fila.')) return;
        await api('POST', '/api/gestor/chamados/' + b.dataset.reabrir + '/reabrir', {}); aviso('Chamado reaberto: voltou para a fila.');
      }
      if (b.dataset.faqRm) { lerFaq(); faqEd.splice(+b.dataset.faqRm, 1); renderFaq(); sujoBase = true; }
      if (b.dataset.virar) {
        const i = aprItens[+b.dataset.virar];
        await mostrar('base'); addFaq(linhas(i.msg_lead), i.enviado); aviso('Revise a pergunta e a resposta e clique em Salvar base de conhecimento.');
      }
      if (b.dataset.incorporar) {
        const id = b.dataset.incorporar, pv = document.querySelector('[data-prop-previa="' + id + '"]');
        if (pv.hidden) {  // 1º clique: mostra a prévia; o 2º confirma
          pv.textContent = previaProposta(id); pv.hidden = false; b.lastChild.textContent = 'Confirmar incorporação';
          return;
        }
        await api('POST', '/api/gestor/propostas/' + id + '/incorporar', corpoProposta(id)); aviso('Proposta #' + id + ' incorporada à base.');
        await recarregarCfg(); await propostas();
      }
      if (b.dataset.descartar) { await api('POST', '/api/gestor/propostas/' + b.dataset.descartar + '/descartar', {}); aviso('Proposta descartada.'); await propostas(); }
      // cadastros
      if (b.dataset.ver) {
        const inp = document.querySelector('[data-eq="' + b.dataset.ver + '"][data-k="codigo"]'), mostra = inp.type === 'password';
        inp.type = mostra ? 'text' : 'password'; b.innerHTML = ic(mostra ? 'eyeoff' : 'eye'); b.setAttribute('aria-label', mostra ? 'Esconder código' : 'Mostrar código');
      }
      if (b.dataset.gerar) {
        const inp = document.querySelector('[data-eq="' + b.dataset.gerar + '"][data-k="codigo"]');
        inp.value = gerarCodigo(); inp.type = 'text'; marcarSujo();
        aviso('Código novo gerado. Salve e passe à pessoa; o código antigo deixa de valer.');
      }
      if (b.dataset.eqRm) { lerCadastros(); if (confirm('Remover ' + (eqEd[+b.dataset.eqRm].nome || 'esta pessoa') + ' da equipe?')) { eqEd.splice(+b.dataset.eqRm, 1); renderEquipe(); marcarSujo(); } }
      if (b.id === 'eq-add') { lerCadastros(); eqEd.push({nome: '', telefone: '', codigo: gerarCodigo()}); renderEquipe(); marcarSujo();
        const ult = document.querySelectorAll('[data-k="nome"][data-eq]'); ult[ult.length - 1].focus(); }
      if (b.dataset.prRm) { lerCadastros(); prEd.splice(+b.dataset.prRm, 1); renderProdutos(); marcarSujo(); }
      if (b.id === 'pr-add') { lerCadastros(); prEd.push({nome: '', palavras: []}); renderProdutos(); marcarSujo();
        const ult = document.querySelectorAll('[data-k="nome"][data-pr]'); ult[ult.length - 1].focus(); }
      if (b.dataset.horAdd) { lerCadastros(); (horEd[b.dataset.horAdd] = horEd[b.dataset.horAdd] || []).push(['08:00', '18:00']); renderHorarios(); marcarSujo(); }
      if (b.dataset.horRm) { lerCadastros(); horEd[b.dataset.horRm].splice(+b.dataset.j, 1); renderHorarios(); marcarSujo(); }
      if (b.id === 'c-cor-limpar') { $('c-cor').value = ''; previaCor(); marcarSujo(); }
    } catch (e) { aviso(e.message, true); }
  });
  $('p-cadastros').addEventListener('input', ev => {
    marcarSujo();
    if (ev.target.id === 'c-cor') previaCor();
    if (ev.target.id === 'c-cor-pick') { $('c-cor').value = ev.target.value.toUpperCase(); previaCor(); }
    if (ev.target.id && ev.target.id.startsWith('pz-assumir')) previaPrazos();
  });
  $('p-cadastros').addEventListener('change', ev => { if (ev.target.id === 'c-tema') marcarSujo(); });
  $('salvar').addEventListener('click', ev => {
    ev.target.closest('button').disabled = true;
    salvarCadastros().catch(e => aviso('Não salvou: ' + e.message, true)).finally(() => { $('salvar').disabled = false; });
  });
  window.addEventListener('beforeunload', ev => { if (sujo && aba === 'cadastros') { ev.preventDefault(); ev.returnValue = ''; } });
  $('faq-add').addEventListener('click', () => { addFaq(); sujoBase = true; });
  $('b-tipo').addEventListener('change', camposCerebro);
  $('c-tipo').addEventListener('change', camposCuradoria);
  $('a-propostas').addEventListener('input', ev => {  // prévia aberta acompanha a edição
    const card = ev.target.closest('[data-prop]'); if (!card) return;
    const pv = card.querySelector('[data-prop-previa]'); if (pv && !pv.hidden) pv.textContent = previaProposta(card.dataset.prop);
    const p = propLista.find(x => String(x.id) === card.dataset.prop), dst = card.querySelector('.destino');
    if (p && p.tipo === 'preco' && dst) {  // o destino acompanha: com promoção vai para o preço promocional
      const b = corpoProposta(p.id), pr = (cfg.produtos || []).find(x => x.id === p.produto_id) || {};
      dst.innerHTML = '<strong>Vai alterar:</strong> ' + esc('Cadastros → Produtos → ' + (pr.nome || p.produto_id) + (b.promocao || b.validade
        ? ' → preço promocional: ' + (pr.preco_promocao || '—') + ' → ' + b.preco_novo + ' (' + (b.promocao || 'promoção') + (b.validade ? ' até ' + b.validade : '') + '); preço normal ' + (pr.preco || '—') + ' fica'
        : ' → preço: ' + (pr.preco || '—') + ' → ' + b.preco_novo));
    }
  });
  $('salvar-base').addEventListener('click', () => salvarBase().catch(e => aviso(e.message, true)));
  $('form-testar').addEventListener('submit', async ev => {
    ev.preventDefault();
    $('t-resultado').innerHTML = '<p class="mut">Testando…</p>';
    try {
      const r = await api('POST', '/api/gestor/testar', {texto: $('t-texto').value});
      $('t-resultado').innerHTML = '<div class="b lead"><small>Cliente</small>' + esc($('t-texto').value) + '</div>' +
        (r.respostas.length ? r.respostas.map(t => '<div class="b ia"><small>' + ic('spark') + 'Assistente (IA)</small>' + esc(t) + '</div>').join('') : '<p class="mut">(o agente não responderia nada)</p>') +
        (r.chamado ? '<p class="sep">Abriria um chamado: ' + esc(AL.MOTIVO[r.chamado] || r.chamado) + '</p>' : '');
    } catch (e) { $('t-resultado').innerHTML = '<p class="erro">' + esc(e.message) + '</p>'; }
  });
  $('a-periodo-salvar').addEventListener('click', async () => {
    try { await recarregarCfg(); cfg = await api('PUT', '/api/gestor/config', Object.assign({}, cfg, {token_gestor: '***', aprendizado: {periodo: $('a-periodo').value}})); aviso('Período salvo.'); }
    catch (e) { aviso(e.message, true); }
  });
  $('a-gerar').addEventListener('click', async ev => {
    const b = ev.target.closest('button'); b.disabled = true;
    try { const r = await api('POST', '/api/gestor/propostas/gerar', {de: $('a-de').value || undefined, ate: $('a-ate').value || undefined});
      aviso(r.criadas ? r.criadas + ' proposta(s) nova(s).' : 'Nenhuma proposta nova no período.'); await propostas(); }
    catch (e) { aviso(e.message, true); } finally { b.disabled = false; }
  });
  $('bc-md').addEventListener('click', () => baixar('/api/gestor/base.md', 'base.md').catch(e => aviso(e.message, true)));
  $('bc-json').addEventListener('click', () => baixar('/api/gestor/base.json', 'base.json').catch(e => aviso(e.message, true)));
  $('bc-arquivo').addEventListener('change', async ev => {
    const f = ev.target.files[0]; ev.target.value = ''; if (!f) return;
    try { await previaImportar(JSON.parse(await f.text())); } catch (e) { aviso(e.message || 'Arquivo inválido', true); }
  });
  $('p-consolidada').addEventListener('click', async ev => {
    const b = ev.target.closest('button'); if (!b) return;
    try {
      if (b.dataset.editar) await irPara(b.dataset.editar);
      if (b.id === 'bc-cancelar') { importando = null; $('bc-importar').hidden = true; }
      if (b.id === 'bc-aplicar' && importando) {
        const r = await api('POST', '/api/gestor/base/importar?aplicar=1', importando);
        importando = null; $('bc-importar').hidden = true; await recarregarCfg(); aviso('Base importada (' + r.mudancas.length + ' mudança(s); backup ' + r.backup + ').'); await consolidada();
      }
    } catch (e) { aviso(e.message, true); }
  });
  // ---------- Importar de link ou arquivo (1.7.8) ----------
  const ST_FONTE = {lendo: 'lendo', analisando: 'analisando', pronto: 'pronto', erro: 'erro'};
  let tFontes = null, fontesAtivas = new Set();
  const n = (v, um, varios) => v + ' ' + (v === 1 ? um : varios);
  function detalheFonte(f) {
    if (f.status === 'lendo') return f.tipo === 'link' ? 'lendo as páginas…' : 'lendo o arquivo…';
    if (f.status === 'erro') return esc(f.erro || 'não deu para ler');
    const base = (f.tipo === 'link' ? n(f.paginas, 'página', 'páginas') + ' · ' : '') + (f.caracteres ? f.caracteres.toLocaleString('pt-BR') + ' caracteres' : 'documento');
    if (f.status === 'analisando') return esc(base) + ' · propondo itens para a base…';
    const av = (f.avisos || []).filter(a => !/^propostas pel/.test(a));
    return esc(base + ' · ' + n(f.propostas, 'proposta', 'propostas')) +
      (av.length ? ' · <span title="' + esc(av.join('\n')) + '">' + n(av.length, 'aviso', 'avisos') + '</span>' : '') +
      (f.propostas ? ' <button type="button" class="btn peq" data-ir="aprendizado">Revisar no Aprendizado' + ic('arrow') + '</button>' : '');
  }
  async function carregarFontes() {
    const r = await api('GET', '/api/gestor/base/fontes');
    $('fo-tipos').textContent = 'TXT, MD, CSV, HTML, DOCX ou PDF, até 10 MB.' +
      (r.pdf.anthropic || r.pdf.pdftotext ? '' : ' PDF só com o cérebro da curadoria Anthropic ou o pdftotext no servidor.');
    $('fo-lista').innerHTML = r.fontes.slice(0, 8).map(f => '<div class="fonte-it">' + ic(f.tipo === 'link' ? 'link' : 'file') +
      '<span class="nome" title="' + esc(f.fonte) + '">' + esc(f.fonte) + '</span><span class="selo st-' + esc(f.status) + '">' + esc(ST_FONTE[f.status] || f.status) + '</span>' +
      '<span class="det' + (f.status === 'erro' ? ' erro' : '') + '">' + detalheFonte(f) + '</span></div>').join('');
    r.fontes.forEach(f => {
      if (fontesAtivas.has(f.id) && (f.status === 'pronto' || f.status === 'erro')) {
        fontesAtivas.delete(f.id);
        aviso(f.status === 'pronto' ? f.fonte + ': ' + n(f.propostas, 'proposta nova', 'propostas novas') + ' no Aprendizado.' : f.fonte + ': ' + (f.erro || 'erro'), f.status === 'erro');
      }
      if (f.status === 'lendo' || f.status === 'analisando') fontesAtivas.add(f.id);
    });
    clearTimeout(tFontes);
    if (fontesAtivas.size && aba === 'base') tFontes = setTimeout(() => carregarFontes().catch(() => {}), 1500);
  }
  $('form-fonte').addEventListener('submit', async ev => {
    ev.preventDefault();
    const b = $('fo-ler'); b.disabled = true;
    try {
      const r = await api('POST', '/api/gestor/base/fonte', {url: $('fo-url').value.trim(), max_paginas: parseInt($('fo-max').value, 10) || 8});
      fontesAtivas.add(r.fonte.id); $('fo-url').value = ''; aviso('Lendo o site. As propostas aparecem no Aprendizado.'); await carregarFontes();
    } catch (e) { aviso(e.message, true); } finally { b.disabled = false; }
  });
  $('fo-arquivo').addEventListener('change', async ev => {
    const f = ev.target.files[0]; ev.target.value = ''; if (!f) return;
    if (f.size > 10 * 1024 * 1024) { aviso('Arquivo maior que 10 MB.', true); return; }
    try {
      const dados = await new Promise((ok, falha) => { const l = new FileReader(); l.onload = () => ok(String(l.result).split(',')[1] || ''); l.onerror = falha; l.readAsDataURL(f); });
      const r = await api('POST', '/api/gestor/base/arquivo', {nome: f.name, conteudo_base64: dados});
      fontesAtivas.add(r.fonte.id); aviso('Lendo ' + f.name + '. As propostas aparecem no Aprendizado.'); await carregarFontes();
    } catch (e) { aviso(e.message, true); }
  });

  // ---------- Chat da base (1.7.8): só o que está na base, com a seção citada; nada é gravado ----------
  let chatHist = [], chatProp = null;
  function desenharChat() {
    if (!chatHist.length) return;
    $('bc-conv').innerHTML = chatHist.map((m, i) => {
      if (m.de === 'gestor') return '<div class="b eu"><small>Você</small>' + esc(m.texto) + '</div>';
      if (m.carregando) return '<div class="b lead"><small>' + ic('book') + 'Base</small>Procurando na base…</div>';
      const r = m.r || {};
      return '<div class="b lead"><small>' + ic('book') + 'Base' + (r.origem === 'regras' ? ' · busca por palavras' : '') + '</small>' + esc(m.texto) +
        (r.fontes && r.fontes.length ? '<ul class="fontes-b">' + r.fontes.map(f => '<li><strong>' + esc(f.secao) + '</strong> — ' + esc(f.trecho) + '</li>').join('') + '</ul>' : '') +
        (r.contradicao || (r.conflitos && r.conflitos.length) ? '<div class="contra">' + esc(r.contradicao || 'Há conflito na base sobre isso.') + ' ' +
          (r.conflitos || []).map(x => '<button type="button" class="btn peq" data-conf-ir="' + x.indice + '">' + ic('alert') + 'ver conflito</button>').join(' ') + '</div>' : '') +
        (r.lacuna ? '<div class="acao-b"><button type="button" class="btn peq pri" data-criar-prop="' + i + '">' + ic('plus') + 'Criar proposta</button></div>' : '') + '</div>';
    }).join('');
    $('bc-conv').scrollTop = 1e9;
  }
  const TIPO_FORM = {faq: 'Pergunta do FAQ', info: 'Informação do negócio', produto: 'Produto novo', preco: 'Preço de produto'};
  function formProposta(p) {
    chatProp = Object.assign({tipo: 'faq', perguntas: [], resposta: '', campo: 'observacoes', nome: '', preco_novo: '', produto_id: '', palavras: []}, p);
    const t = chatProp.tipo, prods = (cfg && cfg.produtos) || [];
    const campos = {faq: '<label class="campo">Perguntas (uma por linha) <textarea id="np-perg" rows="2">' + esc(chatProp.perguntas.join('\n')) + '</textarea></label>' +
        '<label class="campo">Resposta (como o cliente vai ler) <textarea id="np-resp" rows="3">' + esc(chatProp.resposta) + '</textarea></label>',
      info: '<label class="campo">Campo <select id="np-campo">' + Object.keys(ROT_INFO).map(k => '<option value="' + k + '"' + (k === chatProp.campo ? ' selected' : '') + '>' + esc(ROT_INFO[k]) + '</option>').join('') + '</select></label>' +
        '<label class="campo">Texto (como o cliente vai ler) <textarea id="np-resp" rows="3">' + esc(chatProp.resposta) + '</textarea></label>',
      produto: '<div class="grade2"><label class="campo">Nome <input id="np-nome" value="' + esc(chatProp.nome) + '"></label><label class="campo">Preço <input id="np-preco" value="' + esc(chatProp.preco_novo) + '" placeholder="R$ 0,00"></label></div>' +
        '<label class="campo">Palavras que indicam interesse (vírgula) <input id="np-pal" value="' + esc((chatProp.palavras || []).join(', ')) + '"></label>',
      preco: '<div class="grade2"><label class="campo">Produto <select id="np-prod">' + prods.map(x => '<option value="' + esc(x.id) + '"' + (x.id === chatProp.produto_id ? ' selected' : '') + '>' + esc(x.nome) + '</option>').join('') + '</select></label>' +
        '<label class="campo">Preço novo <input id="np-preco" value="' + esc(chatProp.preco_novo) + '" placeholder="R$ 670"></label></div>'};
    $('bc-prop').hidden = false;
    $('bc-prop').innerHTML = '<h3 style="margin:0">Nova proposta para a base</h3><p class="mut peq" style="margin:0">Revise e complete: ela vai para a aba Aprendizado e só entra na base quando você incorporar.</p>' +
      '<label class="campo">Tipo <select id="np-tipo">' + Object.keys(TIPO_FORM).map(k => '<option value="' + k + '"' + (k === t ? ' selected' : '') + '>' + TIPO_FORM[k] + '</option>').join('') + '</select></label>' +
      campos[t] + '<div class="acoes"><button type="button" class="btn pri" id="np-criar">' + ic('plus') + 'Criar proposta</button><button type="button" class="btn sutil" id="np-cancelar">Cancelar</button></div>';
    const foco = $('np-resp') || $('np-nome') || $('np-preco'); if (foco) foco.focus();
  }
  function lerFormProposta() {
    const v = id => $(id) ? $(id).value : undefined, o = {tipo: $('np-tipo').value, origem: 'chat'};
    if (v('np-perg') !== undefined) o.perguntas = linhas(v('np-perg'));
    if (v('np-resp') !== undefined) o.resposta = v('np-resp').trim();
    if (v('np-campo') !== undefined) o.campo = v('np-campo');
    if (v('np-nome') !== undefined) o.nome = v('np-nome').trim();
    if (v('np-preco') !== undefined) o.preco_novo = v('np-preco').trim();
    if (v('np-prod') !== undefined) o.produto_id = v('np-prod');
    if (v('np-pal') !== undefined) o.palavras = v('np-pal').split(',').map(x => x.trim()).filter(Boolean);
    return o;
  }
  $('form-chat').addEventListener('submit', async ev => {
    ev.preventDefault();
    const q = $('bc-pergunta').value.trim(); if (!q) return;
    const historico = chatHist.filter(m => !m.carregando).slice(-6).map(m => ({de: m.de, texto: m.texto}));
    chatHist.push({de: 'gestor', texto: q}); const pend = {de: 'base', carregando: true}; chatHist.push(pend);
    $('bc-pergunta').value = ''; desenharChat();
    try {
      const r = await api('POST', '/api/gestor/base/perguntar', {pergunta: q, historico});
      Object.assign(pend, {carregando: false, texto: r.resposta, r, pergunta: q});
    } catch (e) { Object.assign(pend, {carregando: false, texto: 'Não consegui perguntar: ' + e.message, r: {}}); }
    desenharChat();
  });
  $('bc-chat').addEventListener('change', ev => { if (ev.target.id === 'np-tipo') formProposta(Object.assign(lerFormProposta(), {tipo: ev.target.value})); });
  $('bc-chat').addEventListener('click', async ev => {
    const b = ev.target.closest('button'); if (!b) return;
    try {
      if (b.dataset.criarProp) { const m = chatHist[+b.dataset.criarProp]; formProposta(Object.assign({perguntas: [m.pergunta]}, m.r.proposta || {})); }
      if (b.id === 'np-cancelar') { $('bc-prop').hidden = true; chatProp = null; }
      if (b.id === 'np-criar') {
        const r = await api('POST', '/api/gestor/propostas', lerFormProposta());
        $('bc-prop').hidden = true; chatProp = null;
        aviso('Proposta #' + r.proposta.id + ' criada. Revise e incorpore na aba Aprendizado.');
      }
      if (b.dataset.confIr !== undefined) {
        const li = document.querySelector('#bc-conflitos [data-conf-i="' + b.dataset.confIr + '"]');
        if (li) { document.querySelectorAll('#bc-conflitos li.foco').forEach(x => x.classList.remove('foco')); li.classList.add('foco');
          li.scrollIntoView({behavior: 'smooth', block: 'center'}); const e = li.querySelector('button'); if (e) e.focus({preventScroll: true}); }
      }
    } catch (e) { aviso(e.message, true); }
  });

  // ---------- Atualizar (1.7.8): relê a configuração e a aba atual, sem sair; pergunta antes de descartar o que não foi salvo ----------
  const CARREGAR = {aovivo: () => aoVivo(), hoje: () => hoje(), leads: () => leads(), base: async () => { await base(); await carregarFontes(); },
    consolidada: () => consolidada(), aprendizado: () => aprendizado(), cadastros: () => cadastros()};
  let atualizando = false;
  async function atualizar() {
    if (atualizando || !token) return;
    const pendente = (aba === 'cadastros' && sujo) || (aba === 'base' && sujoBase);
    if (pendente && !(await AL.confirmar('Há alterações não salvas nesta aba. Descartar alterações e atualizar?', 'Descartar e atualizar'))) return;
    atualizando = true;
    document.querySelectorAll('#atualizar,[data-atualizar]').forEach(x => { x.disabled = true; });
    try {
      await recarregarCfg();
      $('negocio-nav').textContent = cfg.nome; $('logo').textContent = AL.iniciais(cfg.nome);
      if (CARREGAR[aba]) await CARREGAR[aba]();
      $('atualizado').textContent = 'Atualizado às ' + AL.agoraHM();
      if (window.innerWidth < 1024) aviso($('atualizado').textContent + '.');
    } catch (e) { aviso(e.message, true); }
    finally { atualizando = false; document.querySelectorAll('#atualizar,[data-atualizar]').forEach(x => { x.disabled = false; }); }
  }
  $('atualizar').addEventListener('click', atualizar);
  document.querySelectorAll('[data-atualizar]').forEach(b => b.addEventListener('click', atualizar));
  AL.atalhoAtualizar(() => { if (!$('painel').hidden) atualizar(); });
  $('p-base').addEventListener('input', ev => { if (!ev.target.closest('#fonte-sec, #form-testar')) sujoBase = true; });
  $('p-base').addEventListener('change', ev => { if (ev.target.matches('select') && !ev.target.closest('#fonte-sec')) sujoBase = true; });
  $('a-propostas').addEventListener('change', ev => {
    const c = ev.target.closest('[data-sel]'); if (!c) return;
    if (c.checked) selecionadas.add(+c.dataset.sel); else selecionadas.delete(+c.dataset.sel);
    contarLote(); if (!$('a-lote-previa').hidden) previaLote();
  });
  $('a-lote-btn').addEventListener('click', previaLote);
  $('a-lote-previa').addEventListener('click', async ev => {
    const b = ev.target.closest('button'); if (!b) return;
    if (b.id === 'a-lote-cancelar') { $('a-lote-previa').hidden = true; return; }
    if (b.id === 'a-lote-ok') { b.disabled = true; try { await incorporarLote(); } catch (e) { aviso(e.message, true); b.disabled = false; } }
  });
  $('exportar').addEventListener('click', async () => {
    try {
      const r = await fetch('/api/gestor/exportar.csv', {headers: {'X-Token': token}});
      if (!r.ok) throw new Error('Erro ' + r.status);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a'); a.href = url; a.download = 'leads.csv'; a.click(); URL.revokeObjectURL(url);
      aviso('leads.csv baixado.');
    } catch (e) { aviso(e.message, true); }
  });
})();
