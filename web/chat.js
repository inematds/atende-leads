// Chat web do lead. Identidade = sessão (localStorage), não o telefone: a 1ª mensagem cria o lead web e
// devolve `sessao`; as seguintes mandam a sessão. Respostas da equipe chegam por GET /api/web/<sessao>.
// Tema, cor de destaque e nome exibido vêm de GET /api/aparencia (Cadastros → Aparência do gestor).
(function () {
  if (new URLSearchParams(location.search).get('widget') === '1') document.body.classList.add('widget');
  const $ = id => document.getElementById(id);
  const guarda = window.localStorage;
  let tel = guarda.getItem('al_tel'), nome = guarda.getItem('al_nome') || '', sessao = guarda.getItem('al_sessao');
  let vistos = 0, relogio = null, colaborador = null;

  function aplicarAparencia(a) {
    if (!a) return;
    AL.aplicarTema(a.tema);
    const raiz = document.documentElement.style;
    if (a.cor_destaque) {
      const tinta = a.cor_destaque_texto || '#1a1206';
      const mut = tinta === '#ffffff' ? 'rgba(255,255,255,.85)' : 'rgba(26,18,6,.74)';
      [['--amb', a.cor_destaque], ['--amb-borda', a.cor_destaque], ['--amb-hover', a.cor_destaque], ['--amb-tinta', tinta],
        ['--b-eu', a.cor_destaque], ['--b-eu-tinta', tinta], ['--b-eu-mut', mut], ['--foco', a.cor_destaque]].forEach(([k, v]) => raiz.setProperty(k, v));
    } else {
      ['--amb', '--amb-borda', '--amb-hover', '--amb-tinta', '--b-eu', '--b-eu-tinta', '--b-eu-mut', '--foco'].forEach(k => raiz.removeProperty(k));
    }
    const n = a.nome_exibido || 'Atendimento';
    $('negocio').textContent = n;
    $('logo').textContent = AL.iniciais(n);
    document.title = 'Fale com ' + n;
  }
  try { aplicarAparencia(JSON.parse(guarda.getItem('al_aparencia') || 'null')); } catch (e) { /* cache vazio */ }
  AL.api('GET', '/api/aparencia').then(a => { guarda.setItem('al_aparencia', JSON.stringify(a)); aplicarAparencia(a); }).catch(() => {});

  // Sempre leva à última mensagem (depois do layout, para pegar a altura certa).
  function aoFim() {
    const log = $('log');
    requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  }
  const agoraHM = () => new Date().toTimeString().slice(0, 5);

  function bolha(texto, classe, rotulo, hora) {
    const d = document.createElement('div');
    d.className = 'b ' + (classe || '');
    d.innerHTML = (rotulo ? '<small>' + AL.esc(rotulo) + '</small>' : '') + AL.esc(texto) + '<time>' + AL.esc(hora || agoraHM()) + '</time>';
    $('log').appendChild(d);
    aoFim();
  }
  function separador(texto) {
    const d = document.createElement('div');
    d.className = 'sep'; d.textContent = texto;
    $('log').appendChild(d);
    aoFim();
  }
  function estado(nomeColab) {
    colaborador = nomeColab || null;
    $('estado-txt').textContent = colaborador ? colaborador + ' · equipe · está te atendendo' : 'Assistente virtual · responde na hora';
  }

  // Teclado do celular: onde o navegador não encolhe o layout (iOS), a página segue a altura visível,
  // e a caixa de escrever continua à vista.
  if (window.visualViewport) {
    const ajustar = () => {
      document.body.style.height = window.visualViewport.height + 'px';
      window.scrollTo(0, 0);
      aoFim();
    };
    window.visualViewport.addEventListener('resize', ajustar);
  }

  function esquecer() {
    sessao = null; ['al_sessao', 'al_tel', 'al_nome'].forEach(k => guarda.removeItem(k));
  }

  async function enviar(texto, mostrar) {
    if (mostrar !== false) bolha(texto, 'minha');
    const corpo = sessao ? {sessao, texto, canal: 'web'} : {telefone: tel, texto, nome: nome || undefined, canal: 'web'};
    try {
      const r = await AL.api('POST', '/api/mensagens', corpo);
      if (r.sessao) { sessao = r.sessao; guarda.setItem('al_sessao', sessao); }
      r.respostas.forEach(t => bolha(t, 'ele', 'Assistente virtual'));
      vistos = -1; // reconta no próximo ciclo
    } catch (e) {
      if (e.status === 404 && sessao) { esquecer(); bolha('Sua conversa expirou. Recarregue a página para começar de novo.', 'falha'); }
      else bolha('Não consegui enviar: ' + e.message + '. Tente de novo.', 'falha');
    }
  }

  async function puxar(historico) {
    if (!sessao) return;
    try {
      const m = await AL.api('GET', '/api/web/' + encodeURIComponent(sessao));
      if (m.colaborador !== colaborador) estado(m.colaborador);
      const msgs = m.mensagens || [];
      // Ao voltar à página: a conversa inteira (sem o "Olá" automático do início).
      if (historico) {
        $('log').innerHTML = '';
        msgs.forEach((x, i) => {
          if (x.de === 'lead') { if (!(i === 0 && x.texto === 'Olá')) bolha(x.texto, 'minha', '', AL.hm(x.em)); }
          else if (x.tipo === 'aviso') separador(x.texto);
          else if (x.de === 'humano') bolha(x.texto, 'ele', (m.colaborador || 'Equipe') + ' · equipe', AL.hm(x.em));
          else if (x.de === 'agente') bolha(x.texto, 'ele', 'Assistente virtual', AL.hm(x.em));
        });
      }
      // Respostas da equipe e avisos (ex.: "Ana vai te atender agora."); as do agente já apareceram no envio.
      const humanos = msgs.filter(x => x.de === 'humano' || x.tipo === 'aviso');
      if (vistos === -1 || historico) vistos = humanos.length;
      humanos.slice(vistos).forEach(x => x.de === 'humano'
        ? bolha(x.texto, 'ele', (m.colaborador || 'Equipe') + ' · equipe', AL.hm(x.em)) : separador(x.texto));
      vistos = humanos.length;
    } catch (e) { /* silencioso */ }
  }

  function abrirChat(voltando) {
    $('entrada').hidden = true; $('chat').hidden = false; $('texto').focus();
    $('texto').addEventListener('focus', () => setTimeout(aoFim, 300));
    vistos = -1; puxar(voltando);
    if (!relogio) relogio = setInterval(() => { if (!document.hidden) puxar(false); }, 2000);
  }

  $('form-entrada').addEventListener('submit', ev => {
    ev.preventDefault();
    const d = $('telefone').value.replace(/\D/g, '');
    if (d.length < 10 || d.length > 13) { $('erro-entrada').textContent = 'Confira o número com DDD.'; $('telefone').focus(); return; }
    tel = d; nome = $('nome').value.trim(); sessao = null;
    guarda.setItem('al_tel', tel); guarda.setItem('al_nome', nome); guarda.removeItem('al_sessao');
    abrirChat(false);
    separador('Você entrou na conversa · ' + agoraHM());
    enviar('Olá', false);  // cria o lead; o "Olá" não aparece como se o lead tivesse escrito
  });
  function mandar() {
    const t = $('texto').value.trim();
    if (!t) return;
    $('texto').value = ''; $('texto').style.height = '';
    enviar(t);
  }
  $('form-msg').addEventListener('submit', ev => { ev.preventDefault(); mandar(); });
  $('texto').addEventListener('keydown', ev => {
    if (ev.key === 'Enter' && !ev.shiftKey && !ev.isComposing) { ev.preventDefault(); mandar(); }
  });
  $('texto').addEventListener('input', () => {
    const t = $('texto'); t.style.height = ''; t.style.height = Math.min(t.scrollHeight + 2, 120) + 'px';
  });
  if (sessao) abrirChat(true);
})();
