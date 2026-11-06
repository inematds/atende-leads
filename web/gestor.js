// Painel do gestor: token na aba (sessionStorage) ou no aparelho (localStorage, se "lembrar").
(function () {
  const $ = id => document.getElementById(id);
  let token = null, cfg = null, aba = 'aovivo', timer = null;
  const api = (m, r, c) => AL.api(m, r, c, {'X-Token': token});
  const aviso = (t, erro) => { $('aviso').textContent = t || ''; $('aviso').className = erro ? 'aviso erro' : 'aviso'; };
  const MOTIVO = {pediu_humano: 'pediu humano', venda: 'chance de venda', precisa: 'precisa de atenção'};
  const brl = v => (v || 0).toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});

  async function aoVivo() {
    const p = await api('GET', '/api/gestor/ao-vivo');
    const opcoes = cfg ? cfg.equipe : [];
    $('av-equipe').innerHTML = p.equipe.map(e => '<div class="cartao"><div class="linha"><h3>' + AL.esc(e.nome) + '</h3>' + AL.tag(e.status) +
      '</div><p class="mut">' + e.minutos + ' min' + (e.proximo ? ' · próxima da vez' : '') + '</p><div class="acoes">' +
      ['livre', 'ocupado', 'fora'].map(s => '<button data-colab="' + AL.esc(e.id) + '" data-st="' + s + '">' + s + '</button>').join('') + '</div></div>').join('');
    const linhaCh = ch => '<tr><td>#' + ch.id + '</td><td>' + AL.esc(ch.lead || ch.lead_nome || '') + '</td><td>' + AL.esc(MOTIVO[ch.motivo] || '') +
      '</td><td>' + AL.tag(ch.prioridade || ch.nota) + ' ' + AL.tag(ch.status) + '</td><td>' + ch.minutos + ' min</td><td>' + AL.esc(ch.ofertado_a || ch.dono || '—') +
      '</td><td><select data-transf="' + ch.id + '"><option value="">transferir…</option>' + opcoes.map(m => '<option value="' + AL.esc(m.id) + '">' + AL.esc(m.nome) + '</option>').join('') + '</select></td></tr>';
    const cab = '<table><tr><th>#</th><th>Lead</th><th>Motivo</th><th>Estado</th><th>Espera</th><th>Com</th><th></th></tr>';
    $('av-fila').innerHTML = p.fila.length ? cab + p.fila.map(linhaCh).join('') + '</table>' : '<p class="mut">Fila vazia.</p>';
    $('av-atendendo').innerHTML = p.atendendo.length ? cab + p.atendendo.map(linhaCh).join('') + '</table>' : '<p class="mut">Ninguém em atendimento.</p>';
  }

  async function hoje() {
    const h = await api('GET', '/api/gestor/hoje');
    const n = (rot, v) => '<div class="cartao"><p class="rotulo">' + AL.esc(rot) + '</p><p class="numero">' + AL.esc(v) + '</p></div>';
    const a = h.assumir;
    $('hoje').innerHTML = '<div class="grade">' + n('Leads novos', h.leads_novos) + n('Chamados abertos', h.chamados_abertos) +
      n('Assumidos', h.assumidos) + n('Vendas', h.vendas) + n('Valor vendido', brl(h.valor_vendido)) +
      n('Abertos agora', h.abertos_agora) + n('Tempo médio p/ assumir', h.tempo_medio_assumir_min + ' min') + '</div>' +
      '<h2>Tempo para assumir</h2><div class="grade" id="hoje-faixas">' + n('⚡ Imediatos (≤ ' + a.imediato_min + ' min)', a.imediatos) +
      n('Médios (até ' + a.extremo_min + ' min)', a.medios) + n('🐢 Extremos (> ' + a.extremo_min + ' min)', a.extremos) +
      n('Maior do dia', a.maior_min + ' min') + '</div>' +
      '<h2>Chamados abertos agora</h2><div class="tabela" id="hoje-abertos">' + (h.chamados_abertos_agora.length ?
        '<table><tr><th>#</th><th>Lead</th><th>Nota</th><th>Status</th><th>Com</th><th>Há</th></tr>' + h.chamados_abertos_agora.map(ch =>
          '<tr><td>#' + ch.id + '</td><td>' + AL.esc(ch.lead_nome || 'lead') + '</td><td>' + AL.tag(ch.nota) + '</td><td>' + AL.tag(ch.status) +
          '</td><td>' + AL.esc(ch.dono || (ch.ofertado_a ? '→ ' + ch.ofertado_a : '—')) + '</td><td>' + AL.esc(AL.dur(ch.minutos)) + '</td></tr>').join('') + '</table>'
        : '<p class="mut">Nenhum chamado aberto.</p>') + '</div>' +
      '<h2>Leads de hoje</h2><div class="tabela" id="hoje-leads">' + (h.leads_hoje.length ? tabelaLeads(h.leads_hoje) : '<p class="mut">Nenhum lead hoje.</p>') + '</div>' +
      '<h2>Por colaborador</h2><div class="tabela"><table>' +
      '<tr><th>Colaborador</th><th>Assumidos</th><th>Imediatos</th><th>Médios</th><th>Extremos</th><th>Maior</th><th>Vendas</th><th>Valor</th></tr>' +
      h.por_colaborador.map(p => '<tr><td>' + AL.esc(p.nome) + '</td><td>' + p.assumidos + '</td><td>' + p.assumir.imediatos + '</td><td>' + p.assumir.medios +
        '</td><td>' + p.assumir.extremos + '</td><td>' + p.assumir.maior_min + ' min</td><td>' + p.vendas + '</td><td>' + brl(p.valor) + '</td></tr>').join('') +
      '</table></div>';
  }

  function tabelaLeads(ls) {
    return '<table><tr><th>#</th><th>Status</th><th>Nome</th><th>Telefone</th><th>Nota</th><th>Colaborador</th><th>Resultado</th><th>Tempos</th><th></th></tr>' +
      ls.map(l => '<tr><td>' + l.id + '</td><td>' + AL.selo(l.status) + (l.retornar_em ? '<br><small class="mut">📅 ' + AL.esc(AL.hora(l.retornar_em)) + '</small>' : '') +
        '</td><td>' + (l.nota === 'quente' ? '🔥 ' : '') + AL.esc(l.nome || '') + '</td><td>' + AL.esc(AL.fone(l.telefone)) +
        '</td><td>' + AL.tag(l.nota) + '</td><td>' + AL.esc(l.colaborador || '') + '</td><td>' + AL.esc(l.resultado || '') +
        '</td><td><small class="mut">' + AL.tempos(l) + '</small></td><td><button data-ficha="' + l.id + '">Ficha</button></td></tr>').join('') + '</table>';
  }

  async function leads() {
    const q = new URLSearchParams();
    if ($('fl-status').value) q.set('status', $('fl-status').value);
    if ($('fl-colab').value) q.set('colaborador', $('fl-colab').value);
    if ($('fl-de').value) q.set('de', $('fl-de').value);
    if ($('fl-ate').value) q.set('ate', $('fl-ate').value);
    const ls = await api('GET', '/api/gestor/leads?' + q);
    $('leads').innerHTML = ls.length ? tabelaLeads(ls) : '<p class="mut">Nenhum lead.</p>';
  }

  async function ficha(id) {
    const f = await api('GET', '/api/gestor/leads/' + id);
    $('ficha').hidden = false;
    $('ficha').innerHTML = '<div class="linha"><h2 style="margin:0">' + AL.esc(f.lead.nome || 'Lead') + ' · ' + AL.esc(AL.fone(f.lead.telefone)) + '</h2></div>' +
      '<p class="mut">' + AL.selo(f.lead.status) + ' · nota ' + AL.esc(f.lead.nota) + '</p><p class="mut">' + AL.tempos(f.lead) + '</p><h3>Chamados</h3>' +
      f.chamados.map(ch => '<p>#' + ch.id + ' ' + AL.esc(MOTIVO[ch.motivo]) + ' · ' + AL.esc(ch.status) + (ch.resultado ? ' · ' + AL.esc(ch.resultado) : '') +
        (ch.dono ? ' · ' + AL.esc(ch.dono) : '') + (ch.status === 'fechado' ? ' <button data-reabrir="' + ch.id + '">Reabrir</button>' : '') + '</p>').join('') +
      '<h3>Mensagens</h3><div class="chat-log" style="max-height:320px">' + f.mensagens.map(m => '<div class="bolha ' + (m.de === 'lead' ? '' : 'humano') +
        '"><small>' + AL.esc(m.de) + ' · ' + AL.esc(AL.hora(m.em)) + '</small>' + AL.esc(m.texto) + '</div>').join('') + '</div>';
    $('ficha').scrollIntoView({behavior: 'smooth'});
  }

  async function cadastros() {
    cfg = await api('GET', '/api/gestor/config');
    $('c-nome').value = cfg.nome || ''; $('c-url').value = cfg.url_publica || '';
    for (const k of ['equipe', 'produtos', 'faq', 'horarios', 'prazos', 'cerebro']) $('c-' + k).value = JSON.stringify(cfg[k], null, 2);
    $('c-imediato').value = (cfg.prazos || {}).assumir_imediato_min || 1;
    $('c-extremo').value = (cfg.prazos || {}).assumir_extremo_min || 10;
  }

  async function mostrar(nova) {
    aba = nova || aba;
    document.querySelectorAll('.aba').forEach(b => b.classList.toggle('ativa', b.dataset.aba === aba));
    document.querySelectorAll('[data-painel]').forEach(s => { s.hidden = s.dataset.painel !== aba; });
    try {
      if (aba === 'aovivo') await aoVivo();
      if (aba === 'hoje') await hoje();
      if (aba === 'leads') await leads();
      if (aba === 'cadastros' && nova) await cadastros();
    } catch (e) { aviso(e.message, true); }
  }

  const CHAVE = 'al_token_gestor';
  async function entrar(valor, lembrar) {
    token = valor;
    try {
      cfg = await api('GET', '/api/gestor/config');
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      $('fl-colab').innerHTML = '<option value="">todos</option>' + cfg.equipe.map(m => '<option value="' + AL.esc(m.id) + '">' + AL.esc(m.nome) + '</option>').join('');
      $('login').hidden = true; $('painel').hidden = false; $('sair').hidden = false;
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
  $('sair').addEventListener('click', () => {
    localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE); location.reload();
  });
  { const salvo = sessionStorage.getItem(CHAVE) || localStorage.getItem(CHAVE);
    if (salvo) entrar(salvo, !!localStorage.getItem(CHAVE)); }
  document.querySelectorAll('.aba').forEach(b => b.addEventListener('click', () => mostrar(b.dataset.aba)));
  $('form-filtro').addEventListener('submit', ev => { ev.preventDefault(); leads().catch(e => aviso(e.message, true)); });
  document.body.addEventListener('click', async ev => {
    const b = ev.target.closest('button'); if (!b) return;
    try {
      if (b.dataset.st) { await api('POST', '/api/gestor/equipe/' + encodeURIComponent(b.dataset.colab) + '/status', {status: b.dataset.st}); await aoVivo(); }
      if (b.dataset.ficha) { if (aba !== 'leads') await mostrar('leads'); await ficha(b.dataset.ficha); }
      if (b.dataset.reabrir) { await api('POST', '/api/gestor/chamados/' + b.dataset.reabrir + '/reabrir', {}); aviso('Chamado reaberto.'); }
    } catch (e) { aviso(e.message, true); }
  });
  document.body.addEventListener('change', async ev => {
    const s = ev.target.closest('select[data-transf]'); if (!s || !s.value) return;
    try { await api('POST', '/api/gestor/chamados/' + s.dataset.transf + '/transferir', {colaborador: s.value}); aviso('Transferido.'); await aoVivo(); }
    catch (e) { aviso(e.message, true); }
  });
  $('salvar').addEventListener('click', async () => {
    try {
      const novo = Object.assign({}, cfg, {nome: $('c-nome').value, url_publica: $('c-url').value, token_gestor: '***'});
      for (const k of ['equipe', 'produtos', 'faq', 'horarios', 'prazos', 'cerebro']) novo[k] = JSON.parse($('c-' + k).value);
      // os campos numéricos das faixas valem sobre o JSON (o servidor valida: inteiros ≥ 1, imediato < extremo)
      const num = v => (/^\d+$/.test(v.trim()) ? parseInt(v, 10) : v);
      novo.prazos = Object.assign({}, novo.prazos, {assumir_imediato_min: num($('c-imediato').value), assumir_extremo_min: num($('c-extremo').value)});
      cfg = await api('PUT', '/api/gestor/config', novo);
      aviso('Cadastros salvos.'); await cadastros();
    } catch (e) { aviso(e instanceof SyntaxError ? 'JSON inválido: ' + e.message : e.message, true); }
  });
  $('exportar').addEventListener('click', async () => {
    try {
      const r = await fetch('/api/gestor/exportar.csv', {headers: {'X-Token': token}});
      if (!r.ok) throw new Error('Erro ' + r.status);
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement('a'); a.href = url; a.download = 'leads.csv'; a.click(); URL.revokeObjectURL(url);
    } catch (e) { aviso(e.message, true); }
  });
})();
