// Painel da equipe: código na aba (sessionStorage) ou no aparelho (localStorage, se "lembrar").
(function () {
  const $ = id => document.getElementById(id);
  const ic = AL.ic, esc = AL.esc;
  let codigo = null, eu = null, ficha = null, fichaChamado = null, produtos = [], sugestaoId = null, descartada = null;
  let filtro = '', contatosCache = [], relogio = null, fichaLeadId = null, fichaChId = null;
  const MOTIVOS = {sem_interesse: [['preco', 'Preço'], ['ja_comprou', 'Já comprou'], ['curioso', 'Curioso'], ['outro', 'Outro']],
    invalido: [['numero_errado', 'Número errado'], ['spam', 'Spam'], ['nao_e_lead', 'Não é lead']]};
  const api = (m, r, c) => AL.api(m, r, c, {'X-Codigo': codigo});
  let tAviso = null;
  const aviso = (t, erro) => {
    const el = $('aviso'); el.textContent = t || ''; el.className = 'toast' + (erro ? ' erro' : '');
    clearTimeout(tAviso); if (t) tAviso = setTimeout(() => { el.textContent = ''; }, erro ? 7000 : 3500);
  };
  const celular = () => window.matchMedia('(max-width: 1023px)').matches;

  AL.seletorTema('tema');
  AL.api('GET', '/api/aparencia').then(a => { $('negocio').textContent = a.nome_exibido; $('logo').textContent = AL.iniciais(a.nome_exibido); }).catch(() => {});

  function botoesContato(ch, compacto) {
    const tel = '<a class="btn' + (compacto ? ' ic' : '') + '" href="' + esc(ch.link_ligar) + '" aria-label="Ligar (telefone)" title="Ligação comum pelo telefone">' +
      ic('phone') + (compacto ? '' : '<span>Ligar<small>telefone</small></span>') + '</a>';
    const wa = '<a class="btn' + (compacto ? ' ic' : '') + '" target="_blank" rel="noopener" href="https://wa.me/' + esc(ch.telefone) +
      '" aria-label="WhatsApp (conversa ou chamada)" title="Abre a conversa; para ligar, toque no ícone de chamada dentro do WhatsApp">' +
      ic('msg') + (compacto ? '' : '<span>WhatsApp<small>conversa ou chamada</small></span>') + '</a>';
    return tel + wa;
  }

  // ---------- faixa "Esperando por você" ----------
  function oferta(ch) {
    const demais = ch.status === 'alerta';
    return '<article class="of" data-of="' + ch.id + '"><div class="txt"><div class="l1"><strong>' + esc(ch.lead_nome || AL.fone(ch.telefone) || 'Lead') + '</strong>' +
      AL.nota(ch.nota) + '<span class="motivo">' + esc(AL.MOTIVO[ch.motivo] || '') + (ch.interesse_nome ? ' · ' + esc(ch.interesse_nome) : '') + '</span>' +
      '<span class="espera' + (demais ? ' demais' : '') + '">' + ic('clock') + esc(AL.dur(ch.minutos)) + (demais ? ' · esperando demais' : '') + '</span></div>' +
      (ch.resumo ? '<q>' + esc(ch.resumo.split('\n').pop().replace(/^Disse:\s*/, '').replace(/^"|"$/g, '')) + '</q>' : '') + '</div>' +
      '<div class="acoes"><button type="button" class="btn pri" data-assumir="' + ch.id + '">' + ic('check') + 'Assumir</button>' +
      (ch.ofertado_a === eu.id ? '<button type="button" class="btn ic" data-passar="' + ch.id + '" aria-label="Passar para o próximo" title="Passar para o próximo">' + ic('pass') + '</button>' : '') +
      '<button type="button" class="btn ic" data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '" aria-label="Ver conversa" title="Ver conversa">' + ic('file') + '</button>' +
      botoesContato(ch, true) + '</div></article>';
  }

  async function carregar() {
    try { eu = await api('GET', '/api/equipe/eu'); } catch (e) { if (e.status === 401) sair(); return; }
    $('quem-nome').textContent = eu.nome; $('quem-av').textContent = AL.iniciais(eu.nome);
    document.querySelectorAll('[data-status]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.status === eu.status)));
    $('status-seg').setAttribute('aria-label', 'Meu status: ' + (AL.COLAB[eu.status] || eu.status));
    $('espera').hidden = !eu.ofertas.length;
    $('espera-n').textContent = eu.ofertas.length;
    $('ofertas').innerHTML = eu.ofertas.map(oferta).join('');
    $('ch-n').textContent = eu.chamados.length;
    $('chamados').innerHTML = eu.chamados.length ? eu.chamados.map(ch => '<div class="cartao-ch"><div class="txt"><strong>' +
      esc(ch.lead_nome || 'Lead') + '</strong> <span class="mut peq">#' + ch.id + '</span><p>' + esc(AL.MOTIVO[ch.motivo] || '') +
      (ch.interesse_nome ? ' · ' + esc(ch.interesse_nome) : '') + ' · aberto há ' + esc(AL.dur(ch.minutos)) + '</p></div>' +
      '<button type="button" class="btn pri" data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '">Abrir</button></div>').join('')
      : '<p class="vazio">Nenhum atendimento aberto. Quando você assumir um lead, ele aparece aqui.</p>';
    $('retornos').innerHTML = eu.retornos_hoje.length ? '<table><thead><tr><th>Hora</th><th>Lead</th><th>Telefone</th></tr></thead><tbody>' +
      eu.retornos_hoje.map(r => '<tr><td>' + esc(r.em.slice(11, 16)) + '</td><td>' + esc(r.nome || 'Lead') + '</td><td>' +
        esc(AL.fone(r.telefone)) + '</td></tr>').join('') + '</tbody></table>' : '<p class="vazio">Nenhum retorno marcado para hoje.</p>';
    await contatos();
    if (fichaLeadId && !digitando()) abrirFicha(fichaLeadId, fichaChId, true);
  }

  // ---------- meus contatos ----------
  async function contatos() {
    try { contatosCache = await api('GET', '/api/equipe/contatos' + (filtro ? '?status=' + encodeURIComponent(filtro) : '')); } catch (e) { return; }
    desenharContatos();
  }
  function desenharContatos() {
    const q = $('busca').value.trim().toLowerCase(), qd = q.replace(/\D/g, '');
    const ls = contatosCache.filter(l => !q || String(l.nome || '').toLowerCase().includes(q) || (qd && String(l.telefone).includes(qd)));
    $('ct-n').textContent = filtro ? '' : contatosCache.length;
    $('contatos').innerHTML = ls.length ? ls.map(l => '<button type="button" class="ct" data-ficha="' + l.id + '"' +
      (l.chamado_aberto ? ' data-ch="' + l.chamado_aberto + '"' : '') + (String(l.id) === String(fichaLeadId) ? ' aria-current="true"' : '') + '>' +
      '<span class="l1"><strong>' + esc(l.nome || AL.fone(l.telefone) || 'Lead') + '</strong><span class="ha">' + esc(AL.ha(l.minutos_desde_contato)) + '</span></span>' +
      (l.ultima_mensagem ? '<span class="msg" style="display:block">“' + esc(l.ultima_mensagem) + '”</span>' : '') +
      '<span class="l3">' + AL.selo(l.status) + AL.nota(l.nota === 'frio' ? '' : l.nota) +
      (l.novas > 0 ? '<span class="selo novas">' + l.novas + (l.novas === 1 ? ' nova' : ' novas') + '</span>' : '') +
      (l.retornar_em ? '<span class="selo st-retornar">' + ic('cal') + 'retorno ' + esc(AL.hora(l.retornar_em)) + '</span>' : '') + '</span>' +
      '<span class="l3" style="margin-top:4px">' + AL.tempos(l) + '</span></button>').join('')
      : '<p class="vazio">Nenhum contato' + (filtro ? ' com este status' : '') + (q ? ' para essa busca' : '') + '.</p>';
  }

  // ---------- ficha / atendimento ----------
  const digitando = () => document.activeElement === $('resposta') || !!$('resposta').value.trim();

  async function abrirFicha(leadId, chId, recarga) {
    let f;
    try { f = await api('GET', '/api/equipe/leads/' + leadId); } catch (e) { if (!recarga) aviso(e.message, true); return; }
    ficha = f; fichaLeadId = leadId;
    fichaChamado = f.chamados.find(c => String(c.id) === String(chId)) || f.chamados.find(c => c.status !== 'fechado') || f.chamados[f.chamados.length - 1];
    fichaChId = fichaChamado ? fichaChamado.id : null;
    const lead = f.lead, nome = lead.nome || AL.fone(lead.telefone) || 'Lead';
    $('inicio').hidden = true; $('atend').hidden = false; $('area').classList.add('aberta');
    $('at-nome').textContent = nome; $('fi-nome').textContent = nome;
    $('at-num').textContent = fichaChamado ? '#' + fichaChamado.id : '';
    const meu = fichaChamado && fichaChamado.status === 'atendendo' && fichaChamado.dono === eu.id;
    const esperando = fichaChamado && ['aguardando', 'alerta'].includes(fichaChamado.status);
    $('at-sobre').textContent = !fichaChamado ? '' : meu ? 'você está atendendo' : esperando ? 'esperando alguém assumir' :
      fichaChamado.status === 'atendendo' ? 'com outra pessoa da equipe' : 'atendimento encerrado';
    const prod = fichaChamado && fichaChamado.interesse_nome;
    const selos = AL.selo(lead.status) + AL.nota(lead.nota) + (prod ? '<span class="selo">' + esc(prod) + '</span>' : '');
    $('fi-sel').innerHTML = selos;
    const hist = f.historico.length ? f.historico.map(h => esc(AL.RESULTADO[h.resultado] || h.resultado) + ' em ' + esc(AL.hora(h.em))).join(' · ') : '';
    $('at-det').innerHTML = '<div class="sel">' + selos + '</div>' + esc(AL.fone(lead.telefone)) + (AL.tempos(lead) ? ' · ' + AL.tempos(lead) : '');
    $('fi-dl').innerHTML = '<dt>Telefone</dt><dd>' + esc(AL.fone(lead.telefone)) + '</dd>' +
      (prod ? '<dt>Interesse</dt><dd>' + esc(prod) + '</dd>' : '') +
      (fichaChamado ? '<dt>Motivo</dt><dd>' + esc(AL.MOTIVO[fichaChamado.motivo] || '') + '</dd>' : '') +
      '<dt>Conversa</dt><dd>' + (AL.tempos(lead) || '—') + '</dd>' + (hist ? '<dt>Histórico</dt><dd>' + hist + '</dd>' : '') +
      (fichaChamado && fichaChamado.resumo ? '<dt>Resumo</dt><dd style="white-space:pre-wrap">' + esc(fichaChamado.resumo) + '</dd>' : '');
    const lig = fichaChamado ? botoesContato(fichaChamado, false) : '';
    $('at-ligar').innerHTML = lig; $('at-ligar-cel').innerHTML = lig;
    $('at-msgs').innerHTML = f.mensagens.map(m => AL.bolhaEquipe(m, lead.nome)).join('') || '<p class="vazio">Sem mensagens ainda.</p>';
    requestAnimationFrame(() => { $('at-msgs').scrollTop = 1e9; });
    // barra de ação: Assumir (se ainda não é de ninguém) · Responder (se é meu) · só leitura
    $('at-assumir').hidden = !esperando;
    if (esperando) {
      $('at-assumir-txt').textContent = fichaChamado.status === 'alerta' ? 'Este lead está esperando demais (' + AL.dur(fichaChamado.minutos) + '). Assuma para responder.'
        : 'Este lead está esperando há ' + AL.dur(fichaChamado.minutos) + '. Assuma para responder.';
      $('at-assumir-btn').dataset.assumir = fichaChamado.id;
      $('at-passar-btn').hidden = fichaChamado.ofertado_a !== eu.id;
      $('at-passar-btn').dataset.passar = fichaChamado.id;
    }
    $('at-responder').hidden = !meu;
    $('form-fechar').hidden = !meu;
    $('at-so-ler').hidden = meu || esperando;
    $('at-so-ler').textContent = !fichaChamado ? '' : fichaChamado.status === 'atendendo' ? 'Este atendimento está com outra pessoa da equipe.'
      : 'Atendimento encerrado' + (fichaChamado.resultado ? ' (' + (AL.RESULTADO[fichaChamado.resultado] || fichaChamado.resultado) + ')' : '') + '. Se o lead voltar a falar, um novo chamado chega pela faixa "Esperando por você".';
    if (!meu) $('area').classList.remove('encerrando');
    // Sugestão da IA (ou das regras): mostrada à parte e já na caixa de resposta; editar mantém o vínculo,
    // "Limpar" tira (aí a resposta conta como livre no aprendizado).
    const sg = meu && f.sugestao && f.sugestao.id !== descartada ? f.sugestao : null;
    $('at-sug').hidden = !sg;
    if (sg && sg.id !== sugestaoId) { sugestaoId = sg.id; $('at-sug-txt').textContent = sg.texto; }
    else if (!sg) { sugestaoId = null; }
    $('resposta').placeholder = 'Responder a ' + (lead.nome ? lead.nome.split(' ')[0] : 'o lead');
    if (!recarga) desenharContatos(); else desenharContatos();
    if (!recarga) contatos();  // abrir a ficha zera as "novas" deste lead
  }
  function fecharFicha() {
    fichaLeadId = fichaChId = null; ficha = fichaChamado = null;
    $('atend').hidden = true; $('inicio').hidden = false; $('area').classList.remove('aberta', 'encerrando');
    $('resposta').value = ''; sugestaoId = null;
    desenharContatos();
  }
  function autoAltura() { const t = $('resposta'); t.style.height = ''; t.style.height = Math.min(t.scrollHeight + 2, 160) + 'px'; }

  function camposFechar() {
    const r = $('f-resultado').value;
    document.querySelector('[data-campo=valor]').hidden = r !== 'vendeu';
    document.querySelector('[data-campo=produto]').hidden = r !== 'vendeu';
    $('f-valor').required = r === 'vendeu';
    document.querySelector('[data-campo=retornar_em]').hidden = r !== 'retornar';
    $('f-retornar').required = r === 'retornar';
    document.querySelector('[data-campo=motivo]').hidden = !MOTIVOS[r];
    $('f-motivo').innerHTML = (MOTIVOS[r] || []).map(m => '<option value="' + m[0] + '">' + m[1] + '</option>').join('');
  }

  // ---------- entrar / sair ----------
  const CHAVE = 'al_codigo_equipe';
  function sair() {
    codigo = null; localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE);
    ['espera', 'corpo', 'status-seg', 'quem', 'sair'].forEach(id => { $(id).hidden = true; });
    $('login').hidden = false; clearInterval(relogio);
  }
  async function entrar(valor, lembrar) {
    codigo = valor;
    try {
      const e0 = await api('GET', '/api/equipe/eu'); produtos = e0.produtos || [];
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      $('login').hidden = true; ['corpo', 'status-seg', 'quem', 'sair'].forEach(id => { $(id).hidden = false; });
      $('f-produto').innerHTML = '<option value="">—</option>' + produtos.map(p => '<option value="' + esc(p.id) + '">' + esc(p.nome) + '</option>').join('');
      camposFechar(); await carregar();
      // Atualização: 2 s com atendimento/ficha aberta, 5 s no resto, 15 s com a aba escondida.
      const ciclo = async () => {
        if (!codigo) return;
        try { await carregar(); } catch (_) {}
        const ativo = !!(eu && eu.chamados && eu.chamados.length) || !!document.querySelector('.area.aberta, .ficha:not([hidden])');
        relogio = setTimeout(ciclo, document.hidden ? 15000 : (ativo ? 2000 : 5000));
      };
      relogio = setTimeout(ciclo, 2000);
      document.addEventListener('visibilitychange', () => { if (!document.hidden && codigo) { clearTimeout(relogio); ciclo(); } });
    } catch (e) {
      codigo = null; localStorage.removeItem(CHAVE); sessionStorage.removeItem(CHAVE);
      $('erro-login').textContent = e.status === 401 ? 'Código inválido. Confira com o gestor.' : e.message;
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

  // ---------- ações ----------
  document.querySelectorAll('[data-status]').forEach(b => b.addEventListener('click', async () => {
    try { await api('POST', '/api/equipe/status', {status: b.dataset.status}); aviso('Status: ' + b.dataset.status + '.'); carregar(); }
    catch (e) { aviso(e.status === 409 ? 'Feche seus atendimentos antes de ficar fora.' : e.message, true); }
  }));
  document.body.addEventListener('click', async ev => {
    const t = ev.target.closest('button'); if (!t) return;
    try {
      if (t.dataset.assumir) {
        t.disabled = true;
        const id = t.dataset.assumir, ch = (eu.ofertas || []).find(o => String(o.id) === String(id));
        await api('POST', '/api/equipe/chamados/' + id + '/assumir', {});
        aviso('Você assumiu #' + id + '.'); await carregar();
        await abrirFicha(ch ? ch.lead_id : fichaLeadId, id);
        t.disabled = false;
      } else if (t.dataset.passar) {
        await api('POST', '/api/equipe/chamados/' + t.dataset.passar + '/passar', {}); aviso('Passado para o próximo da vez.');
        if (fichaChId && String(fichaChId) === String(t.dataset.passar)) fecharFicha();
        await carregar();
      } else if (t.dataset.ficha) {
        $('resposta').value = ''; sugestaoId = null; descartada = null;
        await abrirFicha(t.dataset.ficha, t.dataset.ch);
      } else if (t.hasAttribute('data-devolver')) {
        if (!confirm('Devolver este lead ao assistente? Ele volta a responder sozinho.')) return;
        await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/devolver', {}); aviso('Devolvido ao assistente.'); fecharFicha(); carregar();
      }
    } catch (e) { t.disabled = false; aviso(e.message, true); carregar(); }
  });
  $('filtros').addEventListener('click', ev => {
    const b = ev.target.closest('[data-f]'); if (!b) return;
    filtro = b.dataset.f;
    document.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    contatos();
  });
  $('busca').addEventListener('input', desenharContatos);
  $('voltar').addEventListener('click', fecharFicha);
  $('abrir-encerrar').addEventListener('click', () => {
    if (celular()) { $('area').classList.add('encerrando'); $('f-resultado').focus(); }
    else { $('f-resultado').focus(); $('form-fechar').scrollIntoView({block: 'nearest'}); }
  });
  $('fechar-folha').addEventListener('click', () => $('area').classList.remove('encerrando'));
  document.addEventListener('keydown', ev => {
    if (ev.key !== 'Escape') return;
    if ($('area').classList.contains('encerrando')) $('area').classList.remove('encerrando');
    else if (celular() && fichaLeadId) fecharFicha();
  });
  // Sugestão: Enviar manda como está · Editar leva o texto para a caixa (continua ligada à sugestão) · Limpar tira o vínculo.
  $('sug-enviar').addEventListener('click', () => responder($('at-sug-txt').textContent));
  $('sug-editar').addEventListener('click', () => { const r = $('resposta'); r.value = $('at-sug-txt').textContent; autoAltura(); r.focus(); r.setSelectionRange(r.value.length, r.value.length); });
  $('sug-limpar').addEventListener('click', () => { descartada = sugestaoId; sugestaoId = null; $('resposta').value = ''; autoAltura(); $('at-sug').hidden = true; $('resposta').focus(); });
  $('resposta').addEventListener('input', autoAltura);
  $('resposta').addEventListener('keydown', ev => { if (ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); $('form-responder').requestSubmit(); } });
  $('f-resultado').addEventListener('change', camposFechar);
  $('form-responder').addEventListener('submit', ev => { ev.preventDefault(); responder($('resposta').value); });
  async function responder(texto) {
    texto = String(texto || '').trim(); if (!texto) return;
    const corpo = {texto};
    if (sugestaoId) corpo.sugestao_id = sugestaoId;
    try {
      await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/responder', corpo);
      $('resposta').value = ''; autoAltura(); sugestaoId = null; $('at-sug').hidden = true;
      $('resposta').blur(); abrirFicha(fichaChamado.lead_id, fichaChamado.id, true);
    } catch (e) { aviso(e.message, true); }
  }
  $('form-fechar').addEventListener('submit', async ev => {
    ev.preventDefault();
    const r = $('f-resultado').value, corpo = {resultado: r};
    if (r === 'vendeu') {
      corpo.valor = parseFloat(String($('f-valor').value).replace(',', '.'));
      if (!(corpo.valor >= 0)) { aviso('Informe o valor da venda.', true); $('f-valor').focus(); return; }
      if ($('f-produto').value) corpo.produto = $('f-produto').value;
    }
    if (r === 'retornar') corpo.retornar_em = $('f-retornar').value.slice(0, 16);
    if (MOTIVOS[r]) corpo.motivo = $('f-motivo').value;
    if ($('f-nota').value.trim()) corpo.nota = $('f-nota').value.trim();
    try {
      await api('POST', '/api/equipe/chamados/' + fichaChamado.id + '/fechar', corpo);
      aviso('Atendimento #' + fichaChamado.id + ' encerrado: ' + (AL.RESULTADO[r] || r) + '.');
      $('form-fechar').reset(); camposFechar(); fecharFicha(); carregar();
    } catch (e) { aviso(e.message, true); }
  });
})();
