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
    for (const k of ['equipe', 'produtos', 'horarios', 'prazos']) $('c-' + k).value = JSON.stringify(cfg[k], null, 2);
    $('c-imediato').value = (cfg.prazos || {}).assumir_imediato_min || 1;
    $('c-extremo').value = (cfg.prazos || {}).assumir_extremo_min || 10;
  }

  // ---------- Base de conhecimento ----------
  const CAMPOS = ['horario_atendimento', 'endereco', 'pagamento', 'entrega', 'garantia', 'site', 'observacoes'];
  let faqEd = [];
  const linhas = t => String(t || '').split('\n').map(x => x.trim()).filter(Boolean);

  function renderFaq() {
    $('faq-lista').innerHTML = faqEd.length ? faqEd.map((f, i) => '<div class="cartao faq-item" data-faq="' + i + '">' +
      '<div class="linha"><h3 style="margin:0">' + AL.esc(f.id || 'nova') + '</h3><button type="button" class="perigo" data-faq-rm="' + i + '">Remover</button></div>' +
      '<label>Formas da pergunta (uma por linha) <textarea class="texto" data-faq-perg="' + i + '" rows="3">' + AL.esc((f.perguntas || []).join('\n')) + '</textarea></label>' +
      '<label>Resposta <textarea class="texto" data-faq-resp="' + i + '" rows="3">' + AL.esc(f.resposta || '') + '</textarea></label></div>').join('')
      : '<p class="mut">Nenhuma pergunta ainda.</p>';
  }
  function lerFaq() {
    document.querySelectorAll('[data-faq-perg]').forEach(t => { faqEd[+t.dataset.faqPerg].perguntas = linhas(t.value); });
    document.querySelectorAll('[data-faq-resp]').forEach(t => { faqEd[+t.dataset.faqResp].resposta = t.value.trim(); });
  }
  function novoId() {
    let n = faqEd.length + 1, id;
    do { id = 'faq-' + n++; } while (faqEd.some(f => f.id === id));
    return id;
  }
  function addFaq(perguntas, resposta) {
    lerFaq(); faqEd.push({id: novoId(), perguntas: perguntas || [], resposta: resposta || ''}); renderFaq();
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
    const k = r.contadores, n = (rot, v) => '<div class="cartao"><p class="rotulo">' + AL.esc(rot) + '</p><p class="numero">' + AL.esc(v) + '</p></div>';
    $('a-contadores').innerHTML = n('Respostas registradas', k.total) + n('✅ Sugestão usada sem editar', k.pct_ok + '%') +
      n('✏️ Sugestão editada', k.pct_editadas + '%') + n('🙈 Sugestão ignorada', k.pct_ignoradas + '%') + n('Livres (sem sugestão)', k.livre - k.ignoradas);
    $('a-itens').innerHTML = aprItens.length ? '<table><tr><th>Quando</th><th>Cliente disse</th><th>Sugestão da IA</th><th>Vendedor mandou</th><th>Origem</th><th>Similar.</th><th></th></tr>' +
      aprItens.map((i, ix) => '<tr><td><small>' + AL.esc(AL.hora(i.em)) + '<br>' + AL.esc(i.colaborador_nome || i.colaborador || '') + '</small></td><td>' + AL.esc(i.msg_lead) +
        '</td><td>' + (i.sugestao ? AL.esc(i.sugestao) : '<span class="mut">—</span>') + '</td><td>' + AL.esc(i.enviado) + '</td><td>' + AL.tag(ORIGEM[i.origem] || i.origem) +
        '</td><td>' + (i.distancia == null ? '—' : Math.round(i.distancia * 100) + '%') + '</td><td><button data-virar="' + ix + '">Virar FAQ</button></td></tr>').join('') + '</table>'
      : '<p class="mut">Nenhum registro no filtro.</p>';
    await propostas();
  }
  async function propostas() {
    const ps = await api('GET', '/api/gestor/propostas');
    const novas = ps.filter(p => p.status === 'nova'), velhas = ps.filter(p => p.status !== 'nova').slice(0, 10);
    const TIPO = {faq: 'FAQ novo', info: 'informação do negócio', correcao: 'correção do FAQ'};
    $('a-propostas').innerHTML = (novas.length ? novas.map(p => '<div class="cartao" data-prop="' + p.id + '"><div class="linha"><h3 style="margin:0">#' + p.id + ' · ' +
      AL.esc(TIPO[p.tipo] || p.tipo) + (p.campo ? ' · ' + AL.esc(p.campo) : '') + (p.faq_id ? ' · ' + AL.esc(p.faq_id) : '') + '</h3>' + AL.tag(p.origem) + '</div>' +
      (p.justificativa ? '<p class="mut">' + AL.esc(p.justificativa) + '</p>' : '') +
      (p.tipo !== 'info' ? '<label>Perguntas (uma por linha) <textarea class="texto" rows="3" data-prop-perg="' + p.id + '">' + AL.esc((p.perguntas || []).join('\n')) + '</textarea></label>' : '') +
      '<label>Resposta <textarea class="texto" rows="3" data-prop-resp="' + p.id + '">' + AL.esc(p.resposta) + '</textarea></label>' +
      '<div class="acoes"><button class="primario" data-incorporar="' + p.id + '">Incorporar à base</button><button class="secundario" data-descartar="' + p.id + '">Descartar</button></div></div>').join('')
      : '<p class="mut">Nenhuma proposta nova.</p>') +
      (velhas.length ? '<p class="mut">Já tratadas: ' + velhas.map(p => '#' + p.id + ' ' + AL.esc(p.status)).join(' · ') + '</p>' : '');
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
      if (aba === 'base' && nova) await base();
      if (aba === 'aprendizado' && nova) await aprendizado();
    } catch (e) { aviso(e.message, true); }
  }

  const CHAVE = 'al_token_gestor';
  async function entrar(valor, lembrar) {
    token = valor;
    try {
      cfg = await api('GET', '/api/gestor/config');
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      $('fl-colab').innerHTML = $('a-colab').innerHTML = '<option value="">todos</option>' + cfg.equipe.map(m => '<option value="' + AL.esc(m.id) + '">' + AL.esc(m.nome) + '</option>').join('');
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
      for (const k of ['equipe', 'produtos', 'horarios', 'prazos']) novo[k] = JSON.parse($('c-' + k).value);
      // os campos numéricos das faixas valem sobre o JSON (o servidor valida: inteiros ≥ 1, imediato < extremo)
      const num = v => (/^\d+$/.test(v.trim()) ? parseInt(v, 10) : v);
      novo.prazos = Object.assign({}, novo.prazos, {assumir_imediato_min: num($('c-imediato').value), assumir_extremo_min: num($('c-extremo').value)});
      cfg = await api('PUT', '/api/gestor/config', novo);
      aviso('Cadastros salvos.'); await cadastros();
    } catch (e) { aviso(e instanceof SyntaxError ? 'JSON inválido: ' + e.message : e.message, true); }
  });
  $('faq-add').addEventListener('click', () => addFaq());
  $('b-tipo').addEventListener('change', camposCerebro);
  $('salvar-base').addEventListener('click', () => salvarBase().catch(e => aviso(e.message, true)));
  $('form-testar').addEventListener('submit', async ev => {
    ev.preventDefault();
    $('t-resultado').innerHTML = '<p class="mut">Testando…</p>';
    try {
      const r = await api('POST', '/api/gestor/testar', {texto: $('t-texto').value});
      $('t-resultado').innerHTML = (r.respostas.length ? r.respostas.map(t => '<div class="bolha">' + AL.esc(t) + '</div>').join('') : '<p class="mut">(o agente não responderia nada)</p>') +
        (r.chamado ? '<p class="aviso">Abriria um chamado: ' + AL.esc(MOTIVO[r.chamado] || r.chamado) + '.</p>' : '');
    } catch (e) { $('t-resultado').innerHTML = '<p class="erro">' + AL.esc(e.message) + '</p>'; }
  });
  $('form-apr').addEventListener('submit', ev => { ev.preventDefault(); aprendizado().catch(e => aviso(e.message, true)); });
  $('a-periodo-salvar').addEventListener('click', async () => {
    try { cfg = await api('PUT', '/api/gestor/config', Object.assign({}, cfg, {token_gestor: '***', aprendizado: {periodo: $('a-periodo').value}})); aviso('Período salvo.'); }
    catch (e) { aviso(e.message, true); }
  });
  $('a-gerar').addEventListener('click', async ev => {
    ev.target.disabled = true;
    try { const r = await api('POST', '/api/gestor/propostas/gerar', {de: $('a-de').value || undefined, ate: $('a-ate').value || undefined});
      aviso(r.criadas ? r.criadas + ' proposta(s) nova(s).' : 'Nenhuma proposta nova no período.'); await propostas(); }
    catch (e) { aviso(e.message, true); } finally { ev.target.disabled = false; }
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
