// Painel da equipe: código só na memória da aba (variável), nada em storage.
(function () {
  const $ = id => document.getElementById(id);
  let codigo = null, eu = null, fichaChamado = null, produtos = [];
  const MOTIVOS = {sem_interesse: [['preco', 'Preço'], ['ja_comprou', 'Já comprou'], ['curioso', 'Curioso'], ['outro', 'Outro']],
    invalido: [['numero_errado', 'Número errado'], ['spam', 'Spam'], ['nao_e_lead', 'Não é lead']]};
  const api = (m, r, c) => AL.api(m, r, c, {'X-Codigo': codigo});
  const aviso = (t, erro) => { $('aviso').textContent = t || ''; $('aviso').className = erro ? 'aviso erro' : 'aviso'; };

  function cartao(ch, botoes) {
    return '<div class="cartao"><div class="linha"><h3>#' + ch.id + ' ' + AL.esc(ch.lead_nome || 'lead') + '</h3>' +
      AL.tag(ch.status) + '</div><p class="mut">' + AL.esc({pediu_humano: 'pediu humano', venda: 'chance de venda', precisa: 'precisa de atenção'}[ch.motivo]) +
      ' · nota ' + AL.esc(ch.nota) + (ch.interesse_nome ? ' · ' + AL.esc(ch.interesse_nome) : '') + ' · ' + ch.minutos + ' min</p>' +
      '<p>' + AL.esc(AL.fone(ch.telefone)) + '</p>' + (ch.resumo ? '<pre class="mut">' + AL.esc(ch.resumo) + '</pre>' : '') +
      '<div class="acoes">' + botoes + '<a class="botao" href="' + AL.esc(ch.link_ligar) + '" title="Ligação comum pelo telefone">📞 Ligar (telefone)</a>' +
      '<a class="botao" target="_blank" rel="noopener" href="https://wa.me/' + AL.esc(ch.telefone) + '" title="Abre a conversa; para ligar, toque no ícone de chamada dentro do WhatsApp">💬 WhatsApp (conversa ou chamada)</a></div>' +
      '<p class="mut">📞 Ligar = ligação comum pelo telefone · 💬 WhatsApp = abre a conversa; para ligar, toque no ícone de chamada dentro do WhatsApp.</p></div>';
  }

  async function carregar() {
    try { eu = await api('GET', '/api/equipe/eu'); } catch (e) { if (e.status === 401) sair(); return; }
    $('quem').textContent = eu.nome;
    $('meu-status').textContent = {livre: '🟢 Livre', ocupado: '🔴 Ocupado', fora: '⚫ Fora', atendendo: '🟡 Atendendo'}[eu.status] || eu.status;
    $('ofertas').innerHTML = eu.ofertas.length ? eu.ofertas.map(ch => cartao(ch,
      '<button class="primario" data-assumir="' + ch.id + '">✅ Assumir</button>' +
      (ch.ofertado_a === eu.id ? '<button data-passar="' + ch.id + '">↪️ Passar</button>' : '') +
      '<button data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '">Ficha</button>')).join('') : '<p class="mut">Nada esperando por você.</p>';
    $('chamados').innerHTML = eu.chamados.length ? eu.chamados.map(ch => cartao(ch,
      '<button class="primario" data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '">Abrir</button>')).join('') : '<p class="mut">Nenhum atendimento aberto.</p>';
    $('retornos').innerHTML = eu.retornos_hoje.length ? '<div class="tabela"><table><tr><th>Hora</th><th>Lead</th><th>Telefone</th></tr>' +
      eu.retornos_hoje.map(r => '<tr><td>' + AL.esc(r.em.slice(11, 16)) + '</td><td>' + AL.esc(r.nome || 'lead') + '</td><td>' +
        AL.esc(AL.fone(r.telefone)) + '</td></tr>').join('') + '</table></div>' : '<p class="mut">Nenhum retorno hoje.</p>';
    await contatos();
  }

  async function contatos() {
    const st = $('ct-status').value;
    let ls;
    try { ls = await api('GET', '/api/equipe/contatos' + (st ? '?status=' + encodeURIComponent(st) : '')); } catch (e) { return; }
    $('contatos').innerHTML = ls.length ? ls.map(l => '<button type="button" class="cartao contato" data-ficha="' + l.id + '"' +
      (l.chamado_aberto ? ' data-ch="' + l.chamado_aberto + '"' : '') + '><span class="linha">' + AL.selo(l.status) +
      (l.nota === 'quente' ? '<span title="lead quente">🔥</span>' : '') + '<strong>' + AL.esc(l.nome || 'lead') + '</strong>' +
      '<span class="mut">' + AL.esc(AL.fone(l.telefone)) + '</span>' +
      (l.novas > 0 ? '<span class="selo nova">' + l.novas + (l.novas === 1 ? ' nova' : ' novas') + '</span>' : '') +
      (l.retornar_em ? '<span class="mut">📅 retorno ' + AL.esc(AL.hora(l.retornar_em)) + '</span>' : '') + '</span>' +
      (l.ultima_mensagem ? '<span class="ult">“' + AL.esc(l.ultima_mensagem) + '”</span>' : '') +
      '<small class="mut">' + AL.tempos(l) + '</small></button>').join('') : '<p class="mut">Nenhum contato' + (st ? ' com este status' : '') + '.</p>';
  }

  async function abrirFicha(leadId, chId) {
    try {
      const f = await api('GET', '/api/equipe/leads/' + leadId);
      fichaChamado = f.chamados.find(c => String(c.id) === String(chId)) || f.chamados[f.chamados.length - 1];
      $('ficha').hidden = false;
      $('ficha-titulo').textContent = (f.lead.nome || 'Lead') + ' · #' + fichaChamado.id;
      $('ficha-dados').innerHTML = '<p>' + AL.esc(AL.fone(f.lead.telefone)) + ' · nota ' + AL.esc(f.lead.nota) + ' · ' + AL.selo(f.lead.status) + '</p>' +
        '<p class="mut">' + AL.tempos(f.lead) + '</p>' +
        (f.historico.length ? '<p class="mut">Histórico: ' + f.historico.map(h => AL.esc(h.resultado) + ' (' + AL.esc(h.em) + ')').join(', ') + '</p>' : '');
      $('ficha-msgs').innerHTML = f.mensagens.map(m => '<div class="bolha ' + (m.de === 'lead' ? '' : (m.de === 'humano' ? 'minha' : 'humano')) +
        '"><small>' + AL.esc(m.de) + ' · ' + AL.esc(AL.hora(m.em)) + '</small>' + AL.esc(m.texto) + '</div>').join('');
      $('ficha-msgs').scrollTop = 1e9;
      $('ficha-acoes').hidden = !(fichaChamado.status === 'atendendo' && fichaChamado.dono === eu.id);
      $('ficha').scrollIntoView({behavior: 'smooth'});
      contatos();  // abrir a ficha zera as "novas" deste lead
    } catch (e) { aviso(e.message, true); }
  }

  function camposFechar() {
    const r = $('f-resultado').value;
    document.querySelector('[data-campo=valor]').hidden = r !== 'vendeu';
    document.querySelector('[data-campo=produto]').hidden = r !== 'vendeu';
    document.querySelector('[data-campo=retornar_em]').hidden = r !== 'retornar';
    document.querySelector('[data-campo=motivo]').hidden = !MOTIVOS[r];
    $('f-motivo').innerHTML = (MOTIVOS[r] || []).map(m => '<option value="' + m[0] + '">' + m[1] + '</option>').join('');
  }

  const CHAVE = 'al_codigo_equipe';
  function sair() { codigo = null; localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE); $('painel').hidden = true; $('login').hidden = false; $('sair').hidden = true; }

  async function entrar(valor, lembrar) {
    codigo = valor;
    try {
      const e0 = await api('GET', '/api/equipe/eu'); produtos = e0.produtos || [];
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      $('login').hidden = true; $('painel').hidden = false; $('sair').hidden = false;
      $('f-produto').innerHTML = '<option value="">—</option>' + produtos.map(p => '<option value="' + AL.esc(p.id) + '">' + AL.esc(p.nome) + '</option>').join('');
      camposFechar(); carregar(); setInterval(carregar, 10000);
    } catch (e) {
      codigo = null; localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE);
      $('erro-login').textContent = e.status === 401 ? 'Código inválido.' : e.message;
    }
  }
  $('form-login').addEventListener('submit', ev => {
    ev.preventDefault();
    const v = $('codigo').value.trim(); $('codigo').value = '';
    entrar(v, $('lembrar').checked);
  });
  $('sair').addEventListener('click', () => { sair(); location.reload(); });
  { const salvo = sessionStorage.getItem(CHAVE) || localStorage.getItem(CHAVE);
    if (salvo) entrar(salvo, !!localStorage.getItem(CHAVE)); }
  document.querySelectorAll('[data-status]').forEach(b => b.addEventListener('click', async () => {
    try { await api('POST', '/api/equipe/status', {status: b.dataset.status}); aviso(''); carregar(); } catch (e) { aviso(e.message, true); }
  }));
  document.body.addEventListener('click', async ev => {
    const t = ev.target.closest('button'); if (!t) return;
    try {
      if (t.dataset.assumir) { await api('POST', '/api/equipe/chamados/' + t.dataset.assumir + '/assumir', {}); aviso('Você assumiu #' + t.dataset.assumir); await carregar(); }
      else if (t.dataset.passar) { await api('POST', '/api/equipe/chamados/' + t.dataset.passar + '/passar', {}); await carregar(); }
      else if (t.dataset.ficha) { await abrirFicha(t.dataset.ficha, t.dataset.ch); }
    } catch (e) { aviso(e.message, true); carregar(); }
  });
  $('ct-status').addEventListener('change', contatos);
  $('fechar-ficha').addEventListener('click', () => { $('ficha').hidden = true; });
  $('f-resultado').addEventListener('change', camposFechar);
  $('form-responder').addEventListener('submit', async ev => {
    ev.preventDefault();
    try { await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/responder', {texto: $('resposta').value}); $('resposta').value = '';
      abrirFicha(fichaChamado.lead_id, fichaChamado.id); } catch (e) { aviso(e.message, true); }
  });
  $('form-fechar').addEventListener('submit', async ev => {
    ev.preventDefault();
    const r = $('f-resultado').value, corpo = {resultado: r};
    if (r === 'vendeu') { corpo.valor = parseFloat($('f-valor').value); if ($('f-produto').value) corpo.produto = $('f-produto').value; }
    if (r === 'retornar') corpo.retornar_em = $('f-retornar').value.slice(0, 16);
    if (MOTIVOS[r]) corpo.motivo = $('f-motivo').value;
    if ($('f-nota').value.trim()) corpo.nota = $('f-nota').value.trim();
    try { await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/fechar', corpo); aviso('Atendimento #' + fichaChamado.id + ' fechado.');
      $('ficha').hidden = true; carregar(); } catch (e) { aviso(e.message, true); }
  });
  $('devolver').addEventListener('click', async () => {
    try { await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/devolver', {}); $('ficha').hidden = true; carregar(); } catch (e) { aviso(e.message, true); }
  });
})();
