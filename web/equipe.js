// Painel da equipe: código na aba (sessionStorage) ou no aparelho (localStorage, se "lembrar").
(function () {
  const $ = id => document.getElementById(id);
  const ic = AL.ic, esc = AL.esc;
  let codigo = null, eu = null, ficha = null, fichaChamado = null, produtos = [], sugestaoId = null, descartada = null;
  let filtro = '', contatosCache = [], relogio = null, fichaLeadId = null, fichaChId = null;
  let vista = sessionStorage.getItem('al_vista_equipe') || 'atender';
  const visto = {};                 // chamado → id da última mensagem do lead já vista (abriu a conversa)
  let conhecidos = null;            // ofertas e mensagens já avisadas (null = 1ª carga, não avisa)
  const MOTIVOS = {sem_interesse: [['preco', 'Preço'], ['ja_comprou', 'Já comprou'], ['curioso', 'Curioso'], ['nao_quer_contato', 'Não quer mais contato'], ['outro', 'Outro']],
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
  // 1.10.8: cliente quente pede atenção forte (vermelho pulsando); morno e frio ganham a cor da nota
  // a nota do lead manda (chance de venda de lead morno não vira alarme de quente)
  const quente = ch => ch.nota === 'quente';
  function oferta(ch) {
    const demais = ch.status === 'alerta', q = quente(ch);
    return '<article class="of t-' + (q ? 'quente' : esc(ch.nota || 'frio')) + '" data-of="' + ch.id + '">' +
      (q ? '<p class="of-alarme">' + ic('flame') + 'Cliente quente: atenda agora</p>' : '') + '<div class="txt"><div class="l1"><strong>' + esc(ch.lead_nome || AL.fone(ch.telefone) || 'Lead') + '</strong>' +
      AL.nota(ch.nota) + '<span class="motivo">' + esc(AL.MOTIVO[ch.motivo] || '') + (ch.interesse_nome ? ' · ' + esc(ch.interesse_nome) : '') + '</span>' +
      '<span class="espera' + (demais ? ' demais' : '') + '">' + ic('clock') + esc(AL.dur(ch.minutos)) + (demais ? ' · esperando demais' : '') + '</span></div>' +
      (ch.silencioso ? '<p class="calado">' + ic('spark') + 'O robô viu chance de venda e chamou você. O cliente não sabe que você vem: apresente-se.</p>' : '') +
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
    $('espera').hidden = vista !== 'atender' || !eu.ofertas.length;
    $('espera-n').textContent = eu.ofertas.length;
    const peso = o => (quente(o) ? 2 : 0) + (o.status === 'alerta' ? 1 : 0);  // quente, depois esperando demais
    const ofs = eu.ofertas.slice().sort((a, b) => (peso(b) - peso(a)) || ((b.minutos || 0) - (a.minutos || 0)));
    $('ofertas').innerHTML = ofs.map(oferta).join('');
    alarmeQuente(ofs.filter(quente));
    desenharCadastro();
    desenharConversas();
    avisarNovidades();
    $('robo-mim').setAttribute('aria-pressed', String(!!eu.robo_por_mim));
    $('robo-mim').querySelector('.estado').textContent = eu.robo_por_mim ? 'ligado' : 'desligado';
    if (vista === 'equipe') await vistaEquipe();
    $('retornos').innerHTML = eu.retornos_hoje.length ? '<table><thead><tr><th>Hora</th><th>Lead</th><th>Telefone</th></tr></thead><tbody>' +
      eu.retornos_hoje.map(r => '<tr><td>' + esc(r.em.slice(11, 16)) + '</td><td>' + esc(r.nome || 'Lead') + '</td><td>' +
        esc(AL.fone(r.telefone)) + '</td></tr>').join('') + '</tbody></table>' : '<p class="vazio">Nenhum retorno marcado para hoje.</p>';
    if (vista === 'clientes') await contatos();
    if (fichaLeadId) {
      if (!digitando()) await abrirFicha(fichaLeadId, fichaChId, true);
      else await atualizarMensagens();  // digitando: só a conversa e a sugestão; o texto da caixa fica intacto
    }
  }

  // ---------- minhas conversas (1.9.8): uma linha por cliente que estou atendendo, novas em destaque ----------
  const novas = ch => ch.ultima_msg_lead > (visto[ch.id] ?? 0) && !(String(ch.id) === String(fichaChId) && !document.hidden);
  function desenharConversas() {
    const cs = (eu.chamados || []).slice().sort((a, b) => (b.sem_resposta_min ?? -1) - (a.sem_resposta_min ?? -1));
    // conversa que aparece agora: o que o lead já tinha escrito antes não é "novo" (retomada, transferência)
    cs.forEach(ch => { if (visto[ch.id] === undefined) visto[ch.id] = conhecidos && conhecidos.msg[ch.id] !== undefined ? conhecidos.msg[ch.id] : ch.ultima_msg_lead; });
    $('cv-n').textContent = cs.length;
    $('conversas').innerHTML = cs.length ? cs.map(ch => {
      const sr = ch.sem_resposta_min, nv = novas(ch);
      return '<button type="button" class="ct' + (nv ? ' tem-nova' : '') + '" data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '"' +
        (String(ch.id) === String(fichaChId) ? ' aria-current="true"' : '') + '><span class="l1"><strong>' + esc(ch.lead_nome || AL.fone(ch.telefone) || 'Lead') + '</strong>' +
        '<span class="ha">#' + ch.id + '</span></span><span class="l3">' + AL.nota(ch.nota === 'frio' ? '' : ch.nota) +
        (nv ? '<span class="selo novas">mensagem nova</span>' : '') +
        (sr != null ? '<span class="espera' + (sr >= 5 ? ' demais' : '') + '">' + ic('clock') + 'sem resposta há ' + esc(AL.dur(sr)) + '</span>' : '<span class="mut">respondido</span>') +
        '</span></button>';
    }).join('') : '<p class="vazio">Nenhuma conversa aberta. Assuma um cliente em "Para assumir".</p>';
    // abas acima do chat quando há mais de uma conversa
    const abas = $('abas-conv');
    abas.hidden = cs.length < 2;
    abas.innerHTML = cs.length < 2 ? '' : cs.map(ch => '<button type="button" data-ficha="' + ch.lead_id + '" data-ch="' + ch.id + '" aria-pressed="' +
      (String(ch.id) === String(fichaChId)) + '"' + (novas(ch) ? ' class="tem-nova"' : '') + '>' + esc((ch.lead_nome || 'Lead').split(' ')[0]) +
      (novas(ch) ? ' <span class="pt" aria-label="mensagem nova"></span>' : '') + '</button>').join('');
    const n = (eu.ofertas || []).length + cs.filter(novas).length;
    $('nv-atender').hidden = !n; $('nv-atender').textContent = n;
    document.title = (n ? '(' + n + ') ' : '') + 'Equipe · atendimento';
  }

  // ---------- avisos (1.9.8): notificação do navegador + som quando chega cliente para mim ou mensagem nova ----------
  const somLigado = () => localStorage.getItem('al_som') !== '0';
  // um AudioContext só, reaberto no primeiro clique (o navegador não deixa tocar som antes de um gesto)
  let actx = null;
  function audio() {
    try { if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)(); if (actx.state === 'suspended') actx.resume(); } catch (_) { actx = null; }
    return actx;
  }
  document.addEventListener('pointerdown', () => { if (actx && actx.state === 'suspended') actx.resume(); }, true);
  function tom(freq, ini, dur, vol) {
    const ctx = audio(); if (!ctx) return;
    const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + ini;
    o.frequency.value = freq; g.gain.setValueAtTime(vol, t); g.gain.exponentialRampToValueAtTime(0.001, t + dur);
    o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + dur);
  }
  function bip() { if (somLigado()) try { tom(880, 0, 0.4, 0.15); } catch (_) {} }
  function bipUrgente() { if (somLigado()) try { tom(988, 0, 0.18, 0.25); tom(740, 0.22, 0.18, 0.25); tom(988, 0.44, 0.25, 0.25); } catch (_) {} }
  // 1.10.8: cliente quente esperando → faixa vermelha e, se o gestor ligou, bip repetido até alguém assumir
  let alarme = null, alarmeS = 0, alarmeN = 0;
  function alarmeQuente(qs) {
    const on = qs.length > 0, cfg = eu.alertas || {};
    $('alerta-quente').hidden = !on;
    if (qs.length !== alarmeN) { alarmeN = qs.length; $('quente-sr').textContent = qs.length ? qs.length + (qs.length === 1 ? ' cliente quente esperando' : ' clientes quentes esperando') : ''; }
    $('espera').classList.toggle('tem-quente', on);
    if (on) $('alerta-quente-txt').textContent = qs.length === 1 ? (qs[0].lead_nome || 'Cliente') + ' é cliente quente e está esperando há ' + AL.dur(qs[0].minutos) + ': atenda agora'
      : qs.length + ' clientes quentes esperando: atenda agora';
    const tocar = on && cfg.bip_quente && eu.status !== 'fora';  // quem está Fora não pode assumir: sem bip
    $('som-quente').hidden = !tocar || (somLigado() && actx && actx.state === 'running');
    if (!tocar) { clearInterval(alarme); alarme = null; return; }
    const s = Math.max(5, cfg.bip_s || 20);
    if (alarme && alarmeS === s) return;
    clearInterval(alarme); alarmeS = s;
    bipUrgente(); alarme = setInterval(bipUrgente, s * 1000);
  }
  function notificar(titulo, corpo) {
    bip();
    if (window.Notification && Notification.permission === 'granted' && document.hidden) {
      try { const n = new Notification(titulo, {body: corpo, tag: 'al-equipe'}); n.onclick = () => { window.focus(); n.close(); }; } catch (_) {}
    }
  }
  function avisarNovidades() {
    const atual = {of: new Set((eu.ofertas || []).map(o => o.id)), msg: {}};
    (eu.chamados || []).forEach(ch => { atual.msg[ch.id] = ch.ultima_msg_lead; });
    if (conhecidos) {
      const of = (eu.ofertas || []).filter(o => !conhecidos.of.has(o.id));
      if (of.length) notificar('Cliente para assumir', (of[0].lead_nome || 'Um cliente') + (of.length > 1 ? ' e mais ' + (of.length - 1) : '') + ' está esperando.');
      const ms = (eu.chamados || []).filter(ch => ch.ultima_msg_lead > (conhecidos.msg[ch.id] ?? ch.ultima_msg_lead));
      if (ms.length && !(ms.length === 1 && String(ms[0].id) === String(fichaChId) && !document.hidden))
        notificar('Mensagem nova', (ms[0].lead_nome || 'Cliente') + ' escreveu.');
    }
    conhecidos = atual;
  }
  function textoAvisos() {
    const perm = window.Notification ? Notification.permission : 'denied';
    $('avisos-txt').textContent = perm === 'granted' ? (somLigado() ? 'Avisos e som ligados' : 'Avisos ligados, sem som') : perm === 'denied' ? (somLigado() ? 'Som ligado' : 'Som desligado') : 'Ativar avisos';
  }
  textoAvisos();

  // ---------- vista Equipe (1.9.8): o que está com os outros fica aqui, fora da tela de atender ----------
  async function vistaEquipe() {
    let p; try { p = await api('GET', '/api/painel'); } catch (_) { return; }
    const nome = id => ((p.equipe.find(e => e.id === id) || {}).nome) || id || '—';
    $('ve-equipe').innerHTML = p.equipe.map(e => '<div class="it"><div class="l1">' + AL.ponto(e.status) + '<strong>' + esc(e.nome) + '</strong>' +
      (e.robo_por_mim ? '<span class="selo">' + ic('spark') + 'robô responde</span>' : '') + '<span class="dir">' + esc(AL.COLAB[e.status] || e.status) +
      (e.status !== 'atendendo' ? ' há ' + esc(AL.dur(e.minutos)) : '') + '</span></div>' + (e.proximo ? '<p><strong>Próximo da vez</strong></p>' : '') + '</div>').join('');
    $('ve-fila-n').textContent = p.fila.length;
    $('ve-fila').innerHTML = p.fila.length ? p.fila.map(f => '<div class="it"><div class="l1"><strong>' + esc(f.lead || 'Lead') + '</strong>' +
      (f.prioridade === 'quente' ? AL.nota('quente') : '') + '<span class="espera' + (f.status === 'alerta' ? ' demais' : '') + '" style="margin-left:auto">' + ic('clock') +
      esc(AL.dur(f.minutos)) + '</span></div><p>' + esc(AL.MOTIVO[f.motivo] || '') + (f.ofertado_a ? ' · oferecido a ' + esc(nome(f.ofertado_a)) : '') + '</p></div>').join('')
      : '<p class="vazio">Ninguém esperando.</p>';
    const at = p.atendendo || [];
    $('ve-at-n').textContent = at.length;
    $('ve-atendendo').innerHTML = at.length ? at.map(a => '<div class="it"><div class="l1"><strong>' + esc(a.lead || 'Lead') + '</strong><span class="dir">há ' +
      esc(AL.dur(a.minutos)) + '</span></div><p>com ' + esc(nome(a.dono)) + '</p></div>').join('') : '<p class="vazio">Ninguém em atendimento.</p>';
  }

  function mudarVista(v) {
    vista = v; sessionStorage.setItem('al_vista_equipe', v);
    document.querySelector('.eq-app').dataset.vista = v;
    document.querySelectorAll('[data-vista]').forEach(b => { const s = b.dataset.vista === v; b.setAttribute('aria-selected', String(s)); b.tabIndex = s ? 0 : -1; });
    $('vista-equipe').hidden = v !== 'equipe';
    $('corpo').hidden = v === 'equipe';
    $('espera').hidden = v !== 'atender' || !(eu && eu.ofertas && eu.ofertas.length);
    if (v === 'clientes') contatos();
    if (v === 'equipe') vistaEquipe();
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
      (l.nao_contatar ? '<span class="selo st-perdido">não quer contato</span>' : '') +
      (l.retornar_em ? '<span class="selo st-retornar">' + ic('cal') + 'retorno ' + esc(AL.hora(l.retornar_em)) + '</span>' : '') + '</span>' +
      '<span class="l3" style="margin-top:4px">' + AL.tempos(l) + '</span></button>').join('')
      : '<p class="vazio">Nenhum contato' + (filtro ? ' com este status' : '') + (q ? ' para essa busca' : '') + '.</p>';
  }

  // ---------- ficha / atendimento ----------
  const digitando = () => document.activeElement === $('resposta') || !!$('resposta').value.trim();

  // Atualiza só as mensagens (e a sugestão) da ficha aberta, sem mexer na caixa de resposta nem no formulário.
  async function atualizarMensagens() {
    let f;
    try { f = await api('GET', '/api/equipe/leads/' + fichaLeadId); } catch (_) { return; }
    const box = $('at-msgs');
    const noFim = box.scrollHeight - box.scrollTop - box.clientHeight < 40;
    const html = f.mensagens.map(m => AL.bolhaEquipe(m, f.lead.nome)).join('') || '<p class="vazio">Sem mensagens ainda.</p>';
    if (box.innerHTML !== html) { box.innerHTML = html; if (noFim) box.scrollTop = 1e9; }
    ficha = f;
    const ch = f.chamados.find(c => String(c.id) === String(fichaChId));
    const meu = ch && ch.status === 'atendendo' && ch.dono === eu.id;
    const sg = meu && f.sugestao && f.sugestao.id !== descartada ? f.sugestao : null;
    if (sg && sg.id !== sugestaoId) { sugestaoId = sg.id; $('at-sug-txt').textContent = sg.texto; $('at-sug').hidden = false; }
    mostrarConflito(sg);
  }
  // Divergência entre a base e o que o vendedor disse: aviso discreto + "Atualizar a base" (proposta ao gestor).
  let conflitoSid = null;
  function mostrarConflito(sg) {
    const tem = !!(sg && sg.conflito);
    $('at-conf').hidden = !tem;
    if (!tem) { conflitoSid = null; return; }
    if (conflitoSid === sg.id) return;
    conflitoSid = sg.id; $('at-conf-txt').textContent = sg.conflito;
    const b = $('conf-base'); b.disabled = !!sg.proposta_id;
    b.lastChild.textContent = sg.proposta_id ? 'Enviado ao gestor ✓' : 'Atualizar a base';
  }

  async function abrirFicha(leadId, chId, recarga) {
    let f;
    try { f = await api('GET', '/api/equipe/leads/' + leadId); } catch (e) { if (!recarga) aviso(e.message, true); return; }
    ficha = f; fichaLeadId = leadId;
    const chv = (eu.chamados || []).find(c => String(c.lead_id) === String(leadId));
    if (chv) visto[chv.id] = chv.ultima_msg_lead;
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
    const encerrado = !fichaChamado || fichaChamado.status === 'fechado';
    $('at-so-ler').hidden = meu || esperando || encerrado;
    $('at-retomar').hidden = !encerrado;
    if (encerrado) {
      const apagado = String(lead.telefone || '').startsWith('apagado-');
      const bloq = !!lead.nao_contatar || apagado;
      $('at-retomar-txt').textContent = apagado ? 'Este cliente pediu para apagar os dados.' : bloq ? 'Este cliente pediu para não ser mais contatado. Se ele voltar a escrever, o atendimento é liberado de novo.'
        : 'Atendimento encerrado' + (fichaChamado && fichaChamado.resultado ? ' (' + (AL.RESULTADO[fichaChamado.resultado] || fichaChamado.resultado) + ')' : '') + '. Você pode voltar a falar com este cliente.';
      $('at-retomar-btn').hidden = bloq; $('at-retomar-btn').dataset.lead = leadId;
    }
    $('at-so-ler').textContent = !fichaChamado ? '' : fichaChamado.status === 'atendendo' ? 'Este atendimento está com outra pessoa da equipe.'
      : 'Atendimento encerrado' + (fichaChamado.resultado ? ' (' + (AL.RESULTADO[fichaChamado.resultado] || fichaChamado.resultado) + ')' : '') + '. Se o lead voltar a falar, um novo chamado chega pela faixa "Esperando por você".';
    if (!meu) $('area').classList.remove('encerrando');
    // Sugestão da IA (ou das regras): mostrada à parte e já na caixa de resposta; editar mantém o vínculo,
    // "Limpar" tira (aí a resposta conta como livre no aprendizado).
    const sg = meu && f.sugestao && f.sugestao.id !== descartada ? f.sugestao : null;
    $('at-sug').hidden = !sg;
    if (sg && sg.id !== sugestaoId) { sugestaoId = sg.id; $('at-sug-txt').textContent = sg.texto; }
    else if (!sg) { sugestaoId = null; }
    mostrarConflito(sg);
    $('resposta').placeholder = 'Responder a ' + (lead.nome ? lead.nome.split(' ')[0] : 'o lead');
    desenharContatos(); if (eu) desenharConversas();
    if (!recarga) contatos();  // abrir a ficha zera as "novas" deste lead
  }
  function fecharFicha() {
    fichaLeadId = fichaChId = null; ficha = fichaChamado = null;
    $('atend').hidden = true; $('inicio').hidden = false; $('area').classList.remove('aberta', 'encerrando');
    if (eu) desenharConversas();
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
    ['espera', 'corpo', 'status-seg', 'quem', 'sair', 'atualizar-w', 'eq-nav', 'vista-equipe'].forEach(id => { $(id).hidden = true; });
    $('login').hidden = false; clearInterval(relogio);
  }
  async function entrar(valor, lembrar) {
    codigo = valor;
    try {
      const e0 = await api('GET', '/api/equipe/eu'); produtos = e0.produtos || [];
      (lembrar ? localStorage : sessionStorage).setItem(CHAVE, valor);
      $('login').hidden = true; ['corpo', 'status-seg', 'quem', 'sair', 'atualizar-w', 'eq-nav'].forEach(id => { $(id).hidden = false; });
      mudarVista(vista);
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
  document.querySelectorAll('[data-vista]').forEach(b => b.addEventListener('click', () => mudarVista(b.dataset.vista)));
  $('eq-nav').querySelector('[role=tablist]').addEventListener('keydown', ev => {
    if (!['ArrowLeft', 'ArrowRight'].includes(ev.key)) return;
    const bs = [...document.querySelectorAll('[data-vista]')], i = bs.findIndex(b => b.dataset.vista === vista);
    const n = bs[(i + (ev.key === 'ArrowRight' ? 1 : bs.length - 1)) % bs.length]; mudarVista(n.dataset.vista); n.focus();
  });
  $('robo-mim').addEventListener('click', async () => {
    const ativo = $('robo-mim').getAttribute('aria-pressed') !== 'true';
    try { await api('POST', '/api/equipe/robo', {ativo}); aviso(ativo ? 'O robô vai responder as dúvidas dos seus clientes enquanto você não responde.' : 'Robô desligado: só você responde.'); carregar(); }
    catch (e) { aviso(e.message, true); }
  });
  $('avisos').addEventListener('click', async () => {
    if (window.Notification && Notification.permission === 'default') { try { await Notification.requestPermission(); } catch (_) {} localStorage.setItem('al_som', '1'); bip(); }
    else { localStorage.setItem('al_som', somLigado() ? '0' : '1'); if (somLigado()) bip(); }
    textoAvisos();
  });
  $('som-quente').addEventListener('click', () => {
    localStorage.setItem('al_som', '1'); audio(); bipUrgente(); $('som-quente').hidden = true; textoAvisos();
  });

  // ---------- meu cadastro (1.10.8): nome e telefone; o gestor aprova a mudança (ou deixa valer na hora) ----------
  function desenharCadastro() {
    const pf = eu.perfil || {};
    $('meu-cad-st').hidden = !pf.pendente;
  }
  function abrirCadastro() {
    const pf = eu.perfil || {}, pend = pf.pendente, ult = pf.ultimo;
    $('cad-regra').textContent = pf.sem_aprovacao ? 'A mudança vale na hora.' : 'A mudança vale depois que o gestor aprovar.';
    $('cad-nome').value = pend && pend.dados.nome != null ? pend.dados.nome : pf.nome || '';
    $('cad-tel').value = pend && pend.dados.telefone != null ? AL.fone(pend.dados.telefone) : AL.fone(pf.telefone || '');
    const msgs = [];
    if (pend) msgs.push('Pedido enviado em ' + pend.em.slice(8, 10) + '/' + pend.em.slice(5, 7) + ' às ' + pend.em.slice(11, 16) + ', aguardando o gestor. Enviar de novo troca o pedido.');
    else if (ult && ult.status === 'recusado') msgs.push('Seu último pedido foi recusado' + (ult.motivo ? ': ' + ult.motivo : '') + '.');
    $('cad-pend').textContent = msgs.join(' '); $('cad-pend').hidden = !msgs.length;
    $('cad-cancelar-pedido').hidden = !pend;
    $('cad-erro').textContent = '';
    $('dlg-cad').showModal();
  }
  $('meu-cad').addEventListener('click', abrirCadastro);
  $('cad-fechar').addEventListener('click', () => $('dlg-cad').close());
  $('form-cad').addEventListener('submit', async ev => {
    ev.preventDefault();
    const pf = eu.perfil || {}, corpo = {};
    const nome = $('cad-nome').value.trim(), tel = $('cad-tel').value.replace(/\D/g, '');
    if (nome !== (pf.nome || '')) corpo.nome = nome;
    if ((/^\d{10,11}$/.test(tel) ? '55' + tel : tel) !== String(pf.telefone || '')) corpo.telefone = tel;
    if (!Object.keys(corpo).length) { $('cad-erro').textContent = 'Nada mudou.'; return; }
    try {
      const r = await api('POST', '/api/equipe/perfil', corpo);
      eu.perfil = r; $('dlg-cad').close(); desenharCadastro();
      aviso(r.aplicado ? 'Cadastro atualizado.' : 'Pedido enviado ao gestor.');
      if (r.aplicado) { $('quem-nome').textContent = r.nome; $('quem-av').textContent = AL.iniciais(r.nome); }
    } catch (e) { $('cad-erro').textContent = e.message || 'Não deu para enviar.'; }
  });
  $('cad-cancelar-pedido').addEventListener('click', async () => {
    try { eu.perfil = await api('DELETE', '/api/equipe/perfil'); $('dlg-cad').close(); desenharCadastro(); aviso('Pedido cancelado.'); }
    catch (e) { $('cad-erro').textContent = e.message || 'Não deu para cancelar.'; }
  });
  $('at-retomar-btn').addEventListener('click', async () => {
    const b = $('at-retomar-btn'); b.disabled = true;
    try {
      const r = await api('POST', '/api/equipe/leads/' + b.dataset.lead + '/retomar', {});
      aviso('Conversa retomada. Escreva para o cliente.'); await carregar(); mudarVista('atender');
      await abrirFicha(r.lead_id, r.id); $('resposta').focus();
    } catch (e) { aviso(e.message, true); } finally { b.disabled = false; }
  });
  $('filtros').addEventListener('click', ev => {
    const b = ev.target.closest('[data-f]'); if (!b) return;
    filtro = b.dataset.f;
    document.querySelectorAll('[data-f]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    contatos();
  });
  $('busca').addEventListener('input', desenharContatos);
  // Atualizar (1.7.8): relê /api/equipe/eu, contatos e a ficha aberta sem sair; o texto da caixa de resposta fica.
  async function atualizar() {
    if (!codigo) return;
    const b = $('atualizar'); b.disabled = true;
    try {
      const e0 = await api('GET', '/api/equipe/eu');
      const prod = e0.produtos || [], sel = $('f-produto').value;
      if (JSON.stringify(prod) !== JSON.stringify(produtos)) {
        produtos = prod;
        $('f-produto').innerHTML = '<option value="">—</option>' + produtos.map(p => '<option value="' + esc(p.id) + '">' + esc(p.nome) + '</option>').join('');
        $('f-produto').value = sel;
      }
      await carregar();
      $('atualizado').textContent = 'Atualizado às ' + AL.agoraHM();
      if (window.innerWidth < 1024) aviso($('atualizado').textContent + '.');
    } catch (e) { aviso(e.message, true); } finally { b.disabled = false; }
  }
  $('atualizar').addEventListener('click', atualizar);
  AL.atalhoAtualizar(atualizar);
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
  $('conf-base').addEventListener('click', async () => {
    const b = $('conf-base'); if (!conflitoSid || b.disabled) return;
    b.disabled = true;
    try { await api('POST', '/api/equipe/sugestoes/' + conflitoSid + '/base', {}); b.lastChild.textContent = 'Enviado ao gestor ✓'; }
    catch (e) { b.disabled = false; aviso(e.message, true); }
  });
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
