// Chat web do lead: mesma conversa de POST /api/mensagens; mensagens humanas chegam por /api/meu/<token>.
(function () {
  if (new URLSearchParams(location.search).get('widget') === '1') document.body.classList.add('widget');
  const $ = id => document.getElementById(id);
  let tel = sessionStorage.getItem('al_tel'), nome = sessionStorage.getItem('al_nome') || '', token = sessionStorage.getItem('al_tok');
  let vistos = 0;

  function bolha(texto, classe, rotulo) {
    const d = document.createElement('div');
    d.className = 'bolha ' + (classe || '');
    d.innerHTML = (rotulo ? '<small>' + AL.esc(rotulo) + '</small>' : '') + AL.esc(texto);
    $('log').appendChild(d);
    $('log').scrollTop = $('log').scrollHeight;
  }

  async function enviar(texto) {
    bolha(texto, 'minha');
    try {
      const r = await AL.api('POST', '/api/mensagens', {telefone: tel, texto, nome: nome || undefined, canal: 'web'});
      token = r.lead.token; sessionStorage.setItem('al_tok', token);
      r.respostas.forEach(t => bolha(t));
      vistos = -1; // reconta no próximo ciclo
    } catch (e) { bolha('Não consegui enviar: ' + e.message, 'erro'); }
  }

  async function puxar() {
    if (!token) return;
    try {
      const m = await AL.api('GET', '/api/meu/' + token);
      const humanos = (m.mensagens || []).filter(x => x.de === 'humano');
      if (vistos === -1) vistos = humanos.length;
      humanos.slice(vistos).forEach(x => bolha(x.texto, 'humano', m.colaborador || 'Equipe'));
      vistos = humanos.length;
    } catch (e) { /* silencioso */ }
  }

  function abrirChat() {
    $('entrada').hidden = true; $('chat').hidden = false; $('texto').focus();
    vistos = -1; puxar(); setInterval(puxar, 5000);
  }

  $('form-entrada').addEventListener('submit', ev => {
    ev.preventDefault();
    const d = $('telefone').value.replace(/\D/g, '');
    if (d.length < 10 || d.length > 13) { $('erro-entrada').textContent = 'Confira o número com DDD.'; return; }
    tel = d; nome = $('nome').value.trim();
    sessionStorage.setItem('al_tel', tel); sessionStorage.setItem('al_nome', nome);
    abrirChat();
    enviar('Olá');
  });
  $('form-msg').addEventListener('submit', ev => {
    ev.preventDefault();
    const t = $('texto').value.trim();
    if (!t) return;
    $('texto').value = '';
    enviar(t);
  });
  AL.api('GET', '/api/saude').then(() => {}).catch(() => {});
  if (tel) abrirChat();
})();
