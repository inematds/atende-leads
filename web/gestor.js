// Painel do gestor: token na aba (sessionStorage) ou no aparelho (localStorage, se "lembrar").
(function () {
  const $ = id => document.getElementById(id);
  const ic = AL.ic, esc = AL.esc;
  let token = null, cfg = null, aba = 'aovivo', timer = null;
  const api = (m, r, c) => AL.api(m, r, c, {'X-Token': token});
  let tAviso = null;
  const aviso = (t, erro) => {
    const el = $('aviso'); el.textContent = t || ''; el.className = 'toast' + (erro ? ' erro' : '');
    clearTimeout(tAviso); if (t) tAviso = setTimeout(() => { el.textContent = ''; }, erro ? 8000 : 3500);
  };
  const TITULOS = {aovivo: 'Ao vivo', hoje: 'Hoje', leads: 'Leads', base: 'Base de conhecimento', aprendizado: 'Aprendizado', cadastros: 'Cadastros', exportar: 'Exportar'};
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
      '<div class="seg" role="group" aria-label="Status de ' + esc(e.nome) + '">' + ['livre', 'ocupado', 'fora'].map(s => '<button type="button" data-colab="' + esc(e.id) +
        '" data-st="' + s + '" aria-pressed="' + (e.status === s) + '">' + AL.ponto(s) + s + '</button>').join('') + '</div></div>').join('')
      : vazio('Ninguém da equipe cadastrado.');
    $('av-at-n').textContent = p.atendendo.length;
    $('av-atendendo').innerHTML = p.atendendo.length ? p.atendendo.map(ch => '<div class="it"><div class="l1"><strong>#' + ch.id + ' ' + esc(ch.lead_nome || 'Lead') + '</strong>' +
      AL.nota(ch.nota) + '<span class="dir">aberto há ' + esc(AL.dur(ch.minutos)) + '</span></div><p>com ' + esc(nomeColab(ch.dono)) +
      (ch.interesse_nome ? ' · ' + esc(ch.interesse_nome) : '') + ' · ' + esc(AL.MOTIVO[ch.motivo] || '') + '</p>' + transf(ch.id, ch.dono) +
      '<div class="acao"><button type="button" class="btn sutil peq" data-ficha="' + ch.lead_id + '">' + ic('file') + 'Ver conversa</button></div></div>').join('')
      : vazio('Ninguém em atendimento agora.');
    $('av-fila-n').textContent = p.fila.length;
    $('nav-fila').hidden = !p.fila.length; $('nav-fila').textContent = p.fila.length;
    const ext = extremo();
    $('av-fila').innerHTML = p.fila.length ? p.fila.map(ch => {
      const demais = ch.status === 'alerta' || ch.minutos > ext;
      return '<div class="it' + (demais ? ' ext' : '') + '"><div class="l1"><strong>#' + ch.id + ' ' + esc(ch.lead || 'Lead') + '</strong>' +
        (ch.prioridade === 'quente' ? AL.nota('quente') : '') +
        '<span class="espera' + (demais ? ' demais' : '') + '" style="margin-left:auto">' + ic('clock') + esc(AL.dur(ch.minutos)) + '</span></div>' +
        '<p>' + esc(AL.MOTIVO[ch.motivo] || '') + ' · ' + (ch.ofertado_a ? 'oferecido a ' + esc(nomeColab(ch.ofertado_a)) : 'ninguém aceitou ainda') +
        (demais ? ' · <strong style="color:var(--ruim)">esperando demais</strong>' : '') + '</p>' + transf(ch.id, null) + '</div>';
    }).join('') : vazio('Fila vazia. Ninguém esperando.');
    const atrasados = p.fila.filter(ch => ch.status === 'alerta' || ch.minutos > ext);
    $('av-alerta').innerHTML = atrasados.length ? alerta(atrasados.map(ch => ({nome: ch.lead, minutos: ch.minutos})), false) : '';
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
    const atrasados = h.chamados_abertos_agora.filter(ch => ch.status !== 'atendendo' && (ch.status === 'alerta' || ch.minutos > ext));
    const met = (rot, v) => '<div><dt>' + esc(rot) + '</dt><dd>' + esc(v) + '</dd></div>';
    $('hoje').innerHTML = (atrasados.length ? alerta(atrasados.map(ch => ({nome: ch.lead_nome, minutos: ch.minutos})), true) : '') + regua(a) +
      '<dl class="painel metricas">' + met('Leads novos', h.leads_novos) + met('Chamados abertos', h.chamados_abertos) + met('Assumidos', h.assumidos) +
      met('Vendas', h.vendas) + met('Valor vendido', AL.brl(h.valor_vendido)) + met('Abertos agora', h.abertos_agora) +
      met('Média p/ assumir', AL.dur(h.tempo_medio_assumir_min)) + met('Maior espera', AL.dur(a.maior_min)) + '</dl>' +
      '<h2 class="bloco">Por pessoa</h2><div class="painel tab"><table><thead><tr><th>Colaborador</th><th class="num">Assumidos</th><th class="num">Imediatos</th><th class="num">Médios</th>' +
      '<th class="num">Extremos</th><th class="num">Maior espera</th><th class="num">Vendas</th><th class="num">Valor</th></tr></thead><tbody>' +
      h.por_colaborador.map(p => '<tr><td><strong>' + esc(p.nome) + '</strong></td><td class="num">' + p.assumidos + '</td><td class="num">' + p.assumir.imediatos +
        '</td><td class="num">' + p.assumir.medios + '</td><td class="num">' + (p.assumir.extremos ? '<span class="selo st-perdido">' + p.assumir.extremos + '</span>' : 0) +
        '</td><td class="num">' + esc(AL.dur(p.assumir.maior_min)) + '</td><td class="num">' + p.vendas + '</td><td class="num">' + esc(AL.brl(p.valor)) + '</td></tr>').join('') +
      '</tbody></table></div>' +
      '<h2 class="bloco">Chamados abertos agora</h2><div class="painel tab">' + (h.chamados_abertos_agora.length ?
        '<table><thead><tr><th>#</th><th>Lead</th><th>Nota</th><th>Situação</th><th>Com</th><th class="num">Há</th></tr></thead><tbody>' + h.chamados_abertos_agora.map(ch => {
          const demais = ch.status !== 'atendendo' && (ch.status === 'alerta' || ch.minutos > ext);
          return '<tr class="' + (demais ? 'ext' : '') + '"><td>#' + ch.id + '</td><td><strong>' + esc(ch.lead_nome || 'Lead') + '</strong></td><td>' + AL.nota(ch.nota) +
            '</td><td><span class="selo st-' + esc(ch.status) + '">' + esc(AL.CHAMADO[ch.status] || ch.status) + '</span></td><td>' +
            esc(ch.dono ? nomeColab(ch.dono) : (ch.ofertado_a ? 'oferecido a ' + nomeColab(ch.ofertado_a) : '—')) + '</td><td class="num">' +
            '<span class="espera' + (demais ? ' demais' : '') + '">' + esc(AL.dur(ch.minutos)) + '</span></td></tr>';
        }).join('') + '</tbody></table>' : vazio('Nenhum chamado aberto.')) + '</div>' +
      '<h2 class="bloco">Leads de hoje</h2><div class="painel tab" id="hoje-leads">' + (h.leads_hoje.length ? tabelaLeads(h.leads_hoje) : vazio('Nenhum lead hoje.')) + '</div>';
  }

  function tabelaLeads(ls) {
    return '<table><thead><tr><th>Lead</th><th>Status</th><th>Nota</th><th>Telefone</th><th>Colaborador</th><th>Resultado</th><th>Tempos</th><th><span class="sr">Ação</span></th></tr></thead><tbody>' +
      ls.map(l => '<tr class="clic" data-linha="' + l.id + '"><td><strong>' + esc(l.nome || 'sem nome') + '</strong> <span class="mut peq">#' + l.id + '</span></td><td>' + AL.selo(l.status) +
        (l.retornar_em ? ' <span class="mut peq">' + esc(AL.hora(l.retornar_em)) + '</span>' : '') + '</td><td>' + AL.nota(l.nota) + '</td><td>' + esc(AL.fone(l.telefone)) +
        '</td><td>' + esc(l.colaborador ? nomeColab(l.colaborador) : '—') + '</td><td>' + esc(AL.RESULTADO[l.resultado] || l.resultado || '—') +
        (l.valor ? ' · ' + esc(AL.brl(l.valor)) : '') + '</td><td class="mut peq">' + AL.tempos(l) + '</td><td><button type="button" class="btn peq" data-ficha="' + l.id + '">Ficha</button></td></tr>').join('') +
      '</tbody></table>';
  }

  async function leads() {
    const q = new URLSearchParams();
    ['status', 'colab', 'de', 'ate'].forEach(k => { const v = $('fl-' + k).value; if (v) q.set(k === 'colab' ? 'colaborador' : k, v); });
    const ls = await api('GET', '/api/gestor/leads?' + q);
    $('fl-total').textContent = ls.length + (ls.length === 1 ? ' lead' : ' leads') + ' · filtra ao mudar';
    $('leads').innerHTML = ls.length ? tabelaLeads(ls) : vazio('Nenhum lead neste filtro.');
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
    lerFaq(); faqEd.push({id: novoId(faqEd, 'faq-'), perguntas: perguntas || [], resposta: resposta || ''}); renderFaq();
    const ult = document.querySelector('[data-faq="' + (faqEd.length - 1) + '"]');
    if (ult) { ult.scrollIntoView({behavior: 'smooth', block: 'center'}); ult.querySelector('textarea').focus(); }
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
    const info = cfg.info || {};
    CAMPOS.forEach(k => { $('i-' + k).value = info[k] || ''; });
    $('i-horario-gerado').textContent = 'Vazio = gerado dos horários dos Cadastros.';
    faqEd = JSON.parse(JSON.stringify(cfg.faq || [])); renderFaq();
    const c = cfg.cerebro || {tipo: 'regras'};
    $('b-tipo').value = c.tipo || 'regras'; $('b-modelo').value = c.modelo || ''; $('b-esforco').value = c.esforco || 'low'; $('b-url').value = c.url || '';
    camposCerebro();
    try {
      const s = await AL.api('GET', '/api/saude');
      $('b-saude').textContent = 'Agora no servidor: ' + s.cerebro + (s.cerebro_ok ? ' · ligado' : ' · desligado — ' + (s.cerebro_motivo || '') + ' (respondendo por regras)');
    } catch (e) { $('b-saude').textContent = ''; }
  }
  async function salvarBase() {
    lerFaq();
    const info = {}; CAMPOS.forEach(k => { info[k] = $('i-' + k).value.trim(); });
    const t = $('b-tipo').value, cer = {tipo: t};
    if (t !== 'regras' && $('b-modelo').value.trim()) cer.modelo = $('b-modelo').value.trim();
    if (t === 'anthropic') cer.esforco = $('b-esforco').value;
    if (['ollama', 'openai'].includes(t)) cer.url = $('b-url').value.trim();
    const faq = faqEd.filter(f => f.perguntas.length || f.resposta);
    if (faq.some(f => !f.perguntas.length || !f.resposta)) throw new Error('Cada pergunta do FAQ precisa de ao menos uma forma e de uma resposta.');
    cfg = await api('PUT', '/api/gestor/config', Object.assign({}, cfg, {token_gestor: '***', info, faq, cerebro: cer}));
    aviso('Base de conhecimento salva.'); await base();
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
  async function propostas() {
    const ps = await api('GET', '/api/gestor/propostas');
    const novas = ps.filter(p => p.status === 'nova'), velhas = ps.filter(p => p.status !== 'nova').slice(0, 10);
    const TIPO = {faq: 'FAQ novo', info: 'informação do negócio', correcao: 'correção do FAQ'};
    $('a-propostas').innerHTML = (novas.length ? novas.map(p => '<div class="proposta" data-prop="' + p.id + '"><div class="l1"><h3>#' + p.id + ' · ' +
      esc(TIPO[p.tipo] || p.tipo) + (p.campo ? ' · ' + esc(p.campo) : '') + (p.faq_id ? ' · ' + esc(p.faq_id) : '') + '</h3><span class="selo">' + esc(p.origem === 'cerebro' ? 'pelo cérebro' : 'pelas regras') + '</span></div>' +
      (p.justificativa ? '<p class="mut">' + esc(p.justificativa) + '</p>' : '') + '<div class="grade2">' +
      (p.tipo !== 'info' ? '<label class="campo">Perguntas (uma por linha) <textarea rows="3" data-prop-perg="' + p.id + '">' + esc((p.perguntas || []).join('\n')) + '</textarea></label>' : '') +
      '<label class="campo">Resposta <textarea rows="3" data-prop-resp="' + p.id + '">' + esc(p.resposta) + '</textarea></label></div>' +
      '<div class="acoes"><button type="button" class="btn pri" data-incorporar="' + p.id + '">' + ic('plus') + 'Incorporar à base</button><button type="button" class="btn sutil" data-descartar="' + p.id + '">Descartar</button></div></div>').join('')
      : vazio('Nenhuma proposta nova.')) +
      (velhas.length ? '<p class="vazio peq">Já tratadas: ' + velhas.map(p => '#' + p.id + ' ' + esc(p.status)).join(' · ') + '</p>' : '');
  }

  // ---------- Cadastros (formulário) ----------
  const DIAS = [['seg', 'Segunda'], ['ter', 'Terça'], ['qua', 'Quarta'], ['qui', 'Quinta'], ['sex', 'Sexta'], ['sab', 'Sábado'], ['dom', 'Domingo']];
  const PRAZOS = [['oferta_min', 'Oferta: tempo para aceitar', 2], ['alerta_quente_min', 'Alerta de lead quente', 2], ['alerta_normal_min', 'Alerta de lead normal', 5],
    ['lembrete_min', 'Lembrete de atendimento parado', 30], ['assumir_imediato_min', 'Imediato até', 1], ['assumir_extremo_min', 'Extremo acima de', 10]];
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
        '<input class="pal" data-pr="' + i + '" data-k="palavras" value="' + esc((p.palavras || []).join(', ')) + '" placeholder="mensal, mês, plano" aria-label="Palavras de ' + esc(p.nome) + '">' +
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
    $('c-nome').value = cfg.nome || ''; $('c-url').value = cfg.url_publica || '';
    const ap = cfg.aparencia || {};
    $('c-tema').value = ap.tema || 'claro'; $('c-cor').value = ap.cor_destaque || ''; $('c-nome-exibido').value = ap.nome_exibido || '';
    previaCor();
    eqEd = JSON.parse(JSON.stringify(cfg.equipe || [])); prEd = JSON.parse(JSON.stringify(cfg.produtos || []));
    horEd = JSON.parse(JSON.stringify(cfg.horarios || {}));
    renderEquipe(); renderProdutos(); renderHorarios(); renderPrazos();
    sujo = false; $('c-estado').textContent = 'Nenhuma alteração.';
  }
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
    const novo = Object.assign({}, cfg, {nome: $('c-nome').value.trim(), url_publica: $('c-url').value.trim(), token_gestor: '***',
      equipe, produtos, horarios: horEd, prazos, aparencia});
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
      if (aba === 'base' && trocou) await base();
      if (aba === 'aprendizado' && trocou) await aprendizado();
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
  ['fl-status', 'fl-colab', 'fl-de', 'fl-ate'].forEach(id => $(id).addEventListener('change', () => leads().catch(e => aviso(e.message, true))));
  $('form-filtro').addEventListener('submit', ev => { ev.preventDefault(); leads().catch(e => aviso(e.message, true)); });
  ['a-de', 'a-ate', 'a-colab', 'a-origem'].forEach(id => $(id).addEventListener('change', () => aprendizado().catch(e => aviso(e.message, true))));
  $('form-apr').addEventListener('submit', ev => { ev.preventDefault(); aprendizado().catch(e => aviso(e.message, true)); });

  document.body.addEventListener('click', async ev => {
    const linha = ev.target.closest('tr[data-linha]');
    const b = ev.target.closest('button');
    if (!b && linha) { ev.preventDefault(); if (aba !== 'leads') await mostrar('leads'); ficha(linha.dataset.linha).catch(e => aviso(e.message, true)); return; }
    if (!b) return;
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
      if (b.dataset.faqRm) { lerFaq(); faqEd.splice(+b.dataset.faqRm, 1); renderFaq(); }
      if (b.dataset.virar) {
        const i = aprItens[+b.dataset.virar];
        await mostrar('base'); addFaq(linhas(i.msg_lead), i.enviado); aviso('Revise a pergunta e a resposta e clique em Salvar base de conhecimento.');
      }
      if (b.dataset.incorporar) {
        const id = b.dataset.incorporar, corpo = {resposta: document.querySelector('[data-prop-resp="' + id + '"]').value};
        const pg = document.querySelector('[data-prop-perg="' + id + '"]'); if (pg) corpo.perguntas = linhas(pg.value);
        await api('POST', '/api/gestor/propostas/' + id + '/incorporar', corpo); aviso('Proposta #' + id + ' incorporada à base.'); await propostas();
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
  $('faq-add').addEventListener('click', () => addFaq());
  $('b-tipo').addEventListener('change', camposCerebro);
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
    try { cfg = await api('PUT', '/api/gestor/config', Object.assign({}, cfg, {token_gestor: '***', aprendizado: {periodo: $('a-periodo').value}})); aviso('Período salvo.'); }
    catch (e) { aviso(e.message, true); }
  });
  $('a-gerar').addEventListener('click', async ev => {
    const b = ev.target.closest('button'); b.disabled = true;
    try { const r = await api('POST', '/api/gestor/propostas/gerar', {de: $('a-de').value || undefined, ate: $('a-ate').value || undefined});
      aviso(r.criadas ? r.criadas + ' proposta(s) nova(s).' : 'Nenhuma proposta nova no período.'); await propostas(); }
    catch (e) { aviso(e.message, true); } finally { b.disabled = false; }
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
